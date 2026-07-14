"""Utility functions for ProtonTune."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from protontune.models import GPUVendor


def find_executable(name: str) -> Optional[str]:
    """Check if an executable is available on PATH."""
    return shutil.which(name)


def run_cmd(cmd: list[str], timeout: int = 15) -> Optional[str]:
    """Run a command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def clean_gpu_model(raw: str) -> str:
    """Normalise a GPU model string for matching."""
    s = raw.lower().strip()
    # Remove common noise
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def _config_dir() -> Path:
    """Return the base configuration directory."""
    return Path.home() / ".config" / "steam-proton-optimizer"


def get_backup_dir() -> Path:
    """Return the path to the backups directory, creating it if needed."""
    path = _config_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_exceptions_path() -> Path:
    """Return the path to the per-game exceptions file."""
    return _config_dir() / "exceptions.yaml"


def get_settings_path() -> Path:
    """Return the path to the settings file."""
    return _config_dir() / "settings.yaml"


def ensure_config_dir() -> None:
    """Create the config directory if it doesn't exist."""
    _config_dir().mkdir(parents=True, exist_ok=True)
