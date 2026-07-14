"""Steam library scanning for ProtonTune.

Detects installed Steam games by reading appmanifest_*.acf files
from all known Steam installation locations, without requiring
Steam to be running.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from protontune.models import SteamGame

# Possible Steam installation roots on a generic Linux desktop
_STEAM_ROOTS = [
    Path.home() / ".steam" / "steam",
    Path.home() / ".local" / "share" / "Steam",
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
    Path.home() / "snap" / "steam" / "common" / ".local" / "share" / "Steam",
]

# Fallback: also check /usr/share/steam (native package installs)
_ALT_STEAM = Path("/usr/share/steam")
if _ALT_STEAM.exists():
    _STEAM_ROOTS.append(_ALT_STEAM)


def find_steam_roots() -> list[Path]:
    """Return all Steam roots that actually exist on this system."""
    return [root for root in _STEAM_ROOTS if root.exists()]


def scan_installed_games() -> list[SteamGame]:
    """Scan all detected Steam installations for installed games.

    Returns a list of SteamGame objects, one per installed game found.
    If a game appears in multiple Steam libraries, each occurrence is
    returned separately (callers should deduplicate by app_id if needed).
    """
    games: list[SteamGame] = []
    seen_ids: set[str] = set()

    for root in find_steam_roots():
        steamapps = root / "steamapps"
        if not steamapps.exists():
            continue

        for manifest in sorted(steamapps.glob("appmanifest_*.acf")):
            app_id = _parse_app_id(manifest.name)
            if app_id is None:
                continue

            name = _parse_acf_field(manifest, "name")
            if not name:
                continue

            if app_id not in seen_ids:
                seen_ids.add(app_id)
                games.append(
                    SteamGame(
                        app_id=app_id,
                        name=name,
                        steam_path=str(root),
                    )
                )

    return sorted(games, key=lambda g: g.name.lower())


def _parse_app_id(filename: str) -> Optional[str]:
    """Extract the numeric AppID from an appmanifest filename.

    Example: 'appmanifest_123456.acf' -> '123456'
    """
    match = re.match(r"appmanifest_(\d+)\.acf$", filename)
    return match.group(1) if match else None


def _parse_acf_field(manifest_path: Path, field: str) -> Optional[str]:
    """Parse a quoted top-level field from a Valve KeyValues (.acf) file.

    This is a minimal parser; for robust VDF parsing the 'vdf' library
    is used elsewhere. This lightweight approach is sufficient for the
    simple flat structure of appmanifest files.
    """
    try:
        content = manifest_path.read_text(errors="replace")
        # Match e.g. "name"\t\t"value"
        pattern = re.compile(
            r'^\s*"' + re.escape(field) + r'"\s+"([^"]*)"',
            re.MULTILINE,
        )
        match = pattern.search(content)
        if match:
            return match.group(1)
    except (OSError, UnicodeDecodeError):
        pass
    return None


def get_game_by_app_id(app_id: str) -> Optional[SteamGame]:
    """Look up a single game by its AppID.

    Returns None if the game is not installed locally.
    """
    for game in scan_installed_games():
        if game.app_id == app_id:
            return game
    return None
