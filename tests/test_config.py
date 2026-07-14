"""Tests for configuration management and backup system."""

from protontune.config import _prune_old_backups, list_backups


class TestBackupListing:
    def test_no_backups_returns_empty(self):
        backups = list_backups()
        # Should not crash when no backups exist
        assert isinstance(backups, list)
