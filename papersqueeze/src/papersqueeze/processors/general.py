"""General/fallback document processor."""

from papersqueeze.processors.base import BaseProcessor


class GeneralProcessor(BaseProcessor):
    """Processor for general invoices and receipts.

    This is the fallback processor used when no specific template matches.
    """

    @property
    def template_id(self) -> str:
        return "fallback_general"

    @property
    def description(self) -> str:
        return "General invoices and receipts"
