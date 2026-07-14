"""Launch option scoring engine for ProtonTune.

Scores individual launch options from ProtonDB reports using a
frequency-based model. Only options that appear in a meaningful
percentage of reports are included. Gamemoderun is always appended.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from protontune.models import (
    CONFLICT_GROUPS,
    GPUVendor,
    GameRecommendation,
    HardwareProfile,
    ProtonDBReport,
    ProtonVersion,
    ScoredOption,
    SteamGame,
)
from protontune.proton import find_closest_proton

# Minimum frequency threshold: an option must appear in at least this
# fraction of high-quality reports to be included.
_MIN_FREQUENCY = 0.03  # 3%

# Default trailer appended to all launch strings
_DEFAULT_TRAILER = "gamemoderun %command%"

# Options that are merely cosmetic/monitoring, not game-fixing.
# Filtered out even if they score highly.
_COSMETIC_PREFIXES: set[str] = {
    "MANGOHUD",
    "MANGO_HUD",
    "MANGOHUD_CONFIG",
    "MANGOHUD_CONFIGFILE",
    "OBS_VKCAPTURE",
    "ENABLE_VKBASALT",
    "ENABLE_VKSUMI",
    "VKBASALT_CONFIG_FILE",
    "GAMEMODERUNEXEC",
}

# Option prefixes that are hardware-specific, user-specific, or otherwise
# noisy. These are filtered out because they don't generalise.
_NOISE_PREFIXES: set[str] = {
    # GPU / driver paths
    "DXVK_FILTER_DEVICE_NAME", "VK_ICD_FILENAMES", "VK_DRIVER_FILES",
    "VK_LOADER_DRIVERS_SELECT", "VK_LOADER_LAYERS_ENABLE",
    "AMD_VULKAN_ICD", "RADV_PERFTEST", "RADV_DEBUG",
    "RADV_FORCE_PSTATE_PEAK", "RADV_GFX12_HIZ_WA",
    "RADV_ABSOLUTE_DEPTH_BIAS", "RADV_NO_DYNAMIC_BOUNDS",
    "MESA_LOADER_DRIVER_OVERRIDE", "MESA_VK_WSI_PRESENT_MODE",
    "MESA_VK_DEVICE_SELECT", "MESA_GLTHREAD", "MESA_GLSL_CACHE_DISABLE",
    "MESA_SHADER_CACHE_MAX_SIZE", "MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE",
    "DRI_PRIME", "DISABLE_VK_LAYER",
    # Nvidia low-level
    "__GL_SHADER_DISK_CACHE", "__GL_SHADER_DISK_CACHE_SKIP_CLEANUP",
    "__GL_SHADER_DISK_CACHE_SIZE", "__GL_SHADER_DISK_CACHE_PATH",
    "__GL_THREADED_OPTIMIZATIONS", "__GLX_VENDOR_LIBRARY_NAME",
    "__NV_PRIME_RENDER_OFFLOAD", "__VK_LAYER_NV_OPTIMUS",
    "__GL_GSYNC_ALLOWED", "__GL_SYNC_TO_VBLANK", "__GL_MAXFRAMESALLOWED",
    "NVPRESENT_ENABLE_SMOOTH_MOTION",
    # Library preloading
    "LD_PRELOAD", "LD_BIND_NOW",
    # Vulkan layers
    "VK_INSTANCE_LAYERS", "VK_LAYER_PATH",
    "DISABLE_VK_LAYER_VALVE_STEAM_FOSSILIZE",
    "DISABLE_VK_LAYER_VALVE_STEAM_OVERLAY",
    # Steam Deck specific
    "STEAMDECK", "GAMESCOPE_FRAME_DURATION", "ENABLE_GAMESCOPE_WSI",
    # Display environment
    "WAYLAND_DISPLAY", "DISPLAY", "AQ_NO_MODIFIERS", "XCURSOR_SIZE",
    # Audio
    "PULSE_LATENCY_MSEC", "PIPEWIRE_LATENCY", "WINEPULSE_FAST_POLLING",
    "WINEALSAOUTPUT", "SDL_AUDIO_DRIVER", "SDL_AUDIODRIVER", "SDLAUDIODRIVER",
    # SDL video
    "SDL_VIDEO_DRIVER", "SDL_VIDEODRIVER", "SDLVIDEODRIVER",
    "SDL_VIDEO_WAYLAND_ALLOW_LIBDECOR", "SDL_VIDEO_WAYLAND_SCALE_TO_DISPLAY",
    "SDL_VIDEO_WAYLAND_MODE_SCALING", "SDL_VIDEO_WAYLAND_ALLOW_TEARING",
    "SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "SDL_MOUSE_RELATIVE_MODE_WARP",
    "SDL_IM_MODULE", "SDL_GAMECONTROLLER_ALLOW_BACKGROUND_INPUT",
    # Keyboard / locale
    "XKB_DEFAULT_LAYOUT", "XKB_DEFAULT_OPTIONS", "XKBLAYOUT",
    "QT_IM_MODULE", "XMODIFIERS", "LANG", "HOST_LC_ALL", "XDG_SESSION_TYPE",
    # Memory / CPU limits
    "MAXMEM", "MAXVRAM", "WINE_CPU_TOPOLOGY", "GAMEID",
    # Game-specific environment paths
    "WINEPREFIX", "PROTONPATH", "STEAMAPPID", "STEAMGAMEID",
    "STEAMOVERLAYGAMEID", "STEAM_COMPAT_CLIENT_INSTALL_PATH",
    "STEAM_COMPAT_DATA_PATH", "PROTONPREFIX", "UNSET",
    # Debug — not needed in final config
    "PROTON_LOG", "PROTON_DUMP_DEBUG_COMMANDS",
    # Frame rate limits — personal preference
    "DXVK_FRAME_RATE", "VKD3D_FRAME_RATE", "FPS_LIMIT",
    # Path/manual overrides that don't generalise
    "DXVK_CONFIG", "VKD3D_FILTER_DEVICE_NAME", "NODEVICE_SELECT",
    "FORCE_VK_VENDOR", "CL_FORCEPRELOAD", "VBLANK_MODE",
    "PROTON_WAYLAND_MONITOR", "PYROVEIL", "PYROVEIL_CONFIG",
    "PSOCOMPILEMODE", "VK_KHR_PRESENT_ID", "VK_KHR_PRESENT_WAIT",
    "DXVK_USE_PIPECOMPILER", "DXVK_PRESENT_MODE",
    "PROTON_OPTISCALER_NAME", "DXVK_NVAPI_DRS_SETTINGS",
    "PROTON_DLSS_INDICATOR", "PROTON_NVIDIA_LIBS", "PROTON_HIDE_INTEL_GPU",
    "PROTON_CONFIG", "DXVK_NVAPI_ALLOW_OTHER_DRIVERS", "DXVK_ENABLE_NVAPI",
    "PROTON_DISABLE_NVAPI", "PROTON_FORCE_LARGE_ADDRESS_AWARE",
    "WINE_LARGE_ADDRESS_AWARE", "GRAPHICSADAPTER", "SOUND", "CULTURE",
    "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "MALLOC",
    "VKD3D_SHADER_MODEL", "PROTON_DXVK_LOWLATENCY",
    "PROTON_LOCAL_SHADER_CACHE", "PROTON_ENABLED_HDR",
    "PROTON_HIDE_NVIDIA_GPU", "PROTON_FORCE_NVAPI",
    "PROTON_USE_EAC_LINUX", "PROTON_NO_D3D11",
    "FSR4_WATERMARK", "DXVK_NUM_THREADS",
    "WINE_FULLSCREEN_INTEGER_SCALING", "PROTON_FSR4_RDNA3_UPGRADE",
    "WINENTSYNC", "PROTON_FSR_UPGRADE", "ENABLE_LAYER_MESA_ANTI_LAG",
    "PROTON_XESS_UPGRADE", "PROTON_USER_OPTISCALER", "PROTON_USE_OPTISCALER",
    "PROTON_USE_D9VK", "PROTON_USE_WOW64", "PROTON_NO_STEAMINPUT",
    "PROTON_USE_WIN10", "PROTON_NO_WM_DECORATION", "PROTON_NVAPI_VKREFLEX",
    "INTEL_DEBUG", "VKD3D_FEATURE_LEVEL", "PROTON_FSR4_UPGRADE",
    "PROTON_DLSS_UPGRADE", "PROTON_ENABLE_NGX_UPDATER",
    "VKD3D_DISABLE_EXTENSIONS", "LOW_LATENCY_LAYER",
    "LOW_LATENCY_LAYER_REFLEX", "LOW_LATENCY_LAYER_SPOOF_NVIDIA",
    "WAYLANDDRV_PRIMARY_MONITOR", "WAYLANDDRV_RAWINPUT",
    "PROTON_PRIORITY_HIGH", "PROTON_NO_NTSYNC", "STEAM_RUNTIME",
    "ENABLE_HDR_WSI", "PROTON_ENABLE_HIDRAW",
    "WINE_FULLSCREEN_FSR_STRENGTH",
    "PROTON_PREFER_SDL",
    "PROTON_USE_WINED3D",
}

# Options that are inherently valuable for Proton gaming.
# These are kept if they meet the minimum frequency, while cosmetic
# options like MANGOHUD are excluded.
_HIGH_VALUE_OPTIONS: set[str] = {
    "PROTON_USE_NTSYNC",
    "PROTON_NO_ESYNC",
    "DXVK_ASYNC",
}


def score_recommendations(
    game: SteamGame,
    reports: list[ProtonDBReport],
    hardware: HardwareProfile,
    available_proton: list[ProtonVersion],
) -> Optional[GameRecommendation]:
    """Score launch options for a single game and produce a recommendation."""
    if not reports:
        return None

    now = datetime.now()
    high_quality_reports = [
        r for r in reports
        if r.rating and r.rating.lower() in ("platinum", "gold")
    ]
    if not high_quality_reports:
        high_quality_reports = reports

    total = len(high_quality_reports)
    if total == 0:
        return None

    # Count raw frequency of each option value
    freq: dict[str, dict[str, int]] = {}  # key -> value -> count

    for report in high_quality_reports:
        options = _parse_launch_options(report.launch_options)
        if not options:
            continue

        for key, value in options.items():
            if key not in freq:
                freq[key] = {}
            freq[key][value] = freq[key].get(value, 0) + 1

    if not freq:
        return None

    # Build scored options
    scored: list[ScoredOption] = []
    for key, values in freq.items():
        for value, count in values.items():
            frequency = count / total
            # Only keep options above the frequency threshold
            if frequency >= _MIN_FREQUENCY:
                scored.append(
                    ScoredOption(
                        key=key,
                        value=value,
                        score=frequency,
                        source_report_count=count,
                    )
                )

    if not scored:
        return None

    # Sort by frequency descending
    scored.sort(key=lambda o: o.score, reverse=True)

    # Resolve conflicts (mutually exclusive options)
    scored = _resolve_conflicts(scored)

    # Filter out noise and cosmetic options
    scored = [o for o in scored if not _is_noise(o) and not _is_cosmetic(o)]

    proton_version = _recommend_proton(reports, available_proton)
    combined = _combine_launch_options(scored)

    confidence = min(1.0, total / 50.0)

    return GameRecommendation(
        game=game,
        proton_version=proton_version,
        launch_options=scored,
        combined_launch_string=combined,
        total_reports_scored=total,
        score_confidence=confidence,
        fallback_version=(
            proton_version is not None
            and proton_version.name != _most_reported_proton(reports)
        ),
    )


def _parse_launch_options(options_str: Optional[str]) -> dict[str, str]:
    """Parse a launch options string into a dict of key=value pairs."""
    if not options_str or not options_str.strip():
        return {}

    text = re.sub(r"%command%", "", options_str, flags=re.IGNORECASE).strip()

    options: dict[str, str] = {}
    pattern = re.compile(
        r'(?P<key>[A-Z_][A-Z0-9_]*)\s*=\s*'
        r'(?P<val>"(?:[^"\\]|\\.)*"|[^\s"\']+)',
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        key = match.group("key").upper()
        value = match.group("val").strip('"')
        options[key] = value
    return options


def _resolve_conflicts(options: list[ScoredOption]) -> list[ScoredOption]:
    kept: list[ScoredOption] = []
    removed_keys: set[str] = set()

    for conflict_group in CONFLICT_GROUPS:
        group_options = [o for o in options if o.key in conflict_group]
        if len(group_options) <= 1:
            continue
        best = max(group_options, key=lambda o: o.score)
        for o in group_options:
            if o.key != best.key:
                removed_keys.add(o.key)

    for option in options:
        if option.key not in removed_keys:
            kept.append(option)
    return kept


def _is_noise(option: ScoredOption) -> bool:
    return option.key in _NOISE_PREFIXES


def _is_cosmetic(option: ScoredOption) -> bool:
    return option.key in _COSMETIC_PREFIXES


def _combine_launch_options(options: list[ScoredOption]) -> str:
    """Combine scored options into a launch options string.

    Gamemoderun %command% is always appended at the end and does not
    count toward any limit.
    """
    if not options:
        return _DEFAULT_TRAILER

    parts = [f"{o.key}={o.value}" for o in options]
    parts.append(_DEFAULT_TRAILER)
    return " ".join(parts)


def _recommend_proton(
    reports: list[ProtonDBReport],
    available: list[ProtonVersion],
) -> Optional[ProtonVersion]:
    most_reported = _most_reported_proton(reports)
    if most_reported:
        return find_closest_proton(available, most_reported)
    return None


def _most_reported_proton(reports: list[ProtonDBReport]) -> Optional[str]:
    version_counts: dict[str, int] = {}
    for r in reports:
        if r.rating and r.rating.lower() in ("platinum", "gold"):
            key = r.proton_build or r.proton_version or "unknown"
            version_counts[key] = version_counts.get(key, 0) + 1
    if not version_counts:
        return None
    return max(version_counts, key=version_counts.get)
