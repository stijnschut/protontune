"""Settings persistence for ProtonTune."""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from protontune.utils import get_settings_path, ensure_config_dir

_DEFAULT_SETTINGS: dict[str, Any] = {
    "max_backups": 20,
    "min_reports_for_recommendation": 3,
    "confidence_threshold": 0.3,
}


def load_settings() -> dict[str, Any]:
    """Load settings from the YAML file, returning defaults if absent."""
    path = get_settings_path()
    if not path.exists():
        return dict(_DEFAULT_SETTINGS)

    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            merged = dict(_DEFAULT_SETTINGS)
            merged.update(data)
            return merged
    except (yaml.YAMLError, OSError):
        return dict(_DEFAULT_SETTINGS)


def save_settings(settings: dict[str, Any]) -> bool:
    """Persist settings to the YAML file."""
    ensure_config_dir()
    path = get_settings_path()
    try:
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(settings, f, default_flow_style=False, allow_unicode=True)
        return True
    except (yaml.YAMLError, OSError):
        return False


def get_setting(key: str, default=None):
    """Get a single setting value."""
    return load_settings().get(key, default)


def update_setting(key: str, value) -> bool:
    """Update a single setting and persist."""
    settings = load_settings()
    settings[key] = value
    return save_settings(settings)
