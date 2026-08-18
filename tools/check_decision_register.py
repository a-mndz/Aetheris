#!/usr/bin/env python3
"""CI check: no Proposed decision older than 90 days without an
explicit extension; every DEC-NNN is unique; status values are valid.

Exit codes:
  0 = pass
  1 = fail (with a list of violations)
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs" / "new"
REGISTER = DOCS / "decision_register.md"

VALID_STATUSES = {"Proposed", "Accepted", "Deferred", "Rejected", "Superseded"}
AGING_LIMIT_DAYS = 90

# Match rows like: | DEC-001 | Async-first runtime ... | Accepted | ... | 2026-07-13 | ...
ROW_RE = re.compile(
    r"^\|\s*(DEC-\d{3})\s*\|\s*(.+?)\s*\|\s*(\w+)\s*\|\s*[^|]*\|\s*(\d{4}-\d{2}-\d{2})\s*\|",
    re.MULTILINE,
)


def _parse_rows() -> list[tuple[str, str, str, str]]:
    """Returns (id, title, status, date_str) tuples."""
    if not REGISTER.is_file():
        return []
    text = REGISTER.read_text(encoding="utf-8")
    return [
        (m.group(1), m.group(2).strip(), m.group(3).strip(), m.group(4).strip())
        for m in ROW_RE.finditer(text)
    ]


def main() -> int:
    failures: list[str] = []

    if not REGISTER.is_file():
        sys.stderr.write(
            f"check_decision_register failed: {REGISTER} does not exist.\n"
        )
        return 1

    rows = _parse_rows()
    today = date.today()

    # 1. Uniqueness check.
    ids = [r[0] for r in rows]
    seen: set[str] = set()
    for did in ids:
        if did in seen:
            failures.append(f"Duplicate decision ID: {did}")
        seen.add(did)

    # 2. Status validation and aging check.
    for did, title, status, date_str in rows:
        if status not in VALID_STATUSES:
            failures.append(
                f"{did} ({title[:40]}...): invalid status '{status}'. "
                f"Valid: {', '.join(sorted(VALID_STATUSES))}"
            )

        if status != "Proposed":
            continue

        try:
            dec_date = date.fromisoformat(date_str)
        except ValueError:
            failures.append(
                f"{did} ({title[:40]}...): invalid date format '{date_str}'. "
                f"Expected YYYY-MM-DD."
            )
            continue

        age = (today - dec_date).days
        if age > AGING_LIMIT_DAYS:
            failures.append(
                f"{did} ({title[:40]}...): Proposed decision is {age} days "
                f"old (limit {AGING_LIMIT_DAYS}). Promote to Accepted, "
                f"Deferred, or Rejected, or extend the deadline with a "
                f"recorded reason."
            )

    # 3. Every decision must have a valid RFC reference or "—" in the RFC column.
    # (Light check: at least the RFC column is present.)
    rfc_col_re = re.compile(
        r"^\|\s*DEC-\d{3}\s*\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|\s*([^\|]+?)\s*\|",
        re.MULTILINE,
    )
    if REGISTER.is_file():
        text = REGISTER.read_text(encoding="utf-8")
        for m in rfc_col_re.finditer(text):
            rfc_val = m.group(1).strip()
            if rfc_val and rfc_val != "—":
                # Just check it looks like RFC-NNN or a comma-separated list.
                parts = [p.strip() for p in rfc_val.split(",")]
                for part in parts:
                    if not re.match(r"RFC-\d{3}$", part):
                        failures.append(
                            f"Row for {m.group(0)[:20]}...: RFC column "
                            f"value '{part}' does not look like RFC-NNN."
                        )

    if failures:
        sys.stderr.write("check_decision_register failed:\n")
        for f in failures:
            sys.stderr.write(f"  - {f}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
