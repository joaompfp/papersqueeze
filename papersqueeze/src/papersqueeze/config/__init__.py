"""Configuration management for PaperSqueeze."""

from papersqueeze.config.loader import load_config
from papersqueeze.config.schema import AppConfig

__all__ = ["AppConfig", "load_config"]
