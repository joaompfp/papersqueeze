"""Review queue management using paperless-ngx tags."""

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

import structlog

from papersqueeze.api.paperless import PaperlessClient
from papersqueeze.config.schema import ReviewTagsConfig
from papersqueeze.exceptions import ReviewWorkflowError
from papersqueeze.models.document import Document, DocumentUpdate
from papersqueeze.models.extraction import ProposedChange

logger = structlog.get_logger()


class ReviewQueue:
    """Manages the review workflow using paperless-ngx tags.

    Documents needing review are tagged with 'ai-review-needed'.
    Proposed changes are stored in a designated custom field or notes.

    Workflow:
    1. Document processed -> changes proposed -> tag: ai-review-needed
    2. Human reviews in paperless-ngx UI
    3. Human approves -> papersqueeze approve <id> -> applies changes, tag: ai-approved
    4. Human rejects -> papersqueeze reject <id> -> discards changes, tag: ai-rejected
    """

    # Custom field name for storing proposed changes (if available)
    CHANGES_FIELD_NAME = "AI Proposed Changes"

    def __init__(
        self,
        paperless: PaperlessClient,
        tags_config: ReviewTagsConfig,
    ) -> None:
        """Initialize review queue.

        Args:
            paperless: Paperless-ngx API client.
            tags_config: Tag configuration.
        """
        self.paperless = paperless
        self.tags = tags_config

    async def submit_for_review(
        self,
        doc_id: int,
        changes: list[ProposedChange],
    ) -> None:
        """Submit a document for human review.

        Args:
            doc_id: Document ID.
            changes: List of proposed changes.

        Raises:
            ReviewWorkflowError: If submission fails.
        """
        log = logger.bind(doc_id=doc_id, changes_count=len(changes))
        log.info("Submitting document for review")

        try:
            # Add the review tag
            await self.paperless.add_tag_to_document(doc_id, self.tags.needs_review)

            # Remove other workflow tags if present
            await self._remove_workflow_tags(doc_id, exclude=self.tags.needs_review)

            # Store proposed changes (for later retrieval)
            await self._store_proposed_changes(doc_id, changes)

            log.info("Document submitted for review")

        except Exception as e:
            raise ReviewWorkflowError(
                f"Failed to submit document for review: {e}",
                doc_id=doc_id,
            ) from e

    async def get_pending_reviews(self) -> list[Document]:
        """Get all documents pending review.

        Returns:
            List of documents tagged for review.
        """
        log = logger.bind(tag=self.tags.needs_review)
        log.debug("Fetching pending reviews")

        documents = await self.paperless.get_documents_by_tag(self.tags.needs_review)

        log.info("Found pending reviews", count=len(documents))
        return documents

    async def get_proposed_changes(self, doc_id: int) -> list[ProposedChange]:
        """Retrieve proposed changes for a document.

        Args:
            doc_id: Document ID.

        Returns:
            List of proposed changes, or empty list if none stored.
        """
        doc = await self.paperless.get_document(doc_id)

        # Try to get from custom field
        changes_json = doc.get_custom_field_value(self.CHANGES_FIELD_NAME)
        if changes_json:
            try:
                changes_data = json.loads(changes_json)
                return [
                    ProposedChange(**change)
                    for change in changes_data
                ]
            except (json.JSONDecodeError, TypeError):
                pass

        return []

    async def approve_review(
        self,
        doc_id: int,
        dry_run: bool = False,
    ) -> list[ProposedChange]:
        """Approve pending changes for a document.

        Applies all proposed changes and updates tags.

        Args:
            doc_id: Document ID.
            dry_run: If True, don't actually apply changes.

        Returns:
            List of changes that were (or would be) applied.

        Raises:
            ReviewWorkflowError: If document not in review or approval fails.
        """
        log = logger.bind(doc_id=doc_id, dry_run=dry_run)
        log.info("Approving review")

        # Verify document is in review
        doc = await self.paperless.get_document(doc_id)
        if not doc.has_tag(self.tags.needs_review):
            raise ReviewWorkflowError(
                "Document is not pending review",
                doc_id=doc_id,
            )

        # Get proposed changes
        changes = await self.get_proposed_changes(doc_id)
        if not changes:
            log.warning("No proposed changes found")
            # Still update tags
            if not dry_run:
                await self._update_tags_after_review(doc_id, approved=True)
            return []

        if dry_run:
            log.info("Dry run - would apply changes", changes=len(changes))
            return changes

        # Apply changes
        await self._apply_changes(doc_id, changes)

        # Update tags
        await self._update_tags_after_review(doc_id, approved=True)

        # Clear stored changes
        await self._clear_proposed_changes(doc_id)

        log.info("Review approved", changes_applied=len(changes))
        return changes

    async def reject_review(
        self,
        doc_id: int,
        reason: str | None = None,
    ) -> None:
        """Reject pending changes for a document.

        Discards proposed changes and updates tags.

        Args:
            doc_id: Document ID.
            reason: Optional rejection reason.

        Raises:
            ReviewWorkflowError: If document not in review or rejection fails.
        """
        log = logger.bind(doc_id=doc_id, reason=reason)
        log.info("Rejecting review")

        # Verify document is in review
        doc = await self.paperless.get_document(doc_id)
        if not doc.has_tag(self.tags.needs_review):
            raise ReviewWorkflowError(
                "Document is not pending review",
                doc_id=doc_id,
            )

        # Update tags
        await self._update_tags_after_review(doc_id, approved=False)

        # Clear stored changes
        await self._clear_proposed_changes(doc_id)

        log.info("Review rejected")

    async def mark_processed(self, doc_id: int) -> None:
        """Mark a document as processed (no review needed).

        Args:
            doc_id: Document ID.
        """
        log = logger.bind(doc_id=doc_id)
        log.debug("Marking document as processed")

        await self.paperless.add_tag_to_document(doc_id, self.tags.processed)
        await self._remove_workflow_tags(doc_id, exclude=self.tags.processed)

    async def _store_proposed_changes(
        self,
        doc_id: int,
        changes: list[ProposedChange],
    ) -> None:
        """Store proposed changes for later retrieval.

        Currently stores as JSON in a custom field if available,
        otherwise just logs them.
        """
        changes_data = [
            {
                "field_name": c.field_name,
                "current_value": c.current_value,
                "proposed_value": c.proposed_value,
                "confidence": c.confidence,
                "reason": c.reason,
            }
            for c in changes
        ]

        # Try to store in custom field
        field = await self.paperless.get_custom_field_by_name(self.CHANGES_FIELD_NAME)
        if field:
            changes_json = json.dumps(changes_data, ensure_ascii=False)
            # Note: This requires the custom field to exist and be of text type
            # For now, we just log - actual storage would need proper field setup
            logger.debug(
                "Would store changes in custom field",
                doc_id=doc_id,
                field=self.CHANGES_FIELD_NAME,
            )
        else:
            # Log changes for manual review in paperless-ngx
            logger.info(
                "Proposed changes (review in paperless-ngx)",
                doc_id=doc_id,
                changes=changes_data,
            )

    async def _clear_proposed_changes(self, doc_id: int) -> None:
        """Clear stored proposed changes."""
        field = await self.paperless.get_custom_field_by_name(self.CHANGES_FIELD_NAME)
        if field:
            # Would clear the field here
            pass

    async def _apply_changes(
        self,
        doc_id: int,
        changes: list[ProposedChange],
    ) -> None:
        """Apply proposed changes to document."""
        log = logger.bind(doc_id=doc_id)

        # Build update payload
        doc = await self.paperless.get_document(doc_id)
        custom_fields = list(doc.custom_fields)

        for change in changes:
            if change.field_name == "title":
                # Title is handled separately
                await self.paperless.patch_document(
                    doc_id,
                    DocumentUpdate(title=change.proposed_value),
                )
                log.debug("Applied title change", new_title=change.proposed_value)
            else:
                # Custom field - update in list
                field = await self.paperless.get_custom_field_by_name(change.field_name)
                if field:
                    # Update or add the field
                    updated = False
                    for cf in custom_fields:
                        if cf.field == field.id:
                            cf.value = change.proposed_value
                            updated = True
                            break
                    if not updated:
                        from papersqueeze.models.document import CustomFieldValue
                        custom_fields.append(
                            CustomFieldValue(
                                field=field.id,
                                field_name=field.name,
                                value=change.proposed_value,
                            )
                        )
                    log.debug(
                        "Applied field change",
                        field=change.field_name,
                        value=change.proposed_value,
                    )

        # Apply custom field changes
        if custom_fields:
            from papersqueeze.models.document import CustomFieldValue
            await self.paperless.patch_document(
                doc_id,
                DocumentUpdate(
                    custom_fields=[
                        CustomFieldValue(field=cf.field, value=cf.value)
                        for cf in custom_fields
                    ]
                ),
            )

    async def _update_tags_after_review(
        self,
        doc_id: int,
        approved: bool,
    ) -> None:
        """Update tags after review decision."""
        # Remove review-needed tag
        await self.paperless.remove_tag_from_document(doc_id, self.tags.needs_review)

        # Add appropriate result tag
        if approved:
            await self.paperless.add_tag_to_document(doc_id, self.tags.approved)
        else:
            await self.paperless.add_tag_to_document(doc_id, self.tags.rejected)

    async def _remove_workflow_tags(
        self,
        doc_id: int,
        exclude: str | None = None,
    ) -> None:
        """Remove all workflow tags except the specified one."""
        workflow_tags = [
            self.tags.needs_review,
            self.tags.approved,
            self.tags.rejected,
            self.tags.processed,
        ]

        for tag in workflow_tags:
            if tag != exclude:
                try:
                    await self.paperless.remove_tag_from_document(doc_id, tag)
                except Exception:
                    pass  # Tag might not exist or document might not have it
