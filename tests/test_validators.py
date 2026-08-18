"""Unit tests for schemas and validators used across Phase 1."""

from __future__ import annotations

import pytest

from core.validators import utc_now


class TestUtcNow:
    def test_returns_timezone_aware(self) -> None:
        ts = utc_now()
        assert ts.tzinfo is not None

    def test_close_to_present(self) -> None:
        from datetime import datetime, timezone
        before = datetime.now(timezone.utc)
        ts = utc_now()
        after = datetime.now(timezone.utc)
        assert before <= ts <= after


class TestValidators:
    def test_validate_non_empty(self) -> None:
        from core.validators import validate_non_empty
        assert validate_non_empty("ok", "name") == "ok"
        with pytest.raises(ValueError):
            validate_non_empty("", "name")

    def test_validate_positive_int(self) -> None:
        from core.validators import validate_non_negative_int, validate_positive_int
        with pytest.raises(ValueError):
            validate_positive_int(0, "n")
        assert validate_non_negative_int(0, "n") == 0
        with pytest.raises(ValueError):
            validate_non_negative_int(-1, "n")
