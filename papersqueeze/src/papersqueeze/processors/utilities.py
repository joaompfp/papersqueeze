"""Utilities (energy/water) document processors."""

from papersqueeze.models.document import Document
from papersqueeze.models.extraction import ExtractionResult
from papersqueeze.processors.base import BaseProcessor
from papersqueeze.utils.normalization import normalize_number


class UtilitiesEnergyProcessor(BaseProcessor):
    """Processor for electricity and gas invoices (Iberdrola, EDP, etc.)."""

    @property
    def template_id(self) -> str:
        return "utilities_energy"

    @property
    def description(self) -> str:
        return "Electricity and Gas invoices (Iberdrola, EDP)"

    def post_process(
        self,
        extraction: ExtractionResult,
        document: Document,
    ) -> ExtractionResult:
        """Post-process energy invoice extraction.

        - Ensure consumption is a clean number (no kWh suffix)
        - Format contract power properly
        """
        # Clean up consumption value
        if "consumption_kwh" in extraction.fields:
            field = extraction.fields["consumption_kwh"]
            if field.normalized_value:
                # Ensure no units in the normalized value
                field.normalized_value = normalize_number(field.normalized_value)

        # Normalize contract power format
        if "contract_power" in extraction.fields:
            field = extraction.fields["contract_power"]
            if field.raw_value:
                # Keep the kVA unit in the display value
                raw = field.raw_value.lower()
                if "kva" not in raw and field.normalized_value:
                    # Add kVA if missing
                    field.normalized_value = f"{field.normalized_value} kVA"

        return extraction


class UtilitiesWaterProcessor(BaseProcessor):
    """Processor for water invoices (EPAL, etc.)."""

    @property
    def template_id(self) -> str:
        return "utilities_water"

    @property
    def description(self) -> str:
        return "Water invoices (EPAL)"

    def post_process(
        self,
        extraction: ExtractionResult,
        document: Document,
    ) -> ExtractionResult:
        """Post-process water invoice extraction.

        - Ensure consumption is a clean number (no m3 suffix)
        """
        # Clean up consumption value
        if "consumption_vol" in extraction.fields:
            field = extraction.fields["consumption_vol"]
            if field.normalized_value:
                # Ensure no units in the normalized value
                field.normalized_value = normalize_number(field.normalized_value)

        return extraction
