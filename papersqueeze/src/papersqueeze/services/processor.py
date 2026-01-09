"""Main document processing orchestrator."""

import time
from typing import Any

import structlog

from papersqueeze.api.claude import ClaudeClient
from papersqueeze.api.paperless import PaperlessClient
from papersqueeze.config.schema import AppConfig, Template, TemplatesConfig
from papersqueeze.exceptions import ProcessingError
from papersqueeze.models.document import CustomFieldValue, Document, DocumentUpdate
from papersqueeze.models.extraction import ProcessingResult, ProposedChange
from papersqueeze.processors.base import BaseProcessor
from papersqueeze.processors.fines import FinesProcessor
from papersqueeze.processors.general import GeneralProcessor
from papersqueeze.processors.tax import TaxProcessor
from papersqueeze.processors.utilities import (
    UtilitiesEnergyProcessor,
    UtilitiesWaterProcessor,
)
from papersqueeze.services.confidence import ConfidenceScorer
from papersqueeze.services.merge import MergeStrategy
from papersqueeze.services.review import ReviewQueue

logger = structlog.get_logger()


class DocumentProcessor:
    """Main document processing orchestrator.

    Coordinates the full processing pipeline:
    1. Fetch document from paperless-ngx
    2. Classify document type (gatekeeper AI)
    3. Extract metadata (specialist AI)
    4. Normalize extracted data
    5. Calculate confidence scores
    6. Smart merge with existing metadata
    7. Apply auto-approved changes OR submit for review
    """

    # Map template IDs to processor classes
    PROCESSORS: dict[str, type[BaseProcessor]] = {
        "utilities_energy": UtilitiesEnergyProcessor,
        "utilities_water": UtilitiesWaterProcessor,
        "tax_at_guides": TaxProcessor,
        "law_enforcement_fines": FinesProcessor,
        "fallback_general": GeneralProcessor,
    }

    def __init__(
        self,
        config: AppConfig,
        templates: TemplatesConfig,
        paperless: PaperlessClient,
        claude: ClaudeClient,
    ) -> None:
        """Initialize the document processor.

        Args:
            config: Application configuration.
            templates: Templates configuration.
            paperless: Paperless-ngx API client.
            claude: Claude API client.
        """
        self.config = config
        self.templates = templates
        self.paperless = paperless
        self.claude = claude

        # Initialize services
        self.confidence_scorer = ConfidenceScorer()
        self.merge_strategy = MergeStrategy(
            auto_apply_threshold=config.processing.confidence_threshold,
            suggestion_threshold=config.processing.review_threshold,
        )
        self.review_queue = ReviewQueue(paperless, config.tags.review)

        # Cache processor instances
        self._processors: dict[str, BaseProcessor] = {}

    def get_processor(self, template_id: str) -> BaseProcessor:
        """Get or create a processor for the given template ID.

        Args:
            template_id: Template identifier.

        Returns:
            Processor instance.
        """
        if template_id not in self._processors:
            processor_class = self.PROCESSORS.get(template_id, GeneralProcessor)
            self._processors[template_id] = processor_class()
        return self._processors[template_id]

    async def process_document(
        self,
        doc_id: int,
        dry_run: bool = False,
    ) -> ProcessingResult:
        """Process a single document.

        Args:
            doc_id: Document ID in paperless-ngx.
            dry_run: If True, don't apply changes, just report what would happen.

        Returns:
            ProcessingResult with details of what was done.

        Raises:
            ProcessingError: If processing fails.
        """
        start_time = time.perf_counter()
        log = logger.bind(doc_id=doc_id, dry_run=dry_run)
        log.info("Processing document")

        try:
            # Step 1: Fetch document
            log.debug("Fetching document from paperless-ngx")
            document = await self.paperless.get_document(doc_id)

            # Skip if already processed and not forcing
            if document.has_tag(self.config.tags.review.processed):
                log.info("Document already processed, skipping")
                return ProcessingResult(
                    doc_id=doc_id,
                    success=True,
                    error_message="Already processed",
                    processing_time_ms=(time.perf_counter() - start_time) * 1000,
                )

            # Step 2: Truncate content for AI
            content = document.content[:self.config.processing.max_content_length]
            if not content.strip():
                log.warning("Document has no content, skipping")
                return ProcessingResult(
                    doc_id=doc_id,
                    success=False,
                    error_message="Document has no OCR content",
                    processing_time_ms=(time.perf_counter() - start_time) * 1000,
                )

            # Step 3: Classify and extract
            log.debug("Running AI classification and extraction")
            classification, extraction = self.claude.classify_and_extract(
                content=content,
                templates_config=self.templates,
            )

            # Step 4: Get template and processor
            template = self.templates.get_template_by_id(classification.template_id)
            if not template:
                template = self.templates.get_template_by_id("fallback_general")
                if not template:
                    raise ProcessingError(
                        "No template found",
                        doc_id=doc_id,
                        stage="template_lookup",
                    )

            processor = self.get_processor(classification.template_id)

            # Step 5: Normalize extracted data
            log.debug("Normalizing extraction")
            extraction = processor.normalize_extraction(extraction)
            extraction = processor.post_process(extraction, document)

            # Step 6: Calculate confidence
            confidence = self.confidence_scorer.score_extraction(extraction, template)
            log.info(
                "Extraction scored",
                overall_confidence=f"{confidence.overall:.0%}",
                explanation=confidence.explanation,
            )

            # Step 7: Smart merge
            merge_result = self.merge_strategy.merge_document(
                document=document,
                extraction=extraction,
                field_mapping=template.field_mapping,
                confidence=confidence,
            )

            # Step 8: Handle title
            proposed_title = processor.format_title(template, extraction, document)
            title_merge = self.merge_strategy.merge_title(
                existing_title=document.title,
                proposed_title=proposed_title,
                confidence=confidence.overall,
            )

            # Collect all proposed changes
            all_proposed: list[ProposedChange] = []
            all_proposed.extend(merge_result.auto_apply_changes)
            all_proposed.extend(merge_result.review_changes)

            if title_merge.is_change:
                all_proposed.append(
                    ProposedChange(
                        field_name="title",
                        current_value=title_merge.existing_value,
                        proposed_value=title_merge.ai_value,
                        confidence=title_merge.ai_confidence,
                        reason=title_merge.reason,
                    )
                )

            # Step 9: Apply or queue for review
            applied_changes: list[ProposedChange] = []

            if dry_run:
                log.info(
                    "Dry run complete",
                    auto_apply=len(merge_result.auto_apply_changes),
                    needs_review=len(merge_result.review_changes),
                    proposed_title=proposed_title if title_merge.is_change else None,
                )
            else:
                # Apply auto-approved changes
                if merge_result.auto_apply_changes or title_merge.is_auto_apply:
                    applied_changes = await self._apply_auto_changes(
                        doc_id=doc_id,
                        document=document,
                        changes=merge_result.auto_apply_changes,
                        title_change=title_merge if title_merge.is_auto_apply else None,
                        template=template,
                    )

                # Submit for review if needed
                if merge_result.review_changes or (
                    title_merge.is_change and not title_merge.is_auto_apply
                ):
                    review_changes = list(merge_result.review_changes)
                    if title_merge.is_change and not title_merge.is_auto_apply:
                        review_changes.append(
                            ProposedChange(
                                field_name="title",
                                current_value=title_merge.existing_value,
                                proposed_value=title_merge.ai_value,
                                confidence=title_merge.ai_confidence,
                                reason=title_merge.reason,
                            )
                        )
                    await self.review_queue.submit_for_review(doc_id, review_changes)
                elif applied_changes:
                    # All changes applied, mark as processed
                    await self.review_queue.mark_processed(doc_id)

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            result = ProcessingResult(
                doc_id=doc_id,
                success=True,
                template_id=classification.template_id,
                classification=classification,
                extraction=extraction,
                proposed_changes=all_proposed,
                applied_changes=applied_changes,
                review_required=merge_result.needs_review,
                processing_time_ms=elapsed_ms,
            )

            log.info(
                "Document processed",
                template=classification.template_id,
                confidence=f"{confidence.overall:.0%}",
                auto_applied=len(applied_changes),
                needs_review=result.review_required,
                elapsed_ms=round(elapsed_ms),
            )

            return result

        except ProcessingError:
            raise
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            log.error("Processing failed", error=str(e))
            return ProcessingResult(
                doc_id=doc_id,
                success=False,
                error_message=str(e),
                processing_time_ms=elapsed_ms,
            )

    async def _apply_auto_changes(
        self,
        doc_id: int,
        document: Document,
        changes: list[ProposedChange],
        title_change: Any | None,
        template: Template,
    ) -> list[ProposedChange]:
        """Apply auto-approved changes to a document.

        Args:
            doc_id: Document ID.
            document: Current document state.
            changes: Field changes to apply.
            title_change: Title change to apply (if any).
            template: Template for additional metadata.

        Returns:
            List of changes that were applied.
        """
        log = logger.bind(doc_id=doc_id)
        log.debug("Applying auto-approved changes", count=len(changes))

        applied: list[ProposedChange] = []
        update = DocumentUpdate()

        # Apply title change
        if title_change and title_change.is_auto_apply:
            update.title = title_change.ai_value
            applied.append(
                ProposedChange(
                    field_name="title",
                    current_value=title_change.existing_value,
                    proposed_value=title_change.ai_value,
                    confidence=title_change.ai_confidence,
                    reason=title_change.reason,
                )
            )

        # Apply custom field changes
        custom_fields: list[CustomFieldValue] = []
        for change in changes:
            field = await self.paperless.get_custom_field_by_name(change.field_name)
            if field:
                custom_fields.append(
                    CustomFieldValue(
                        field=field.id,
                        field_name=field.name,
                        value=change.proposed_value,
                    )
                )
                applied.append(change)
            else:
                log.warning("Custom field not found", field=change.field_name)

        if custom_fields:
            update.custom_fields = custom_fields

        # Apply document type if specified
        if template.document_type:
            doc_type = await self.paperless.get_document_type_by_name(template.document_type)
            if doc_type and document.document_type != doc_type.id:
                update.document_type = doc_type.id

        # Apply correspondent if hinted and not already set
        if template.correspondent_hint and not document.correspondent:
            correspondent = await self.paperless.get_correspondent_by_name(
                template.correspondent_hint
            )
            if correspondent:
                update.correspondent = correspondent.id

        # Apply tags
        tags_to_add = template.tags_add
        if tags_to_add:
            new_tag_ids = list(document.tags)
            for tag_name in tags_to_add:
                tag = await self.paperless.get_tag_by_name(tag_name)
                if tag and tag.id not in new_tag_ids:
                    new_tag_ids.append(tag.id)
            if new_tag_ids != document.tags:
                update.tags = new_tag_ids

        # Patch document if we have changes
        if not update.is_empty():
            await self.paperless.patch_document(doc_id, update)
            log.info("Applied changes", count=len(applied))

        return applied

    async def process_batch(
        self,
        doc_ids: list[int],
        dry_run: bool = False,
    ) -> list[ProcessingResult]:
        """Process multiple documents.

        Args:
            doc_ids: List of document IDs to process.
            dry_run: If True, don't apply changes.

        Returns:
            List of ProcessingResults.
        """
        log = logger.bind(batch_size=len(doc_ids), dry_run=dry_run)
        log.info("Starting batch processing")

        results = []
        for i, doc_id in enumerate(doc_ids):
            log.info(f"Processing {i + 1}/{len(doc_ids)}", doc_id=doc_id)
            try:
                result = await self.process_document(doc_id, dry_run=dry_run)
                results.append(result)
            except Exception as e:
                log.error("Failed to process document", doc_id=doc_id, error=str(e))
                results.append(
                    ProcessingResult(
                        doc_id=doc_id,
                        success=False,
                        error_message=str(e),
                    )
                )

        # Summary
        successful = sum(1 for r in results if r.success)
        log.info(
            "Batch processing complete",
            total=len(doc_ids),
            successful=successful,
            failed=len(doc_ids) - successful,
        )

        return results

    async def process_by_tag(
        self,
        tag_name: str,
        dry_run: bool = False,
    ) -> list[ProcessingResult]:
        """Process all documents with a specific tag.

        Args:
            tag_name: Tag name to filter by.
            dry_run: If True, don't apply changes.

        Returns:
            List of ProcessingResults.
        """
        log = logger.bind(tag=tag_name)
        log.info("Fetching documents by tag")

        documents = await self.paperless.get_documents_by_tag(tag_name)
        doc_ids = [d.id for d in documents]

        log.info(f"Found {len(doc_ids)} documents")
        return await self.process_batch(doc_ids, dry_run=dry_run)

    async def process_by_correspondent(
        self,
        correspondent_name: str,
        dry_run: bool = False,
    ) -> list[ProcessingResult]:
        """Process all documents for a specific correspondent.

        Args:
            correspondent_name: Correspondent name to filter by.
            dry_run: If True, don't apply changes.

        Returns:
            List of ProcessingResults.
        """
        log = logger.bind(correspondent=correspondent_name)
        log.info("Fetching documents by correspondent")

        documents = await self.paperless.get_documents_by_correspondent(correspondent_name)
        doc_ids = [d.id for d in documents]

        log.info(f"Found {len(doc_ids)} documents")
        return await self.process_batch(doc_ids, dry_run=dry_run)
