"""Document data models."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CustomFieldValue(BaseModel):
    """A custom field value on a document."""

    field: int = Field(description="Custom field ID in paperless-ngx")
    field_name: str | None = Field(default=None, description="Human-readable field name")
    value: Any = Field(description="Field value")


class Document(BaseModel):
    """A document from paperless-ngx."""

    id: int
    title: str
    content: str = Field(default="", description="OCR text content")
    created: date | None = Field(default=None, description="Document date")
    added: datetime | None = Field(default=None, description="When added to paperless")
    modified: datetime | None = Field(default=None, description="Last modification time")

    # Relationships (IDs)
    correspondent: int | None = Field(default=None)
    document_type: int | None = Field(default=None)
    storage_path: int | None = Field(default=None)
    tags: list[int] = Field(default_factory=list)

    # Resolved names (populated by client)
    correspondent_name: str | None = Field(default=None)
    document_type_name: str | None = Field(default=None)
    tag_names: list[str] = Field(default_factory=list)

    # Custom fields
    custom_fields: list[CustomFieldValue] = Field(default_factory=list)

    # Archive info
    archive_serial_number: int | None = Field(default=None)
    original_file_name: str | None = Field(default=None)

    @field_validator("created", mode="before")
    @classmethod
    def parse_created_date(cls, v: Any) -> date | None:
        """Parse created date from various formats."""
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            # paperless-ngx returns YYYY-MM-DD
            try:
                return date.fromisoformat(v)
            except ValueError:
                return None
        return None

    def get_custom_field_value(self, field_name: str) -> Any | None:
        """Get value of a custom field by name."""
        for cf in self.custom_fields:
            if cf.field_name == field_name:
                return cf.value
        return None

    def get_custom_field_by_id(self, field_id: int) -> Any | None:
        """Get value of a custom field by ID."""
        for cf in self.custom_fields:
            if cf.field == field_id:
                return cf.value
        return None

    def has_tag(self, tag_name: str) -> bool:
        """Check if document has a specific tag by name."""
        return tag_name.lower() in [t.lower() for t in self.tag_names]

    def has_tag_id(self, tag_id: int) -> bool:
        """Check if document has a specific tag by ID."""
        return tag_id in self.tags


class DocumentUpdate(BaseModel):
    """Payload for updating a document in paperless-ngx."""

    title: str | None = Field(default=None)
    created: date | None = Field(default=None)
    correspondent: int | None = Field(default=None)
    document_type: int | None = Field(default=None)
    storage_path: int | None = Field(default=None)
    tags: list[int] | None = Field(default=None)
    custom_fields: list[CustomFieldValue] | None = Field(default=None)
    archive_serial_number: int | None = Field(default=None)

    @field_validator("created", mode="before")
    @classmethod
    def serialize_date(cls, v: Any) -> date | None:
        """Ensure date is properly formatted."""
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, str):
            return date.fromisoformat(v)
        return None

    def to_api_payload(self) -> dict[str, Any]:
        """Convert to paperless-ngx API payload format.

        Only includes non-None fields.
        """
        payload: dict[str, Any] = {}

        if self.title is not None:
            payload["title"] = self.title
        if self.created is not None:
            payload["created"] = self.created.isoformat()
        if self.correspondent is not None:
            payload["correspondent"] = self.correspondent
        if self.document_type is not None:
            payload["document_type"] = self.document_type
        if self.storage_path is not None:
            payload["storage_path"] = self.storage_path
        if self.tags is not None:
            payload["tags"] = self.tags
        if self.archive_serial_number is not None:
            payload["archive_serial_number"] = self.archive_serial_number
        if self.custom_fields is not None:
            payload["custom_fields"] = [
                {"field": cf.field, "value": cf.value}
                for cf in self.custom_fields
            ]

        return payload

    def is_empty(self) -> bool:
        """Check if update has no changes."""
        return all(
            v is None
            for v in [
                self.title,
                self.created,
                self.correspondent,
                self.document_type,
                self.storage_path,
                self.tags,
                self.custom_fields,
                self.archive_serial_number,
            ]
        )


class Correspondent(BaseModel):
    """A correspondent in paperless-ngx."""

    id: int
    name: str
    slug: str | None = Field(default=None)
    match: str | None = Field(default=None)
    matching_algorithm: int | None = Field(default=None)
    is_insensitive: bool = Field(default=True)
    document_count: int = Field(default=0)


class Tag(BaseModel):
    """A tag in paperless-ngx."""

    id: int
    name: str
    slug: str | None = Field(default=None)
    color: str | None = Field(default=None)
    text_color: str | None = Field(default=None)
    is_inbox_tag: bool = Field(default=False)
    document_count: int = Field(default=0)


class DocumentType(BaseModel):
    """A document type in paperless-ngx."""

    id: int
    name: str
    slug: str | None = Field(default=None)
    match: str | None = Field(default=None)
    matching_algorithm: int | None = Field(default=None)
    is_insensitive: bool = Field(default=True)
    document_count: int = Field(default=0)


class CustomField(BaseModel):
    """A custom field definition in paperless-ngx."""

    id: int
    name: str
    data_type: str = Field(description="Type: string, date, integer, monetary, etc.")
