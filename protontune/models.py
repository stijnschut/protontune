"""Data models for ProtonTune."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class GPUVendor(Enum):
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    UNKNOWN = "unknown"


@dataclass
class HardwareProfile:
    """Detected system hardware relevant to Proton configuration."""

    gpu_vendor: GPUVendor
    gpu_model: Optional[str] = None
    gpu_model_clean: Optional[str] = None  # Normalised for matching


@dataclass
class SteamGame:
    """A game detected in the local Steam library."""

    app_id: str
    name: str
    steam_path: str  # Which Steam root it was found under


@dataclass
class ProtonVersion:
    """A locally installed Proton build."""

    name: str  # Display name, e.g. "Proton 9.0", "GE-Proton9-25"
    path: str  # Absolute path to the tool directory
    is_custom: bool  # True for GE-Proton etc., False for official Valve builds
    version: Optional[str] = None  # Parsed version string where available

    def __str__(self) -> str:
        return self.name


@dataclass
class ProtonDBReport:
    """A single ProtonDB community report for a game."""

    app_id: str
    steam_id: str
    reported_at: datetime
    author: str
    system_info: Optional[str] = None
    gpu: Optional[str] = None
    gpu_driver: Optional[str] = None
    os: Optional[str] = None
    proton_version: Optional[str] = None
    proton_build: Optional[str] = None
    rating: Optional[str] = None  # e.g. "Platinum", "Gold", "Silver", "Bronze", "Borked"
    comments: Optional[str] = None
    launch_options: Optional[str] = None  # Raw launch options string from report


@dataclass
class ScoredOption:
    """A single launch option with its computed score."""

    key: str  # e.g. "PROTON_USE_WINED3D"
    value: str  # e.g. "1"
    score: float
    source_report_count: int


@dataclass
class GameRecommendation:
    """Complete recommendation for a single game."""

    game: SteamGame
    proton_version: Optional[ProtonVersion]
    launch_options: list[ScoredOption]
    combined_launch_string: str
    total_reports_scored: int
    score_confidence: float  # 0.0–1.0
    fallback_version: bool  # True if the ideal version was not installed


@dataclass
class BackupManifest:
    """Metadata about a single backup."""

    timestamp: str  # ISO-8601 timestamp used as directory name
    summary: str  # e.g. "12 games changed, 3 Proton versions changed"
    path: str  # Full path to backup directory
    created_at: datetime = field(default_factory=datetime.now)


# Conflict groups — mutually exclusive launch options
CONFLICT_GROUPS: list[set[str]] = [
    # DXVK vs. wined3d — mutually exclusive render paths
    {"PROTON_USE_WINED3D", "DXVK_ASYNC"},
    {"PROTON_USE_WINED3D", "DXVK_HUD"},
    {"PROTON_USE_WINED3D", "DXVK_CONFIG_FILE"},
    # Sync backends — mutually exclusive
    {"PROTON_NO_ESYNC", "PROTON_NO_FSYNC"},
]


