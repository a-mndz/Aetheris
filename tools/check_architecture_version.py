#!/usr/bin/env python3
"""CI check: hard fail if any file in the architectural watchlist is
changed without a corresponding bump in orchestrator/versioning.py.

The check compares the architecture_version at a git base revision with
the version in the working tree. If watchlisted files changed and the
version is unchanged (or lower), the check fails.

Usage:
    # Derive changed files and base version from git:
    python tools/check_architecture_version.py --base-ref origin/main

    # Provide the changed-file list explicitly (base version still
    # comes from git via --base-ref, default origin/main):
    git diff --name-only origin/main | python tools/check_architecture_version.py --stdin
    python tools/check_architecture_version.py --changed-files file1.py file2.py

Exit codes:
  0 = pass (no architectural files changed, or version was bumped)
  1 = fail (architectural files changed without version bump, or the
      base/current version could not be determined)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE_REL = "orchestrator/versioning.py"
VERSION_FILE = REPO_ROOT / VERSION_FILE_REL

# Architectural watchlist — files whose change requires an
# architecture_version bump.  Paths are relative to REPO_ROOT.
WATCHLIST_GLOBS: list[str] = [
    "orchestrator/planner.py",
    "orchestrator/strategic_planner.py",
    "orchestrator/execution_planner.py",
    "orchestrator/scheduler.py",
    "orchestrator/resource_manager.py",
    "orchestrator/meta_reasoner.py",
    "orchestrator/routing.py",
    "orchestrator/consensus.py",
    "orchestrator/repair.py",
    "orchestrator/prediction.py",
    "orchestrator/budget.py",
    "orchestrator/context_manager.py",
    "orchestrator/knowledge_layer.py",
    "orchestrator/reasoning_layer.py",
    "orchestrator/validation_layer.py",
    "orchestrator/contracts.py",
    "orchestrator/execution_manager.py",
    "orchestrator/execution_replay.py",
    "orchestrator/experience_db.py",
    "orchestrator/versioning.py",
    "orchestrator/execution_manifest.py",
    "orchestrator/feature_flags.py",
    "orchestrator/skills.py",
    "orchestrator/uncertainty.py",
    "orchestrator/performance.py",
    "orchestrator/memory_hierarchy.py",
    "orchestrator/retrieval.py",
    "orchestrator/routing_feedback.py",
    "orchestrator/memory_manager.py",
    "core/schemas.py",
    "api_gateway/strategy.py",
    "api_gateway/capabilities.py",
    "api_gateway/client.py",
]

# config/ files — any change under config/capabilities/ or
# config/prompt_versions.json requires a bump.
WATCHLIST_DIR_GLOBS: list[str] = [
    "config/capabilities/",
    "config/prompt_versions.json",
]

VERSION_RE = re.compile(
    r'architecture_version\s*[:=]\s*["\']([^"\']+)["\']'
)


def _is_watchlisted(path: str) -> bool:
    p = path.strip().replace("\\", "/")
    for g in WATCHLIST_GLOBS:
        if p == g:
            return True
    for d in WATCHLIST_DIR_GLOBS:
        if p.startswith(d):
            return True
    return False


def _extract_version(text: str) -> str | None:
    m = VERSION_RE.search(text)
    return m.group(1) if m else None


def _read_current_version() -> str | None:
    if not VERSION_FILE.is_file():
        return None
    return _extract_version(VERSION_FILE.read_text(encoding="utf-8"))


def _git(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _read_base_version(base_ref: str) -> str | None:
    text = _git(["show", f"{base_ref}:{VERSION_FILE_REL}"])
    if text is None:
        return None
    return _extract_version(text)


def _read_changed_files_from_git(base_ref: str) -> list[str] | None:
    out = _git(["diff", "--name-only", base_ref])
    if out is None:
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


def _read_changed_files_from_stdin() -> list[str]:
    return [line.strip() for line in sys.stdin if line.strip()]


def _parse_version_tuple(version: str) -> tuple[int, ...] | None:
    parts = version.strip().split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def _version_bumped(base: str, current: str) -> bool:
    """True when current is a bump beyond base.

    Numeric dotted versions are compared component-wise. If either
    version is not numeric-dotted, any change in the string counts as
    a bump (fail only on exact equality).
    """
    base_t = _parse_version_tuple(base)
    cur_t = _parse_version_tuple(current)
    if base_t is not None and cur_t is not None:
        return cur_t > base_t
    return current != base


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that architectural changes include a version bump."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--stdin",
        action="store_true",
        help="Read changed file list from stdin (one per line).",
    )
    group.add_argument(
        "--changed-files",
        nargs="+",
        help="List of changed file paths.",
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help=(
            "Git revision to compare architecture_version against and, "
            "when no explicit file list is given, to diff for changed "
            "files (default: origin/main)."
        ),
    )
    args = parser.parse_args()

    if args.stdin:
        changed = _read_changed_files_from_stdin()
    elif args.changed_files:
        changed = args.changed_files
    else:
        derived = _read_changed_files_from_git(args.base_ref)
        if derived is None:
            sys.stderr.write(
                "check_architecture_version failed: could not derive "
                f"changed files from git diff against '{args.base_ref}'. "
                "Provide --stdin or --changed-files, or fix the ref.\n"
            )
            return 1
        changed = derived

    watchlisted = [f for f in changed if _is_watchlisted(f)]

    if not watchlisted:
        return 0

    current_version = _read_current_version()
    if current_version is None:
        sys.stderr.write(
            "check_architecture_version failed: could not read "
            "architecture_version from orchestrator/versioning.py.\n"
        )
        return 1

    if _git(["rev-parse", "--verify", args.base_ref]) is None:
        sys.stderr.write(
            "check_architecture_version failed: base ref "
            f"'{args.base_ref}' does not exist. Fetch it (e.g. "
            "git fetch origin main) or pass --base-ref.\n"
        )
        return 1

    base_version = _read_base_version(args.base_ref)
    if base_version is None:
        # versioning.py absent (or unparsable) at base: the version file
        # itself is being introduced, which is inherently a version change.
        sys.stderr.write(
            f"Note: no architecture_version at base ref '{args.base_ref}'; "
            "treating current version as a bump.\n"
        )
        return 0

    if _version_bumped(base_version, current_version):
        return 0

    sys.stderr.write(
        f"Architectural files changed ({len(watchlisted)}):\n"
    )
    for f in watchlisted:
        sys.stderr.write(f"  - {f}\n")
    sys.stderr.write(
        f"\nBase architecture_version:    {base_version}\n"
        f"Current architecture_version: {current_version}\n"
        f"Please bump architecture_version in orchestrator/versioning.py "
        f"and record the change in docs/new/decision_register.md.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
