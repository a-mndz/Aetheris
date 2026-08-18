#!/usr/bin/env python3
"""CI check: every RFC-NNN title appears in docs/plan.md §2; every
Related RFCs field in an ADR resolves to a real RFC file.

Exit codes:
  0 = pass
  1 = fail (with a list of broken references)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs" / "new"
PLAN = DOCS / "plan.md"
RFCS_DIR = DOCS / "rfcs"
ADRS_DIR = DOCS / "adrs"

RFC_TITLE_RE = re.compile(r"^#\s+(RFC-\d{3}):\s+(.+)$", re.MULTILINE)
PLAN_TABLE_RE = re.compile(
    r"^\|\s*(RFC-\d{3})\s*\|\s*([^\|]+?)\s*\|", re.MULTILINE
)
ADR_RELATED_RE = re.compile(
    r"^-\s\*\*Related RFCs:\*\*\s*(.+)$", re.MULTILINE
)


def _existing_rfc_ids() -> set[str]:
    if not RFCS_DIR.is_dir():
        return set()
    out: set[str] = set()
    for path in sorted(RFCS_DIR.glob("RFC-*.md")):
        m = re.match(r"RFC-(\d{3})", path.stem)
        if m:
            out.add(f"RFC-{m.group(1)}")
    return out


def _plan_table_rfc_ids() -> set[str]:
    if not PLAN.is_file():
        return set()
    text = PLAN.read_text(encoding="utf-8")
    return {m.group(1) for m in PLAN_TABLE_RE.finditer(text)}


def _adr_related_rfc_refs() -> list[tuple[str, list[str]]]:
    refs: list[tuple[str, list[str]]] = []
    if not ADRS_DIR.is_dir():
        return refs
    for path in sorted(ADRS_DIR.glob("ADR-*.md")):
        text = path.read_text(encoding="utf-8")
        for m in ADR_RELATED_RE.finditer(text):
            raw = m.group(1)
            ids = re.findall(r"RFC-\d{3}", raw)
            refs.append((path.name, ids))
    return refs


def main() -> int:
    failures: list[str] = []

    existing = _existing_rfc_ids()
    plan_table = _plan_table_rfc_ids()

    # 1. Every RFC file must appear in plan.md §2 pointer table.
    for rfc in existing:
        if rfc not in plan_table:
            failures.append(
                f"{rfc} file exists in docs/rfcs/ but is missing from "
                f"docs/plan.md §2 pointer table."
            )

    # 2. Every entry in plan.md §2 must resolve to a real RFC file.
    for rfc in plan_table:
        if rfc not in existing:
            failures.append(
                f"{rfc} listed in docs/plan.md §2 but no file "
                f"docs/rfcs/{rfc}_*.md exists."
            )

    # 3. Every "Related RFCs" field in an ADR must resolve.
    for adr_name, refs in _adr_related_rfc_refs():
        for rfc in refs:
            if rfc not in existing:
                failures.append(
                    f"{adr_name} references {rfc} in its Related RFCs "
                    f"field, but no such RFC file exists."
                )

    if failures:
        sys.stderr.write("check_rfc_index failed:\n")
        for f in failures:
            sys.stderr.write(f"  - {f}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
