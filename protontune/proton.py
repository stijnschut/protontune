"""Local Proton installation detection for ProtonTune.

Scans the filesystem for installed Proton builds — both official
Valve releases and custom builds (e.g. GE-Proton) — without
requiring Steam to be running.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from protontune.models import ProtonVersion
from protontune.steam import find_steam_roots


def scan_proton_versions() -> list[ProtonVersion]:
    """Scan all known locations for installed Proton versions.

    Checks two locations within each detected Steam root:
    1. steamapps/common/Proton */ — official Valve builds
    2. compatibilitytools.d/ — custom builds (GE-Proton, Proton-GE, etc.)
    """
    versions: list[ProtonVersion] = []
    seen_names: set[str] = set()

    for root in find_steam_roots():
        # Official builds: steamapps/common/Proton <version>/
        common_dir = root / "steamapps" / "common"
        if common_dir.exists():
            for entry in common_dir.iterdir():
                if entry.name.startswith("Proton ") and entry.is_dir():
                    name = entry.name
                    if name not in seen_names:
                        seen_names.add(name)
                        versions.append(
                            ProtonVersion(
                                name=name,
                                path=str(entry),
                                is_custom=False,
                                version=_parse_proton_version(name),
                                internal_name=_to_internal_name(name, is_custom=False),
                            )
                        )

        # Custom builds: compatibilitytools.d/
        compat_dir = root / "compatibilitytools.d"
        if compat_dir.exists():
            for entry in compat_dir.iterdir():
                if entry.is_dir() and _looks_like_proton(entry):
                    name = entry.name
                    if name not in seen_names:
                        seen_names.add(name)
                        versions.append(
                            ProtonVersion(
                                name=name,
                                path=str(entry),
                                is_custom=True,
                                version=_parse_proton_version(name),
                                internal_name=_to_internal_name(name, is_custom=True),
                            )
                        )

    # Sort: official builds first, then custom, alphabetically within each group
    versions.sort(key=lambda v: (not v.is_custom, v.name.lower()))
    return versions


def _to_internal_name(name: str, is_custom: bool) -> str:
    """Derive the Steam internal name from a Proton build's display name.

    Official builds:  "Proton - Experimental" -> "proton_experimental"
    Custom builds:    "GE-Proton11-1"        -> "GE-Proton11-1"
    """
    if is_custom:
        # Custom builds use their directory name as-is
        return name
    # Official: lowercase, replace " - " and spaces with underscores
    return name.lower().replace(" - ", "_").replace(" ", "_")


def _parse_proton_version(name: str) -> Optional[str]:
    """Attempt to extract a semver-ish version from a Proton build name.

    Examples:
        'Proton 9.0' -> '9.0'
        'GE-Proton9-25' -> '9-25'
        'Proton Experimental' -> None
    """
    match = re.search(r"(\d[\d.]*-?\d*)", name)
    return match.group(1) if match else None


def _looks_like_proton(dir_path: Path) -> bool:
    """Heuristic: check if a directory looks like a Proton build.

    Proton builds typically contain a 'proton' script and a
    'version' file or 'dist/' directory.
    """
    proton_script = dir_path / "proton"
    if proton_script.exists() and proton_script.is_file():
        return True
    # Fallback: check for a version file or dist directory
    if (dir_path / "version").exists() or (dir_path / "dist").is_dir():
        return True
    return False


def get_proton_by_name(name: str) -> Optional[ProtonVersion]:
    """Find a specific Proton version by display name."""
    for pv in scan_proton_versions():
        if pv.name == name:
            return pv
    return None


def _sort_key_version(v: ProtonVersion) -> tuple[int, ...]:
    """Generate a sort key for version strings, handling dotted numeric versions.

    'Proton 9.0' -> (9, 0), 'Proton 7.0' -> (7, 0), 'GE-Proton9-25' -> (9, 25).
    Falls back to parsing the name if the version field is not set.
    Non-numeric versions sort before numeric ones.
    """
    ver = v.version or _parse_proton_version(v.name)
    if not ver:
        return (-1,)
    parts = re.split(r"[.\-]", ver)
    result: list[int] = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(-1)
    return tuple(result)


def find_closest_proton(versions: list[ProtonVersion], target_name: str) -> Optional[ProtonVersion]:
    """Find the closest installed Proton version to a target name.

    Falls back to the latest stable Proton, then to any available
    custom build, then to the first available version.
    """
    if not versions:
        return None

    # Exact match
    for v in versions:
        if v.name.lower() == target_name.lower():
            return v

    # Contains match
    for v in versions:
        if target_name.lower() in v.name.lower() or v.name.lower() in target_name.lower():
            return v

    # Fallback: latest stable Proton (numeric sort)
    stable = sorted(
        [v for v in versions if not v.is_custom],
        key=_sort_key_version,
        reverse=True,
    )
    if stable:
        return stable[0]

    # Fallback: latest custom build
    custom = sorted(
        [v for v in versions if v.is_custom],
        key=_sort_key_version,
        reverse=True,
    )
    if custom:
        return custom[0]

    return versions[0]
