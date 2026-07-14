"""Tests for hardware detection module."""

from unittest.mock import patch

from protontune.hardware import detect_hardware, is_steam_running
from protontune.models import GPUVendor


class TestDetectHardware:
    def test_detect_hardware_returns_profile(self):
        """Hardware detection should always return a HardwareProfile."""
        profile = detect_hardware()
        assert profile.gpu_vendor in GPUVendor

    @patch("pathlib.Path.exists", return_value=True)
    @patch("protontune.hardware._detect_gpu_vendor", return_value=GPUVendor.NVIDIA)
    def test_nvidia_detected(self, mock_vendor, mock_exists):
        profile = detect_hardware()
        assert profile.gpu_vendor == GPUVendor.NVIDIA
