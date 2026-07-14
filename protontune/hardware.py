"""Hardware and system detection for ProtonTune."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from protontune.models import GPUVendor, HardwareProfile
from protontune.utils import clean_gpu_model, run_cmd


def detect_hardware() -> HardwareProfile:
    """Detect GPU vendor and model from the local system.

    Uses multiple strategies in order of reliability:
    1. nvidia-smi (Nvidia only)
    2. /proc/driver/nvidia/version (Nvidia fallback)
    3. lspci (any vendor)
    """
    gpu_vendor = _detect_gpu_vendor()
    gpu_model = _detect_gpu_model(gpu_vendor)
    gpu_model_clean = clean_gpu_model(gpu_model) if gpu_model else None

    return HardwareProfile(
        gpu_vendor=gpu_vendor,
        gpu_model=gpu_model,
        gpu_model_clean=gpu_model_clean,
    )


def _detect_gpu_vendor() -> GPUVendor:
    """Identify the GPU vendor by checking for vendor-specific indicators."""
    # Check for Nvidia
    if Path("/proc/driver/nvidia/version").exists():
        return GPUVendor.NVIDIA

    nvidia_smi = run_cmd(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    if nvidia_smi and not nvidia_smi.lower().startswith("nvidia-smi has failed") and "nvidia" in nvidia_smi.lower():
        return GPUVendor.NVIDIA

    # Check via lspci
    lspci_out = run_cmd(["lspci"])
    if lspci_out:
        lower = lspci_out.lower()
        if "nvidia" in lower or "nouveau" in lower:
            return GPUVendor.NVIDIA
        if "amd" in lower or "advanced micro devices" in lower or "radeon" in lower:
            return GPUVendor.AMD
        if "intel" in lower and ("graphics" in lower or "gpu" in lower):
            return GPUVendor.INTEL

    # Check via DRI
    for render_node in Path("/dev/dri").glob("renderD*") if Path("/dev/dri").exists() else []:
        try:
            link = Path(f"/sys/class/drm/{render_node.name}/device/modalias")
            if link.exists():
                text = link.read_text().strip().lower()
                if "nvidia" in text or "10de" in text:
                    return GPUVendor.NVIDIA
                if "amd" in text or "1002" in text:
                    return GPUVendor.AMD
                if "intel" in text or "8086" in text:
                    return GPUVendor.INTEL
        except OSError:
            continue

    return GPUVendor.UNKNOWN


def _detect_gpu_model(gpu_vendor: GPUVendor) -> Optional[str]:
    """Attempt to identify the exact GPU model."""
    if gpu_vendor == GPUVendor.NVIDIA:
        model = run_cmd(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        if model and not model.lower().startswith("nvidia-smi has failed"):
            return model.strip()

    # Fall back to lspci
    lspci_out = run_cmd(["lspci"])
    if lspci_out:
        for line in lspci_out.splitlines():
            lower = line.lower()
            if "vga compatible" in lower or "3d controller" in lower:
                # Extract the model name after the controller type
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    return parts[2].strip()
                return line.strip()

    return None


def is_steam_running() -> bool:
    """Check whether any Steam process is currently running."""
    try:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-x", "steam"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
