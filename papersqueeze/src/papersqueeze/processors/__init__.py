"""Document type processors."""

from papersqueeze.processors.base import BaseProcessor
from papersqueeze.processors.fines import FinesProcessor
from papersqueeze.processors.general import GeneralProcessor
from papersqueeze.processors.tax import TaxProcessor
from papersqueeze.processors.utilities import UtilitiesEnergyProcessor, UtilitiesWaterProcessor

__all__ = [
    "BaseProcessor",
    "FinesProcessor",
    "GeneralProcessor",
    "TaxProcessor",
    "UtilitiesEnergyProcessor",
    "UtilitiesWaterProcessor",
]
