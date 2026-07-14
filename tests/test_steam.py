"""Tests for Steam library scanning."""

from pathlib import Path

from protontune.steam import _parse_app_id, _parse_acf_field


class TestParseAppId:
    def test_standard_manifest(self):
        assert _parse_app_id("appmanifest_123456.acf") == "123456"

    def test_no_match(self):
        assert _parse_app_id("something_else.txt") is None

    def test_empty_string(self):
        assert _parse_app_id("") is None


class TestParseAcfField:
    def test_simple_name_field(self, tmp_path: Path):
        acf = tmp_path / "appmanifest_123.acf"
        acf.write_text('"AppState"\n{\n    "appid"\t\t"123"\n    "name"\t\t"Test Game"\n}')
        assert _parse_acf_field(acf, "name") == "Test Game"

    def test_missing_field_returns_none(self, tmp_path: Path):
        acf = tmp_path / "appmanifest_456.acf"
        acf.write_text('"AppState"\n{\n    "appid"\t\t"456"\n}')
        assert _parse_acf_field(acf, "name") is None

    def test_file_not_found(self):
        from protontune.steam import _parse_acf_field
        result = _parse_acf_field(Path("/nonexistent/file.acf"), "name")
        assert result is None
