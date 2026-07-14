"""Steam configuration management for ProtonTune.

Handles reading and writing Steam configuration files (VDF format),
backup creation, restore, and pruning of old backups.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from protontune.settings import get_setting
from protontune.utils import get_backup_dir, ensure_config_dir

# How many backups to keep by default
_DEFAULT_MAX_BACKUPS = 20


# ─── VDF Helpers (lightweight, for reading known fields) ────────────────────

def _read_vdf_simple(path: Path) -> Optional[str]:
    """Read a VDF file as plain text.

    For full VDF manipulation we use the `vdf` library in write operations.
    This simple read is used for preview/diff purposes.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _find_steam_userdata_dirs() -> list[Path]:
    """Find Steam userdata directories containing localconfig.vdf."""
    dirs: list[Path] = []
    for steam_root in (
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
    ):
        userdata = steam_root / "userdata"
        if userdata.exists():
            for user_dir in userdata.iterdir():
                if user_dir.is_dir():
                    config_vdf = user_dir / "config" / "localconfig.vdf"
                    if config_vdf.exists():
                        dirs.append(user_dir)
    return dirs


def get_config_vdf_path() -> Optional[Path]:
    """Return the path to Steam's config.vdf file."""
    for steam_root in (
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
    ):
        config_vdf = steam_root / "config" / "config.vdf"
        if config_vdf.exists():
            return config_vdf
    return None


def get_first_localconfig_vdf() -> Optional[Path]:
    """Return the first localconfig.vdf found (primary Steam user)."""
    dirs = _find_steam_userdata_dirs()
    if not dirs:
        return None
    return dirs[0] / "config" / "localconfig.vdf"


def get_all_localconfig_paths() -> list[Path]:
    """Return all localconfig.vdf paths across Steam users."""
    return [d / "config" / "localconfig.vdf" for d in _find_steam_userdata_dirs()]


# ─── Backup Management ──────────────────────────────────────────────────────

def create_backup(summary: str) -> Optional[str]:
    """Create a timestamped backup of Steam config files.

    Backs up:
      - config.vdf
      - localconfig.vdf (all users)

    Returns the timestamp string on success, None on failure.
    """
    ensure_config_dir()
    backup_dir = get_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / timestamp
    dest.mkdir(parents=True, exist_ok=True)

    files_backed_up = 0

    # Backup config.vdf
    config_path = get_config_vdf_path()
    if config_path and config_path.exists():
        shutil.copy2(config_path, dest / "config.vdf")
        files_backed_up += 1

    # Backup localconfig.vdf (all users)
    for i, lc_path in enumerate(get_all_localconfig_paths()):
        if lc_path.exists():
            dest_path = dest / f"localconfig_{i}.vdf" if i > 0 else dest / "localconfig.vdf"
            shutil.copy2(lc_path, dest_path)
            files_backed_up += 1

    if files_backed_up == 0:
        return None

    # Write manifest
    manifest = {
        "timestamp": timestamp,
        "summary": summary,
        "files_backed_up": files_backed_up,
        "created_at": datetime.now().isoformat(),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Prune old backups
    _prune_old_backups()

    return timestamp


def list_backups() -> list[dict]:
    """List available backups with metadata, sorted newest-first."""
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return []

    backups: list[dict] = []
    for entry in sorted(backup_dir.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                backups.append({
                    "timestamp": entry.name,
                    "summary": manifest.get("summary", "Unknown"),
                    "created_at": manifest.get("created_at", entry.name),
                    "files_backed_up": manifest.get("files_backed_up", 0),
                })
            except (json.JSONDecodeError, OSError):
                backups.append({
                    "timestamp": entry.name,
                    "summary": "Corrupt manifest",
                    "created_at": entry.name,
                    "files_backed_up": 0,
                })
        else:
            backups.append({
                "timestamp": entry.name,
                "summary": "No manifest (manual backup?)",
                "created_at": entry.name,
                "files_backed_up": 0,
            })

    return backups


def restore_backup(timestamp: str) -> bool:
    """Restore Steam config files from a specific backup.

    Returns True on success, False on failure.
    """
    backup_dir = get_backup_dir() / timestamp
    if not backup_dir.exists():
        return False

    # Double-check Steam isn't running
    from protontune.hardware import is_steam_running
    if is_steam_running():
        return False

    restored = 0

    # Restore config.vdf
    config_backup = backup_dir / "config.vdf"
    if config_backup.exists():
        config_dest = get_config_vdf_path()
        if config_dest:
            shutil.copy2(config_backup, config_dest)
            restored += 1

    # Restore localconfig.vdf files
    for child in backup_dir.iterdir():
        if child.name.startswith("localconfig") and child.suffix == ".vdf":
            # Map back to userdata dirs
            localconfig_paths = get_all_localconfig_paths()
            idx = 0
            if child.name != "localconfig.vdf":
                # Extract index from filename: localconfig_1.vdf -> 1
                try:
                    idx = int(child.stem.split("_")[1])
                except (IndexError, ValueError):
                    continue
            if idx < len(localconfig_paths):
                shutil.copy2(child, localconfig_paths[idx])
                restored += 1

    return restored > 0


def _prune_old_backups() -> None:
    """Remove backups beyond the retention limit."""
    max_backups = get_setting("max_backups", _DEFAULT_MAX_BACKUPS)
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return

    backups = sorted(
        [d for d in backup_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    for old in backups[max_backups:]:
        shutil.rmtree(old, ignore_errors=True)


def get_backup_count() -> int:
    """Return the number of existing backups."""
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return 0
    return len([d for d in backup_dir.iterdir() if d.is_dir()])


# ─── Configuration Injection ───────────────────────────────────────────────

def write_launch_options(app_id: str, options_string: str, localconfig_path: Path) -> bool:
    """Write launch options for a specific game into localconfig.vdf.

    Uses the `vdf` library for proper VDF manipulation.

    Returns True on success, False on failure.
    """
    import vdf

    try:
        with localconfig_path.open("r", encoding="utf-8") as f:
            content = vdf.load(f)
    except Exception:
        return False

    try:
        # Navigate to the UserLocalConfigStore -> Software -> Valve -> Steam -> apps -> {app_id}
        apps = (
            content
            .get("UserLocalConfigStore", {})
            .get("Software", {})
            .get("Valve", {})
            .get("Steam", {})
            .get("apps", {})
        )
    except AttributeError:
        return False

    if app_id not in apps:
        apps[app_id] = {}

    # Set or update LaunchOptions
    apps[app_id]["LaunchOptions"] = options_string

    try:
        with localconfig_path.open("w", encoding="utf-8") as f:
            vdf.dump(content, f)
        return True
    except Exception:
        return False


def write_proton_version(app_id: str, proton_name: str, config_path: Path) -> bool:
    """Force a Proton version for a specific game in Steam's config.vdf.

    Uses direct text manipulation to preserve Steam's exact tab formatting.
    Rewriting the entire file with the vdf library removes tab indentation,
    which causes Steam to ignore the Proton override settings.

    Returns True on success, False on failure.
    """
    import re

    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return False

    if '"CompatToolMapping"' not in text:
        return False

    # Build the entry with real tab characters matching Steam's format
    T = "\t"
    entry_block = (
        f'{T*5}"{app_id}"\n'
        f'{T*5}{{\n'
        f'{T*6}"name"{T*2}"{proton_name}"\n'
        f'{T*6}"config"{T*2}""\n'
        f'{T*6}"priority"{T*2}"250"\n'
        f'{T*5}}}\n'
    )

    # Pattern to match an existing entry for this AppID
    existing_pattern = re.compile(
        rf'{re.escape(T*5)}+"{re.escape(app_id)}"\n'
        rf'{re.escape(T*5)}+\{{\n'
        rf'{re.escape(T*6)}+"name"{re.escape(T*2)}+"[^"]*"\n'
        rf'{re.escape(T*6)}+"config"{re.escape(T*2)}+"[^"]*"\n'
        rf'{re.escape(T*6)}+"priority"{re.escape(T*2)}+"[^"]*"\n'
        rf'{re.escape(T*5)}+\}}\n?'
    )

    if existing_pattern.search(text):
        # Replace existing entry
        text = existing_pattern.sub(entry_block, text, count=1)
    else:
        # Insert before the closing brace of CompatToolMapping
        # Find "CompatToolMapping" section and insert before its closing brace
        marker = f'{T*4}"CompatToolMapping"'
        section_start = text.index(marker)
        # Find the closing brace at the same indent level as the section
        search_from = section_start
        # Skip past the opening brace
        open_brace = text.index('{', search_from)
        search_from = open_brace + 1
        # Find the matching closing brace at indent level 4
        closing_pattern = f'\n{T*4}}}'
        try:
            closing_pos = text.index(closing_pattern, search_from)
        except ValueError:
            # CompatToolMapping may be empty: "CompatToolMapping" { }
            # In that case, insert just before the single closing brace
            closing_pos = text.index('}', open_brace)
        # Insert before closing brace, add newline for cleanliness
        text = text[:closing_pos] + '\n' + entry_block.rstrip('\n') + text[closing_pos:]

    try:
        config_path.write_text(text, encoding="utf-8")
        return True
    except OSError:
        return False


def read_launch_options(app_id: str, localconfig_path: Path) -> Optional[str]:
    """Read current launch options for a specific game."""
    import vdf

    try:
        with localconfig_path.open("r", encoding="utf-8") as f:
            content = vdf.load(f)
    except Exception:
        return None

    try:
        return (
            content
            .get("UserLocalConfigStore", {})
            .get("Software", {})
            .get("Valve", {})
            .get("Steam", {})
            .get("apps", {})
            .get(app_id, {})
            .get("LaunchOptions", "")
        )
    except AttributeError:
        return None


def read_proton_version(app_id: str, config_path: Path) -> Optional[str]:
    """Read the currently forced Proton version for a game."""
    import vdf

    try:
        with config_path.open("r", encoding="utf-8") as f:
            content = vdf.load(f)
    except Exception:
        return None

    try:
        entry = (
            content
            .get("InstallConfigStore", {})
            .get("Software", {})
            .get("Valve", {})
            .get("Steam", {})
            .get("CompatToolMapping", {})
            .get(app_id, {})
        )
        return entry.get("name")
    except AttributeError:
        return None
