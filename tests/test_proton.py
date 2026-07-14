"""Tests for Proton version scanning."""

from protontune.proton import _looks_like_proton, find_closest_proton
from protontune.models import ProtonVersion


class TestLooksLikeProton:
    def test_has_proton_script(self, tmp_path):
        pdir = tmp_path / "GE-Proton9-25"
        pdir.mkdir()
        (pdir / "proton").write_text("#!/bin/bash")
        assert _looks_like_proton(pdir)

    def test_no_proton_script(self, tmp_path):
        pdir = tmp_path / "not-proton"
        pdir.mkdir()
        assert not _looks_like_proton(pdir)


class TestFindClosestProton:
    def test_exact_match(self):
        versions = [
            ProtonVersion(name="Proton 9.0", path="/a", is_custom=False),
            ProtonVersion(name="Proton 8.0", path="/b", is_custom=False),
        ]
        result = find_closest_proton(versions, "Proton 9.0")
        assert result is not None
        assert result.name == "Proton 9.0"

    def test_fallback_to_latest_stable(self):
        versions = [
            ProtonVersion(name="Proton 7.0", path="/a", is_custom=False, version="7.0"),
            ProtonVersion(name="Proton 9.0", path="/b", is_custom=False, version="9.0"),
        ]
        result = find_closest_proton(versions, "Proton Experimental")
        assert result is not None
        assert result.name == "Proton 9.0"  # Latest stable

    def test_empty_list_returns_none(self):
        assert find_closest_proton([], "Proton 9.0") is None
