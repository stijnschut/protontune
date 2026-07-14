"""Tests for the scoring engine."""

from datetime import datetime

from protontune.models import (
    CONFLICT_GROUPS,
    GPUVendor,
    HardwareProfile,
    ProtonDBReport,
    ProtonVersion,
    ScoredOption,
    SteamGame,
)
from protontune.scoring import (
    _combine_launch_options,
    _parse_launch_options,
    _resolve_conflicts,
    score_recommendations,
)


class TestParseLaunchOptions:
    def test_single_option(self):
        result = _parse_launch_options("PROTON_USE_WINED3D=1 %command%")
        assert result == {"PROTON_USE_WINED3D": "1"}

    def test_multiple_options(self):
        result = _parse_launch_options('DXVK_ASYNC=1 WINEDLLOVERRIDES="d3d11=n" %command%')
        assert result["DXVK_ASYNC"] == "1"
        assert result["WINEDLLOVERRIDES"] == "d3d11=n"

    def test_empty_string(self):
        assert _parse_launch_options("") == {}

    def test_none(self):
        assert _parse_launch_options(None) == {}


class TestResolveConflicts:
    def test_removes_conflicting_options(self):
        options = [
            ScoredOption(key="PROTON_USE_WINED3D", value="1", score=0.8, source_report_count=10),
            ScoredOption(key="DXVK_ASYNC", value="1", score=0.9, source_report_count=15),
        ]
        resolved = _resolve_conflicts(options)
        keys = {o.key for o in resolved}
        assert "DXVK_ASYNC" in keys
        assert "PROTON_USE_WINED3D" not in keys

    def test_single_option_in_group(self):
        options = [
            ScoredOption(key="PROTON_USE_WINED3D", value="1", score=0.8, source_report_count=10),
        ]
        resolved = _resolve_conflicts(options)
        assert len(resolved) == 1


class TestCombineLaunchOptions:
    def test_empty(self):
        assert _combine_launch_options([]) == "gamemoderun %command%"

    def test_single(self):
        opts = [ScoredOption(key="DXVK_ASYNC", value="1", score=1.0, source_report_count=1)]
        assert _combine_launch_options(opts) == "DXVK_ASYNC=1 gamemoderun %command%"

    def test_multiple(self):
        opts = [
            ScoredOption(key="DXVK_ASYNC", value="1", score=1.0, source_report_count=1),
            ScoredOption(key="PROTON_NO_ESYNC", value="1", score=0.5, source_report_count=1),
        ]
        result = _combine_launch_options(opts)
        assert "DXVK_ASYNC=1" in result
        assert "PROTON_NO_ESYNC=1" in result
        assert "gamemoderun %command%" in result


class TestScoreRecommendations:
    def test_no_reports_returns_none(self):
        game = SteamGame(app_id="123", name="Test Game", steam_path="/steam")
        hw = HardwareProfile(gpu_vendor=GPUVendor.NVIDIA)
        result = score_recommendations(game, [], hw, [])
        assert result is None

    def test_with_gold_reports(self):
        game = SteamGame(app_id="123", name="Test Game", steam_path="/steam")
        hw = HardwareProfile(gpu_vendor=GPUVendor.NVIDIA)
        reports = [
            ProtonDBReport(
                app_id="123", steam_id="123",
                reported_at=datetime.now(),
                author="tester",
                rating="Gold",
                launch_options="DXVK_ASYNC=1 %command%",
                gpu="NVIDIA GeForce RTX 3080",
            ),
            ProtonDBReport(
                app_id="123", steam_id="123",
                reported_at=datetime.now(),
                author="tester2",
                rating="Platinum",
                launch_options="DXVK_ASYNC=1 %command%",
                gpu="NVIDIA GeForce RTX 3080",
            ),
        ]
        result = score_recommendations(game, reports, hw, [])
        assert result is not None
        assert "DXVK_ASYNC=1" in result.combined_launch_string
        assert "gamemoderun %command%" in result.combined_launch_string
        assert result.game.name == "Test Game"
