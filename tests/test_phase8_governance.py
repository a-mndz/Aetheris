"""Phase 8 governance regressions for tools/check_architecture_version.py.

Covers the repaired base-revision version comparison: the checker must
pass when the version is bumped beyond the base, and fail when
watchlisted files change without a bump.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import check_architecture_version as cav  # noqa: E402


class TestWatchlist:
    def test_exact_watchlisted_file_matches(self):
        assert cav._is_watchlisted("orchestrator/scheduler.py")

    def test_windows_separators_normalized(self):
        assert cav._is_watchlisted("orchestrator\\scheduler.py")

    def test_config_directory_prefix_matches(self):
        assert cav._is_watchlisted("config/capabilities/openai.json")

    def test_non_watchlisted_file_ignored(self):
        assert not cav._is_watchlisted("README.md")


class TestVersionBumped:
    def test_equal_versions_are_not_a_bump(self):
        assert not cav._version_bumped("0.1.7", "0.1.7")

    def test_numeric_increase_is_a_bump(self):
        assert cav._version_bumped("0.1.7", "0.1.8")
        assert cav._version_bumped("0.1.7", "0.2.0")
        assert cav._version_bumped("0.9.9", "1.0.0")

    def test_numeric_decrease_is_not_a_bump(self):
        assert not cav._version_bumped("0.2.0", "0.1.9")

    def test_component_count_change_compares_numerically(self):
        assert cav._version_bumped("0.1", "0.1.1")

    def test_non_numeric_versions_fall_back_to_inequality(self):
        assert cav._version_bumped("0.1.7", "0.1.7-rc1")
        assert not cav._version_bumped("0.1.7-rc1", "0.1.7-rc1")


class TestMainFlow:
    def _run(self, monkeypatch, argv, *, base=None, current=None,
             ref_exists=True):
        monkeypatch.setattr(
            cav, "_read_current_version", lambda: current
        )
        monkeypatch.setattr(
            cav, "_read_base_version", lambda ref: base
        )
        monkeypatch.setattr(
            cav,
            "_git",
            lambda args: "ok" if ref_exists and args[0] == "rev-parse" else None,
        )
        monkeypatch.setattr(
            sys, "argv", ["check_architecture_version.py", *argv]
        )
        return cav.main()

    def test_no_watchlisted_changes_pass(self, monkeypatch):
        rc = self._run(
            monkeypatch,
            ["--changed-files", "README.md"],
            base="0.1.7",
            current="0.1.7",
        )
        assert rc == 0

    def test_watchlisted_change_without_bump_fails(self, monkeypatch):
        rc = self._run(
            monkeypatch,
            ["--changed-files", "orchestrator/scheduler.py"],
            base="0.1.7",
            current="0.1.7",
        )
        assert rc == 1

    def test_watchlisted_change_with_bump_passes(self, monkeypatch):
        rc = self._run(
            monkeypatch,
            ["--changed-files", "orchestrator/scheduler.py"],
            base="0.1.7",
            current="0.1.8",
        )
        assert rc == 0

    def test_version_downgrade_fails(self, monkeypatch):
        rc = self._run(
            monkeypatch,
            ["--changed-files", "orchestrator/versioning.py"],
            base="0.1.8",
            current="0.1.7",
        )
        assert rc == 1

    def test_missing_base_ref_fails(self, monkeypatch):
        rc = self._run(
            monkeypatch,
            ["--changed-files", "orchestrator/scheduler.py"],
            base=None,
            current="0.1.8",
            ref_exists=False,
        )
        assert rc == 1

    def test_missing_base_version_file_passes_as_bump(self, monkeypatch):
        rc = self._run(
            monkeypatch,
            ["--changed-files", "orchestrator/scheduler.py"],
            base=None,
            current="0.1.8",
            ref_exists=True,
        )
        assert rc == 0

    def test_missing_current_version_fails(self, monkeypatch):
        rc = self._run(
            monkeypatch,
            ["--changed-files", "orchestrator/scheduler.py"],
            base="0.1.7",
            current=None,
        )
        assert rc == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
