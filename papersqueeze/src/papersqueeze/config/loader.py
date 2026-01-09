"""Configuration loading from YAML files and environment variables."""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from papersqueeze.config.schema import AppConfig, TemplatesConfig
from papersqueeze.exceptions import ConfigurationError

# Default config search paths
DEFAULT_CONFIG_PATHS = [
    Path("config.yaml"),
    Path("papersqueeze/config.yaml"),  # When running from scripts/
    Path("/usr/src/paperless/scripts/papersqueeze/config.yaml"),  # Inside container
    Path.home() / ".config" / "papersqueeze" / "config.yaml",
]

DEFAULT_TEMPLATES_PATHS = [
    Path("templates.yaml"),
    Path("papersqueeze/templates.yaml"),  # When running from scripts/
    Path("/usr/src/paperless/scripts/papersqueeze/templates.yaml"),
    Path.home() / ".config" / "papersqueeze" / "templates.yaml",
]

# Environment variable pattern: ${VAR_NAME} or ${VAR_NAME:default}
ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::([^}]*))?\}")


def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitute environment variables in config values.

    Supports patterns:
    - ${VAR_NAME} - Required, raises error if not set
    - ${VAR_NAME:default} - Optional with default value
    """
    if isinstance(value, str):
        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(2)
            env_value = os.environ.get(var_name)

            if env_value is not None:
                return env_value
            if default is not None:
                return default
            raise ConfigurationError(
                f"Environment variable '{var_name}' is required but not set"
            )

        return ENV_VAR_PATTERN.sub(replacer, value)

    if isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]

    return value


def _find_config_file(
    explicit_path: Path | str | None,
    default_paths: list[Path],
    config_type: str,
) -> Path:
    """Find configuration file from explicit path or search default locations."""
    if explicit_path:
        path = Path(explicit_path)
        if not path.exists():
            raise ConfigurationError(f"{config_type} file not found: {path}")
        return path

    for path in default_paths:
        if path.exists():
            return path

    searched = ", ".join(str(p) for p in default_paths)
    raise ConfigurationError(
        f"No {config_type} file found. Searched: {searched}. "
        f"Create one or set PAPERSQUEEZE_CONFIG environment variable."
    )


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load and parse YAML file."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ConfigurationError(f"Invalid YAML structure in {path}: expected dict")
            return data
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Failed to parse YAML file {path}: {e}") from e
    except OSError as e:
        raise ConfigurationError(f"Failed to read file {path}: {e}") from e


def load_config(config_path: Path | str | None = None) -> AppConfig:
    """Load application configuration from YAML file.

    Args:
        config_path: Explicit path to config file. If None, searches default locations.
                    Can also be set via PAPERSQUEEZE_CONFIG environment variable.

    Returns:
        Validated AppConfig instance.

    Raises:
        ConfigurationError: If config file not found or validation fails.
    """
    # Check environment variable for config path
    env_config_path = os.environ.get("PAPERSQUEEZE_CONFIG")
    if env_config_path and not config_path:
        config_path = env_config_path

    path = _find_config_file(config_path, DEFAULT_CONFIG_PATHS, "Configuration")
    raw_config = _load_yaml_file(path)

    # Substitute environment variables
    try:
        substituted = _substitute_env_vars(raw_config)
    except ConfigurationError:
        raise
    except Exception as e:
        raise ConfigurationError(f"Failed to substitute environment variables: {e}") from e

    # Validate with Pydantic
    try:
        return AppConfig.model_validate(substituted)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            errors.append(f"  - {loc}: {err['msg']}")
        error_list = "\n".join(errors)
        raise ConfigurationError(
            f"Configuration validation failed for {path}:\n{error_list}"
        ) from e


def load_templates(templates_path: Path | str | None = None) -> TemplatesConfig:
    """Load templates configuration from YAML file.

    Args:
        templates_path: Explicit path to templates file. If None, searches default locations.
                       Can also be set via PAPERSQUEEZE_TEMPLATES environment variable.

    Returns:
        Validated TemplatesConfig instance.

    Raises:
        ConfigurationError: If templates file not found or validation fails.
    """
    # Check environment variable for templates path
    env_templates_path = os.environ.get("PAPERSQUEEZE_TEMPLATES")
    if env_templates_path and not templates_path:
        templates_path = env_templates_path

    path = _find_config_file(templates_path, DEFAULT_TEMPLATES_PATHS, "Templates")
    raw_templates = _load_yaml_file(path)

    # Substitute environment variables (rarely needed in templates, but supported)
    try:
        substituted = _substitute_env_vars(raw_templates)
    except ConfigurationError:
        raise
    except Exception as e:
        raise ConfigurationError(f"Failed to substitute environment variables: {e}") from e

    # Validate with Pydantic
    try:
        return TemplatesConfig.model_validate(substituted)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            errors.append(f"  - {loc}: {err['msg']}")
        error_list = "\n".join(errors)
        raise ConfigurationError(
            f"Templates validation failed for {path}:\n{error_list}"
        ) from e


def load_all_config(
    config_path: Path | str | None = None,
    templates_path: Path | str | None = None,
) -> tuple[AppConfig, TemplatesConfig]:
    """Load both application and templates configuration.

    Args:
        config_path: Path to config.yaml
        templates_path: Path to templates.yaml

    Returns:
        Tuple of (AppConfig, TemplatesConfig)

    Raises:
        ConfigurationError: If any configuration fails to load.
    """
    config = load_config(config_path)
    templates = load_templates(templates_path)
    return config, templates
