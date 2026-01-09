# PaperSqueeze — Architecture & Field Mapping

Overview
- PaperSqueeze enriches documents already stored in paperless-ngx by:
  - Classifying document type (fast model)
  - Extracting structured fields (specialist model)
  - Normalizing values and applying or suggesting changes back to paperless-ngx

Entry points
- CLI commands:
  - `process <doc_id>` — process a single document (invoked by post-consume hook)
  - `batch` — process by tag or correspondent
  - `review` — manage human review flow
- Integration: run as post-consume script in paperless-ngx container (see README).

Data flow
1. Read document via paperless API (`/documents/<id>/`) — Document model mirrors API response.
2. Resolve human-readable names for tags, correspondents, document types, and custom fields using the PaperlessClient caches.
3. Send document content to AI (classification then extraction).
4. Normalize extracted values (dates, amounts, identifiers).
5. Perform "smart merge" with existing metadata:
   - Empty + confidence >= confidence_threshold => auto-apply
   - Existing + high-confidence mismatch => queue for review (tag `ai-review-needed`)
   - Successful auto-applies get `ai-processed` tag
6. Persist via paperless API PATCH/POST operations.

Field and tag mapping
- Configured field names (config.fields) are human-readable names that must match the custom field name in paperless-ngx.
- The client resolves NAME -> ID using `/custom_fields/` endpoints (cached) and uses IDs when sending API payloads.
- Tags used by the workflow (configured in TagsConfig) are looked up by name; IDs are used to attach/detach tags to documents.

Caching & performance
- PaperlessClient preloads `/tags/`, `/correspondents/`, `/document_types/`, and `/custom_fields/` into memory for batch operations.
- Call `preload_metadata_cache()` before large batches to avoid per-document lookups.

Where to look in the code
- API client: src/papersqueeze/api/paperless.py — all interactions with paperless-ngx, caches, helpers.
- Models: src/papersqueeze/models/document.py — Document, DocumentUpdate, CustomFieldValue, etc.
- Config: src/papersqueeze/config/schema.py — how fields/tags/templates are declared and accessed.
- Processing orchestration: src/papersqueeze/services/* (processor, merge, review logic).
- CLI: src/papersqueeze/cli.py — entry points for operations.

Recommendations for quick introspection
- Use the PaperlessClient helper `get_custom_field_ids(...)` (added) to map configured names to IDs before applying updates.
- Use `preload_metadata_cache()` before batch runs to reduce API calls.

This file is intentionally concise — for feature-level details, check the processors and services modules that implement classification, extraction, normalization, and merge logic.
