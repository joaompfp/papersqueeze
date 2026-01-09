"""Data models for PaperSqueeze."""

from papersqueeze.models.document import Document, DocumentUpdate
from papersqueeze.models.extraction import ExtractionResult, ExtractedField

__all__ = ["Document", "DocumentUpdate", "ExtractionResult", "ExtractedField"]
