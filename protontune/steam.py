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


# Known non-game AppIDs — Steam runtimes, Proton builds, tools, servers, etc.
_NON_GAME_APPIDS: set[str] = {
    # Steam Linux Runtimes
    "1070560",  # Steam Linux Runtime 1.0 (scout)
    "1391110",  # Steam Linux Runtime 2.0 (soldier)
    "1628350",  # Steam Linux Runtime 3.0 (sniper)
    "4183110",  # Steam Linux Runtime 4.0
    # Proton builds
    "1493710",  # Proton Experimental
    "1826330",  # Proton EasyAntiCheat Runtime
    "961740",   # Proton 3.7
    "1054830",  # Proton 4.11
    "1245620",  # Proton 5.0
    "1420170",  # Proton 6.3
    "1883940",  # Proton 7.0
    "2180100",  # Proton 8.0
    "2465220",  # Proton 9.0
    # Redistributables
    "228980",   # Steamworks Common Redistributables
    # VR
    "250820",   # SteamVR
    # SDKs / tools
    "107410",   # Source SDK Base 2013 Multiplayer
    "243750",   # Source SDK Base 2013 Singleplayer
    "346110",   # Source SDK 2007
    "211820",   # Starbound Dedicated Server
    "258550",   # Rust Dedicated Server
    "298740",   # Space Engineers Dedicated Server
    "4020",     # Win32 Dedicated Server
    # Other tools
    "223770",   # Portal 2 Authoring Tools
    "246760",   # Counter-Strike: Global Offensive - SDK
    "207690",   # Counter-Strike: Global Offensive Dedicated Server
    "222730",   # Dota 2 Workshop Tools
    # Steam streaming / link
    "353370",   # Steam Link
    "1466050",  # Steam Remote Play
}

# Name patterns that indicate a non-game entry (case-insensitive)
_NON_GAME_NAME_PATTERNS = (
    "steam linux runtime",
    "steamworks",
    "proton",
    "redistributable",
    "dedicated server",
    "sdk",
    "workshop tool",
    "authoring tool",
    "steamvr",
    "steam link",
    "steam streaming",
    "remote play",
)


def is_actual_game_name(name: str) -> bool:
    """Check whether a game name looks like an actual game, not a Steam tool."""
    lower = name.lower()
    return not any(pattern in lower for pattern in _NON_GAME_NAME_PATTERNS)


def scan_installed_games() -> list[SteamGame]:
    """Scan all detected Steam installations for installed games.

    Filters out known non-game entries (Steam runtimes, Proton builds,
    redistributables, etc.) automatically.

    Returns a list of SteamGame objects, one per installed game found.
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

            # Filter out non-game entries
            if app_id in _NON_GAME_APPIDS or not is_actual_game_name(name):
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
