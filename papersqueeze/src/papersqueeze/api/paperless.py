"""Paperless-ngx API client (synchronous)."""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from papersqueeze.config.schema import PaperlessConfig
from papersqueeze.exceptions import (
    PaperlessAPIError,
    PaperlessAuthError,
    PaperlessNotFoundError,
)

logger = logging.getLogger(__name__)


@dataclass
class Tag:
    """Paperless tag."""
    id: int
    name: str
    slug: str = ""
    color: str = ""


@dataclass
class Correspondent:
    """Paperless correspondent."""
    id: int
    name: str
    slug: str = ""


@dataclass
class DocumentType:
    """Paperless document type."""
    id: int
    name: str
    slug: str = ""


@dataclass
class CustomField:
    """Paperless custom field definition."""
    id: int
    name: str
    data_type: str = "string"


@dataclass
class CustomFieldValue:
    """Custom field value on a document."""
    field_id: int
    field_name: str
    value: Any


@dataclass
class DocumentSnapshot:
    """Immutable snapshot of document state.

    Used for the state pipeline: capture state before processing,
    compare after to generate diffs.
    """
    # Core identifiers
    id: int
    title: str
    original_file_name: str | None

    # Classification
    correspondent_id: int | None
    correspondent_name: str | None
    document_type_id: int | None
    document_type_name: str | None

    # Tags
    tag_ids: list[int]
    tag_names: list[str]

    # Custom fields (field_name -> value)
    custom_fields: dict[str, Any]

    # Content
    content: str
    content_hash: str
    content_length: int

    # Dates
    created: str | None
    added: str | None
    modified: str | None

    # Storage
    storage_path: str | None
    archive_serial_number: int | None

    def get_custom_field(self, field_name: str) -> Any:
        """Get custom field value by name."""
        return self.custom_fields.get(field_name)

    def has_tag(self, tag_name: str) -> bool:
        """Check if document has a tag by name."""
        return tag_name.lower() in [t.lower() for t in self.tag_names]

    def has_tag_id(self, tag_id: int) -> bool:
        """Check if document has a tag by ID."""
        return tag_id in self.tag_ids


@dataclass
class DocumentPatch:
    """Changes to apply to a document."""
    title: str | None = None
    correspondent_id: int | None = None
    document_type_id: int | None = None
    tags_add: list[int] = field(default_factory=list)
    tags_remove: list[int] = field(default_factory=list)
    custom_fields: dict[int, Any] = field(default_factory=dict)  # field_id -> value

    def is_empty(self) -> bool:
        """Check if there are any changes to apply."""
        return (
            self.title is None
            and self.correspondent_id is None
            and self.document_type_id is None
            and not self.tags_add
            and not self.tags_remove
            and not self.custom_fields
        )

    def to_api_payload(self, current_tags: list[int]) -> dict[str, Any]:
        """Convert to Paperless API payload."""
        payload: dict[str, Any] = {}

        if self.title is not None:
            payload["title"] = self.title

        if self.correspondent_id is not None:
            payload["correspondent"] = self.correspondent_id

        if self.document_type_id is not None:
            payload["document_type"] = self.document_type_id

        # Handle tags: compute final tag list
        if self.tags_add or self.tags_remove:
            new_tags = set(current_tags)
            new_tags.update(self.tags_add)
            new_tags.difference_update(self.tags_remove)
            payload["tags"] = list(new_tags)

        # Handle custom fields
        if self.custom_fields:
            payload["custom_fields"] = [
                {"field": field_id, "value": value}
                for field_id, value in self.custom_fields.items()
            ]

        return payload


class PaperlessClient:
    """Synchronous client for paperless-ngx REST API."""

    def __init__(self, config: PaperlessConfig) -> None:
        """Initialize the client."""
        self.config = config
        self.base_url = config.url
        self._client: httpx.Client | None = None

        # Caches for metadata lookups
        self._tag_cache: dict[str, Tag] = {}
        self._correspondent_cache: dict[str, Correspondent] = {}
        self._document_type_cache: dict[str, DocumentType] = {}
        self._custom_field_cache: dict[str, CustomField] = {}

        # ID to name reverse lookups
        self._tag_id_cache: dict[int, str] = {}
        self._correspondent_id_cache: dict[int, str] = {}
        self._document_type_id_cache: dict[int, str] = {}
        self._custom_field_id_cache: dict[int, str] = {}

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Token {self.config.token}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.config.timeout_seconds),
                verify=self.config.verify_ssl,
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            self._client.close()
            self._client = None

    def __enter__(self) -> "PaperlessClient":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    def _handle_response_error(self, response: httpx.Response, context: str) -> None:
        """Handle HTTP error responses."""
        if response.status_code == 401:
            raise PaperlessAuthError("Invalid or expired API token")
        if response.status_code == 404:
            raise PaperlessNotFoundError("resource", context)
        if response.status_code >= 400:
            raise PaperlessAPIError(
                f"API error during {context}",
                status_code=response.status_code,
                response_body=response.text,
            )

    # =========================================================================
    # Document Operations
    # =========================================================================

    def get_document_snapshot(self, doc_id: int) -> DocumentSnapshot:
        """Fetch a document and return an immutable snapshot.

        This is the primary method for the state pipeline.
        """
        logger.debug(f"Fetching document {doc_id}")

        response = self.client.get(f"/documents/{doc_id}/")
        self._handle_response_error(response, f"get document {doc_id}")
        data = response.json()

        # Resolve tag names
        tag_ids = data.get("tags", [])
        tag_names = []
        for tag_id in tag_ids:
            name = self._resolve_tag_name(tag_id)
            if name:
                tag_names.append(name)

        # Resolve correspondent name
        correspondent_id = data.get("correspondent")
        correspondent_name = None
        if correspondent_id:
            correspondent_name = self._resolve_correspondent_name(correspondent_id)

        # Resolve document type name
        document_type_id = data.get("document_type")
        document_type_name = None
        if document_type_id:
            document_type_name = self._resolve_document_type_name(document_type_id)

        # Parse custom fields into dict
        custom_fields: dict[str, Any] = {}
        for cf in data.get("custom_fields", []):
            field_name = self._resolve_custom_field_name(cf["field"])
            if field_name:
                custom_fields[field_name] = cf.get("value")

        # Compute content hash
        content = data.get("content", "")
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        return DocumentSnapshot(
            id=data["id"],
            title=data.get("title", ""),
            original_file_name=data.get("original_file_name"),
            correspondent_id=correspondent_id,
            correspondent_name=correspondent_name,
            document_type_id=document_type_id,
            document_type_name=document_type_name,
            tag_ids=tag_ids,
            tag_names=tag_names,
            custom_fields=custom_fields,
            content=content,
            content_hash=content_hash,
            content_length=len(content),
            created=data.get("created"),
            added=data.get("added"),
            modified=data.get("modified"),
            storage_path=data.get("storage_path"),
            archive_serial_number=data.get("archive_serial_number"),
        )

    def patch_document(self, doc_id: int, patch: DocumentPatch, current_tags: list[int]) -> DocumentSnapshot:
        """Apply a patch to a document and return the new snapshot.

        Args:
            doc_id: Document ID to update.
            patch: Changes to apply.
            current_tags: Current tag IDs (needed for tag operations).

        Returns:
            New document snapshot after the patch.
        """
        payload = patch.to_api_payload(current_tags)
        if not payload:
            logger.debug(f"No changes to apply for document {doc_id}")
            return self.get_document_snapshot(doc_id)

        logger.info(f"Patching document {doc_id}: {list(payload.keys())}")

        response = self.client.patch(f"/documents/{doc_id}/", json=payload)
        self._handle_response_error(response, f"patch document {doc_id}")

        return self.get_document_snapshot(doc_id)

    # =========================================================================
    # Tag Operations
    # =========================================================================

    def get_tag_by_name(self, name: str) -> Tag | None:
        """Find a tag by name (case-insensitive)."""
        cache_key = name.lower()
        if cache_key in self._tag_cache:
            return self._tag_cache[cache_key]

        response = self.client.get("/tags/", params={"name__iexact": name})
        self._handle_response_error(response, f"find tag {name}")

        results = response.json().get("results", [])
        if not results:
            return None

        tag = Tag(
            id=results[0]["id"],
            name=results[0]["name"],
            slug=results[0].get("slug", ""),
            color=results[0].get("color", ""),
        )
        self._tag_cache[cache_key] = tag
        self._tag_id_cache[tag.id] = tag.name
        return tag

    def get_tag_id(self, name: str) -> int | None:
        """Get tag ID by name."""
        tag = self.get_tag_by_name(name)
        return tag.id if tag else None

    def _resolve_tag_name(self, tag_id: int) -> str | None:
        """Resolve tag ID to name."""
        if tag_id in self._tag_id_cache:
            return self._tag_id_cache[tag_id]

        response = self.client.get(f"/tags/{tag_id}/")
        if response.status_code == 404:
            return None
        self._handle_response_error(response, f"get tag {tag_id}")

        data = response.json()
        name = data.get("name")
        if name:
            self._tag_id_cache[tag_id] = name
            self._tag_cache[name.lower()] = Tag(
                id=data["id"],
                name=name,
                slug=data.get("slug", ""),
                color=data.get("color", ""),
            )
        return name

    # =========================================================================
    # Correspondent Operations
    # =========================================================================

    def get_correspondent_by_name(self, name: str) -> Correspondent | None:
        """Find a correspondent by name (case-insensitive)."""
        cache_key = name.lower()
        if cache_key in self._correspondent_cache:
            return self._correspondent_cache[cache_key]

        response = self.client.get("/correspondents/", params={"name__iexact": name})
        self._handle_response_error(response, f"find correspondent {name}")

        results = response.json().get("results", [])
        if not results:
            return None

        correspondent = Correspondent(
            id=results[0]["id"],
            name=results[0]["name"],
            slug=results[0].get("slug", ""),
        )
        self._correspondent_cache[cache_key] = correspondent
        self._correspondent_id_cache[correspondent.id] = correspondent.name
        return correspondent

    def _resolve_correspondent_name(self, correspondent_id: int) -> str | None:
        """Resolve correspondent ID to name."""
        if correspondent_id in self._correspondent_id_cache:
            return self._correspondent_id_cache[correspondent_id]

        response = self.client.get(f"/correspondents/{correspondent_id}/")
        if response.status_code == 404:
            return None
        self._handle_response_error(response, f"get correspondent {correspondent_id}")

        data = response.json()
        name = data.get("name")
        if name:
            self._correspondent_id_cache[correspondent_id] = name
            self._correspondent_cache[name.lower()] = Correspondent(
                id=data["id"],
                name=name,
                slug=data.get("slug", ""),
            )
        return name

    # =========================================================================
    # Document Type Operations
    # =========================================================================

    def get_document_type_by_name(self, name: str) -> DocumentType | None:
        """Find a document type by name (case-insensitive)."""
        cache_key = name.lower()
        if cache_key in self._document_type_cache:
            return self._document_type_cache[cache_key]

        response = self.client.get("/document_types/", params={"name__iexact": name})
        self._handle_response_error(response, f"find document type {name}")

        results = response.json().get("results", [])
        if not results:
            return None

        doc_type = DocumentType(
            id=results[0]["id"],
            name=results[0]["name"],
            slug=results[0].get("slug", ""),
        )
        self._document_type_cache[cache_key] = doc_type
        self._document_type_id_cache[doc_type.id] = doc_type.name
        return doc_type

    def _resolve_document_type_name(self, doc_type_id: int) -> str | None:
        """Resolve document type ID to name."""
        if doc_type_id in self._document_type_id_cache:
            return self._document_type_id_cache[doc_type_id]

        response = self.client.get(f"/document_types/{doc_type_id}/")
        if response.status_code == 404:
            return None
        self._handle_response_error(response, f"get document type {doc_type_id}")

        data = response.json()
        name = data.get("name")
        if name:
            self._document_type_id_cache[doc_type_id] = name
            self._document_type_cache[name.lower()] = DocumentType(
                id=data["id"],
                name=name,
                slug=data.get("slug", ""),
            )
        return name

    # =========================================================================
    # Custom Field Operations
    # =========================================================================

    def get_custom_field_by_name(self, name: str) -> CustomField | None:
        """Find a custom field by name (case-insensitive)."""
        cache_key = name.lower()
        if cache_key in self._custom_field_cache:
            return self._custom_field_cache[cache_key]

        response = self.client.get("/custom_fields/", params={"name__iexact": name})
        self._handle_response_error(response, f"find custom field {name}")

        results = response.json().get("results", [])
        if not results:
            return None

        field = CustomField(
            id=results[0]["id"],
            name=results[0]["name"],
            data_type=results[0].get("data_type", "string"),
        )
        self._custom_field_cache[cache_key] = field
        self._custom_field_id_cache[field.id] = field.name
        return field

    def get_custom_field_id(self, name: str) -> int | None:
        """Get custom field ID by name."""
        field = self.get_custom_field_by_name(name)
        return field.id if field else None

    def _resolve_custom_field_name(self, field_id: int) -> str | None:
        """Resolve custom field ID to name."""
        if field_id in self._custom_field_id_cache:
            return self._custom_field_id_cache[field_id]

        response = self.client.get(f"/custom_fields/{field_id}/")
        if response.status_code == 404:
            return None
        self._handle_response_error(response, f"get custom field {field_id}")

        data = response.json()
        name = data.get("name")
        if name:
            self._custom_field_id_cache[field_id] = name
            self._custom_field_cache[name.lower()] = CustomField(
                id=data["id"],
                name=name,
                data_type=data.get("data_type", "string"),
            )
        return name

    # =========================================================================
    # Cache Operations
    # =========================================================================

    def preload_cache(self) -> None:
        """Preload all metadata into cache for faster lookups."""
        logger.info("Preloading metadata cache")

        def load_all(endpoint: str) -> list[dict]:
            items = []
            page = 1
            while True:
                response = self.client.get(endpoint, params={"page": page})
                if response.status_code != 200:
                    break
                data = response.json()
                items.extend(data.get("results", []))
                if not data.get("next"):
                    break
                page += 1
            return items

        # Load tags
        for item in load_all("/tags/"):
            tag = Tag(id=item["id"], name=item["name"], slug=item.get("slug", ""))
            self._tag_cache[tag.name.lower()] = tag
            self._tag_id_cache[tag.id] = tag.name

        # Load correspondents
        for item in load_all("/correspondents/"):
            corr = Correspondent(id=item["id"], name=item["name"], slug=item.get("slug", ""))
            self._correspondent_cache[corr.name.lower()] = corr
            self._correspondent_id_cache[corr.id] = corr.name

        # Load document types
        for item in load_all("/document_types/"):
            dt = DocumentType(id=item["id"], name=item["name"], slug=item.get("slug", ""))
            self._document_type_cache[dt.name.lower()] = dt
            self._document_type_id_cache[dt.id] = dt.name

        # Load custom fields
        for item in load_all("/custom_fields/"):
            cf = CustomField(id=item["id"], name=item["name"], data_type=item.get("data_type", "string"))
            self._custom_field_cache[cf.name.lower()] = cf
            self._custom_field_id_cache[cf.id] = cf.name

        logger.info(
            f"Cache loaded: {len(self._tag_cache)} tags, "
            f"{len(self._correspondent_cache)} correspondents, "
            f"{len(self._document_type_cache)} doc types, "
            f"{len(self._custom_field_cache)} custom fields"
        )

    def clear_cache(self) -> None:
        """Clear all metadata caches."""
        self._tag_cache.clear()
        self._correspondent_cache.clear()
        self._document_type_cache.clear()
        self._custom_field_cache.clear()
        self._tag_id_cache.clear()
        self._correspondent_id_cache.clear()
        self._document_type_id_cache.clear()
        self._custom_field_id_cache.clear()
