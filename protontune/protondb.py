"""ProtonDB data handling for ProtonTune.

Supports multiple data sources:
1. Local data dump: CSV or JSON files placed in the data directory
2. GitHub data dump: automatic download and extraction of the official
   ProtonDB data dump from github.com/bdefore/protondb-data (ODbL-licensed)
"""

from __future__ import annotations

import csv
import json
import os
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from protontune.models import ProtonDBReport
from protontune.utils import ensure_config_dir

# Default data directory within the package
_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# User-data directory where the downloaded dump can be placed
_USER_DATA_DIR = Path.home() / ".config" / "steam-proton-optimizer" / "data"

# GitHub repo for data dumps
_GITHUB_REPO = "https://github.com/bdefore/protondb-data"
_GITHUB_RAW = "https://raw.githubusercontent.com/bdefore/protondb-data/master"
_GITHUB_API = "https://api.github.com/repos/bdefore/protondb-data/git/trees/master?recursive=1"


def _data_dirs() -> list[Path]:
    """Return data directories to search, in priority order."""
    _USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return [_USER_DATA_DIR, _DEFAULT_DATA_DIR]


def find_dump_file() -> Optional[Path]:
    """Locate the ProtonDB data dump file on disk.

    Searches for (in priority order):
    - Extracted report directories (reports/*.json)
    - reports_*.json (the PII-removed flat JSON from the GitHub dump)
    - protondb_data*.csv / protondb_data*.json (legacy flat files)
    - Un-extracted tar.gz archives
    """
    for data_dir in _data_dirs():
        if not data_dir.exists():
            continue

        # 1. Extracted reports/ directory (per-game JSON files)
        reports_dir = data_dir / "reports"
        if reports_dir.exists() and any(reports_dir.iterdir()):
            return reports_dir

        # 2. Manifest from GitHub extraction — check for reports_*.json in data_dir
        manifest = data_dir / ".extracted.json"
        if manifest.exists():
            # Find the extracted flat JSON file
            for pattern in ("reports_*.json",):
                matches = sorted(data_dir.glob(pattern))
                if matches:
                    return matches[-1]
        # 3. Flat CSV/JSON files (legacy)
        for pattern in ("reports_*.json", "protondb_data*.csv",
                        "protondb_data*.json", "protondb-reports*.csv",
                        "protondb-reports*.json"):
            matches = sorted(data_dir.glob(pattern))
            if matches:
                return matches[-1]

        # 4. Un-extracted tar.gz archives
        for pattern in ("*.tar.gz",):
            matches = sorted(data_dir.glob(pattern))
            if matches:
                return matches[-1]

    return None


def get_dump_info() -> Optional[dict]:
    """Return metadata about the found dump file, or None."""
    path = find_dump_file()
    if not path:
        return None

    if path.is_dir():
        info = {
            "path": str(path),
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            "format": "directory (extracted reports)",
        }
        game_count = len(list(path.glob("*.json"))) if path.exists() else 0
        info["games"] = game_count
    else:
        info = {
            "path": str(path),
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        }
    if path.suffix == ".gz":
        info["format"] = "tar.gz (archive — needs extraction)"
    else:
        info["format"] = path.suffix[1:] if path.suffix else "unknown"
        # For the flat reports_*.json format, count games by scanning the file
        if path.name.startswith("reports_") and path.suffix == ".json":
            info["format"] = "flat JSON (PII-removed dump)"
            info["note"] = "Use option 5 to verify or re-download"

    return info


def is_dump_stale(days: int = 90) -> bool:
    """Check whether the local ProtonDB data dump is older than `days`.

    Returns True if the data is missing or older than the threshold.
    """
    path = find_dump_file()
    if not path:
        return True

    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age.days > days


def get_dump_age_days() -> Optional[int]:
    """Return how many days old the ProtonDB dump is, or None if missing."""
    path = find_dump_file()
    if not path:
        return None
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age.days


def load_reports_for_game(app_id: str) -> list[ProtonDBReport]:
    """Load all ProtonDB reports for a specific AppID from the local dump.

    Supports:
    - Extracted reports/ directory (from GitHub tar.gz, per-game JSON files)
    - reports_*.json flat file (the PII-removed GitHub dump)
    - Flat CSV files (legacy)
    - Flat JSON files (legacy)

    Returns an empty list if no dump file is found or the AppID
    has no matching reports.
    """
    dump_path = find_dump_file()
    if not dump_path:
        return []

    # Directory of extracted JSON reports (from tar.gz -> reports/*.json)
    if dump_path.is_dir():
        game_file = dump_path / f"{app_id}.json"
        if game_file.exists():
            return _load_reports_from_json_file(game_file)
        return []

    # Flat file
    suffix = dump_path.suffix.lower()
    if suffix == ".csv":
        return _load_reports_csv(dump_path, app_id)
    elif suffix == ".json":
        # Try the flat reports_*.json format first (GitHub dump)
        if dump_path.name.startswith("reports_"):
            return _load_reports_flat_array(dump_path, app_id)
        return _load_reports_flat_json(dump_path, app_id)
    elif suffix == ".gz":
        return []

    return []


# ─── GitHub Dump Download & Extraction ────────────────────────────────────

def _get_latest_dump_url() -> Optional[str]:
    """Find the URL of the latest ProtonDB data dump on GitHub."""
    dumps = list_available_dumps()
    if dumps:
        return dumps[0]["url"]
    return None


def list_available_dumps() -> list[dict]:
    """List all available data dump archives from the GitHub repo, sorted newest-first."""
    try:
        import urllib.request
        req = urllib.request.Request(_GITHUB_API)
        req.add_header("User-Agent", "ProtonTune/0.1")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        archives = []
        for entry in data.get("tree", []):
            path = entry.get("path", "")
            if path.startswith("reports/") and path.endswith(".tar.gz"):
                name = path.split("/")[-1]
                size_mb = round(entry.get("size", 0) / (1024 * 1024), 2)
                date_key = _parse_dump_date(name)
                archives.append({
                    "name": name,
                    "size_mb": size_mb,
                    "url": f"{_GITHUB_REPO}/raw/master/{path}",
                    "date_key": date_key,
                })

        # Sort by date descending (newest first)
        archives.sort(key=lambda a: a["date_key"], reverse=True)
        return archives
    except Exception:
        return []


_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_dump_date(name: str) -> tuple[int, int, int]:
    """Extract a sortable date tuple (year, month, day) from a dump filename.

    Handles formats like:
        reports_jan1_2026.tar.gz  -> (2026, 1, 1)
        reports_sep5_2020.tar.gz  -> (2020, 9, 5)
        reports_apr3_2024.tar.gz  -> (2024, 4, 3)
    """
    import re
    match = re.match(r"reports_([a-z]+)(\d+)_(\d+)", name)
    if not match:
        return (0, 0, 0)
    month_str = match.group(1).lower()
    day = int(match.group(2))
    year = int(match.group(3))
    month = _MONTH_MAP.get(month_str, 0)
    return (year, month, day)


def download_and_extract(dump_url: str) -> bool:
    """Download a ProtonDB data dump tar.gz and extract it.

    Returns True on success, False on failure.
    """
    ensure_config_dir()
    dest_dir = _USER_DATA_DIR

    try:
        import urllib.request
        import urllib.error

        # Download to temp file
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = tmp.name
            req = urllib.request.Request(dump_url)
            req.add_header("User-Agent", "ProtonTune/0.1")
            with urllib.request.urlopen(req, timeout=300) as response:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    tmp.write(chunk)

        # Extract to data directory
        with tarfile.open(tmp_path, "r:gz") as tar:
            tar.extractall(path=dest_dir, filter="data")

        # Clean up temp file
        os.unlink(tmp_path)

        # Write manifest with all extracted JSON files
        extracted: list[str] = []
        for p in Path(dest_dir).rglob("*.json"):
            if p.name != ".extracted.json":
                extracted.append(p.relative_to(dest_dir).as_posix())
        manifest = {
            "source": dump_url,
            "extracted_at": datetime.now().isoformat(),
            "files": sorted(extracted),
        }
        (dest_dir / ".extracted.json").write_text(
            json.dumps(manifest, indent=2)
        )

        return True

    except (urllib.error.URLError, OSError, tarfile.TarError, json.JSONDecodeError) as e:
        # Clean up temp file on error
        if "tmp_path" in locals():
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False


# ─── JSON Report Parsing ──────────────────────────────────────────────────

def _load_reports_from_json_file(path: Path) -> list[ProtonDBReport]:
    """Load reports from a single game's JSON file (from the extracted dump)."""
    reports: list[ProtonDBReport] = []
    app_id = path.stem  # filename without .json is the AppID

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))

        # Handle both dict and list formats
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            entries = data.get("reports", data.get(app_id, [data]))
            if isinstance(entries, dict):
                entries = [entries]
        else:
            entries = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            report = _parse_json_report(entry, app_id)
            if report:
                reports.append(report)

    except (OSError, json.JSONDecodeError):
        pass

    return reports


def _parse_json_report(entry: dict, app_id: str) -> Optional[ProtonDBReport]:
    """Convert a JSON report dict to a ProtonDBReport.

    Handles both pre-2022 and post-2022 data formats.
    """
    try:
        reported_at = _parse_date(entry.get("reportedAt", "") or entry.get("reported_at", "") or entry.get("date", ""))
    except (ValueError, TypeError):
        reported_at = datetime.min

    # Determine Proton version: pre-2022 uses 'protonVersion', post-2022 uses 'variant'
    proton_version = entry.get("protonVersion") or entry.get("proton_version") or ""
    variant = entry.get("variant", "")

    # In post-2022 format, protonVersion is only present for variant='older'
    # The build name is in 'customProtonVersion' for custom builds
    proton_build = entry.get("customProtonVersion") or entry.get("proton_build", "")

    # Rating/verdict
    rating = entry.get("verdict") or entry.get("rating", "")
    if isinstance(rating, dict):
        rating = rating.get("value", rating.get("label", ""))

    # Launch options (post-2022 field)
    launch_options = entry.get("launchOptions") or entry.get("launch_options") or entry.get("options", "")

    # System info (post-2022: 'specs' object)
    specs = entry.get("specs", {})
    if isinstance(specs, dict):
        gpu = specs.get("gpu", entry.get("gpu", ""))
        gpu_driver = specs.get("gpuDriver", specs.get("gpu_driver", entry.get("gpu_driver", "")))
        os_str = specs.get("os", entry.get("os", ""))
        system_info = json.dumps(specs) if specs else entry.get("system_info", "")
    else:
        gpu = entry.get("gpu", "")
        gpu_driver = entry.get("gpu_driver", "")
        os_str = entry.get("os", "")
        system_info = entry.get("system_info", "")

    # Comments/conclusion (post-2022)
    comments = entry.get("concludingNotes") or entry.get("concluding_notes") or entry.get("comments", "")

    return ProtonDBReport(
        app_id=app_id,
        steam_id=str(entry.get("steamId", entry.get("steam_id", app_id))),
        reported_at=reported_at,
        author=entry.get("author", "anonymous"),
        system_info=system_info or None,
        gpu=gpu or None,
        gpu_driver=gpu_driver or None,
        os=os_str or None,
        proton_version=proton_version or None,
        proton_build=proton_build or None,
        rating=rating or None,
        comments=comments or None,
        launch_options=launch_options or None,
    )


def _load_reports_flat_array(path: Path, app_id: str) -> list[ProtonDBReport]:
    """Load reports from the flat reports_*.json array format (GitHub dump).

    This format is a single JSON array where each entry uses a nested structure:
    {
        "app": {"steam": {"appId": "..."}, "title": "..."},
        "responses": {"verdict": "yes|no", "protonVersion": "...", "launchOptions": "..."},
        "timestamp": 1234567890,
        "systemInfo": {"gpu": "...", "gpuDriver": "...", "os": "..."}
    }
    """
    reports: list[ProtonDBReport] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return []

        for entry in data:
            if not isinstance(entry, dict):
                continue

            # Extract AppID from nested structure
            entry_app_id = (
                entry.get("app", {}).get("steam", {}).get("appId", "")
                or entry.get("steamId", "")
                or ""
            )
            if str(entry_app_id) != app_id:
                continue

            report = _parse_legacy_report(entry, app_id)
            if report:
                reports.append(report)

    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: failed to read ProtonDB dump: {e}")

    return reports


def _parse_legacy_report(entry: dict, app_id: str) -> Optional[ProtonDBReport]:
    """Parse a report entry from the legacy flat JSON array format.

    Handles the structure:
    - app.steam.appId / app.title
    - responses.verdict, responses.protonVersion, responses.launchOptions
    - timestamp (Unix)
    - systemInfo.gpu, systemInfo.gpuDriver, systemInfo.os
    """
    responses = entry.get("responses", {})
    if not isinstance(responses, dict):
        responses = {}

    system_info = entry.get("systemInfo", {})
    if not isinstance(system_info, dict):
        system_info = {}

    # Timestamp: Unix timestamp in seconds
    timestamp = entry.get("timestamp", 0)
    if timestamp:
        try:
            reported_at = datetime.fromtimestamp(int(timestamp))
        except (ValueError, OSError):
            reported_at = datetime.min
    else:
        reported_at = datetime.min

    # Verdict mapping:
    #   "yes", "out the box" -> Gold/Platinum (working)
    #   "no", "is le borked" -> Borked
    #   anything else -> reported as-is
    raw_verdict = responses.get("verdict", "")
    notes = responses.get("notes", {})
    if isinstance(notes, dict):
        notes_verdict = notes.get("verdict", "")
    else:
        notes_verdict = ""

    if raw_verdict == "yes" or raw_verdict == "out the box":
        rating = "Gold"
    elif raw_verdict == "no":
        rating = "Borked"
    elif notes_verdict:
        # Use notes verdict as description (e.g. "is le borked")
        rating = notes_verdict
    else:
        rating = raw_verdict or None

    return ProtonDBReport(
        app_id=app_id,
        steam_id=app_id,
        reported_at=reported_at,
        author=responses.get("author", "anonymous"),
        system_info=json.dumps(system_info) if system_info else None,
        gpu=system_info.get("gpu", "") or None,
        gpu_driver=system_info.get("gpuDriver", "") or None,
        os=system_info.get("os", "") or None,
        proton_version=responses.get("protonVersion", "") or None,
        proton_build=responses.get("customProtonVersion", "") or None,
        rating=rating,
        comments=responses.get("notes", {}).get("extra", "") if isinstance(responses.get("notes"), dict) else None,
        launch_options=responses.get("launchOptions", "") or None,
    )


# ─── Flat File Parsing (legacy CSV/JSON support) ──────────────────────────

def _load_reports_csv(path: Path, app_id: str) -> list[ProtonDBReport]:
    """Load reports from a CSV dump, filtered by AppID."""
    reports: list[ProtonDBReport] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_app_id = (row.get("app_id", "") or row.get("steam_id", "") or "").strip()
                if row_app_id != app_id:
                    continue
                report = _row_to_report(row)
                if report:
                    reports.append(report)
    except (OSError, csv.Error) as e:
        print(f"Warning: failed to read ProtonDB dump: {e}")

    return reports


def _load_reports_flat_json(path: Path, app_id: str) -> list[ProtonDBReport]:
    """Load reports from a flat JSON file, filtered by AppID."""
    reports: list[ProtonDBReport] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))

        if isinstance(data, dict):
            entries = data.get(app_id, [])
        elif isinstance(data, list):
            entries = [e for e in data if str(e.get("app_id", "")) == app_id]
        else:
            entries = []

        for entry in entries:
            report = _parse_json_report(entry, app_id)
            if report:
                reports.append(report)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: failed to read ProtonDB dump: {e}")

    return reports


def _row_to_report(row: dict) -> Optional[ProtonDBReport]:
    """Convert a CSV row dict to a ProtonDBReport."""
    try:
        reported_at = _parse_date(row.get("reported_at", "") or row.get("date", ""))
    except (ValueError, TypeError):
        reported_at = datetime.min

    return ProtonDBReport(
        app_id=row.get("app_id", "") or row.get("steam_id", ""),
        steam_id=row.get("steam_id", "") or row.get("app_id", ""),
        reported_at=reported_at,
        author=row.get("author", "") or "anonymous",
        system_info=row.get("system_info"),
        gpu=row.get("gpu"),
        gpu_driver=row.get("gpu_driver"),
        os=row.get("os"),
        proton_version=row.get("proton_version") or row.get("proton"),
        proton_build=row.get("proton_build"),
        rating=row.get("rating"),
        comments=row.get("comments"),
        launch_options=row.get("launch_options") or row.get("options"),
    )


def _parse_date(date_str: str) -> datetime:
    """Parse a date string in various common formats."""
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    raise ValueError(f"Unrecognised date format: {date_str}")
