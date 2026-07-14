"""Per-game exception management for ProtonTune.

Users can define exceptions — either excluding specific AppIDs from
any changes, or forcing specific launch options — via a YAML file.
The tool never touches games listed under 'exclude' AppIDs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from protontune.utils import get_exceptions_path, ensure_config_dir

# Default empty exceptions structure
_DEFAULT_EXCEPTIONS: dict = {
    "exclude": [],       # List of AppIDs to never modify
    "force_options": {},  # AppID -> forced launch options string
    "force_proton": {},   # AppID -> forced Proton version name
}


def load_exceptions() -> dict:
    """Load the per-game exceptions file, returning a default dict if absent."""
    path = get_exceptions_path()
    if not path.exists():
        return dict(_DEFAULT_EXCEPTIONS)

    import yaml
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            # Ensure all keys exist
            for key in _DEFAULT_EXCEPTIONS:
                data.setdefault(key, _DEFAULT_EXCEPTIONS[key])
            return data
    except (yaml.YAMLError, OSError):
        return dict(_DEFAULT_EXCEPTIONS)


def save_exceptions(data: dict) -> bool:
    """Save the exceptions dict to the YAML file."""
    ensure_config_dir()
    path = get_exceptions_path()

    import yaml
    try:
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        return True
    except (yaml.YAMLError, OSError):
        return False


def is_excluded(app_id: str) -> bool:
    """Check whether an AppID is excluded from any modifications."""
    data = load_exceptions()
    return app_id in data.get("exclude", [])


def get_forced_options(app_id: str) -> Optional[str]:
    """Return the forced launch options string for an AppID, if any."""
    data = load_exceptions()
    return data.get("force_options", {}).get(app_id)


def get_forced_proton(app_id: str) -> Optional[str]:
    """Return the forced Proton version name for an AppID, if any."""
    data = load_exceptions()
    return data.get("force_proton", {}).get(app_id)


def add_exclusion(app_id: str) -> bool:
    """Add an AppID to the exclusion list."""
    data = load_exceptions()
    excludes = data.setdefault("exclude", [])
    if app_id not in excludes:
        excludes.append(app_id)
        return save_exceptions(data)
    return True


def remove_exclusion(app_id: str) -> bool:
    """Remove an AppID from the exclusion list."""
    data = load_exceptions()
    excludes = data.get("exclude", [])
    if app_id in excludes:
        excludes.remove(app_id)
        return save_exceptions(data)
    return True


def set_forced_options(app_id: str, options_string: str) -> bool:
    """Force specific launch options for an AppID."""
    data = load_exceptions()
    force_opts = data.setdefault("force_options", {})
    if options_string:
        force_opts[app_id] = options_string
    else:
        force_opts.pop(app_id, None)
    return save_exceptions(data)


def set_forced_proton(app_id: str, proton_name: str) -> bool:
    """Force a specific Proton version for an AppID."""
    data = load_exceptions()
    force_proton = data.setdefault("force_proton", {})
    if proton_name:
        force_proton[app_id] = proton_name
    else:
        force_proton.pop(app_id, None)
    return save_exceptions(data)
