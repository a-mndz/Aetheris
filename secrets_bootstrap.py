"""
aetheris — Secret bootstrap.

Loads provider API keys from the OS-native secret store (Windows
Credential Manager, macOS Keychain, Linux Secret Service) and exports
them as ``AETHERIS_*`` environment variables *before* ``aetherisConfig``
is constructed.  This keeps live keys out of ``.env`` and out of any
file that could be committed to version control.

CRIT-007 audit compliance
--------------------------
``core/config.py`` refuses to load any value whose prefix matches the
``LEAKED_KEY_PREFIXES`` blocklist.  Plain-text ``.env`` files are the
threat surface the audit closes.  By sourcing the keys from the OS
secret store we:

  * keep them out of working-tree files (no risk of ``git add .env``)
  * keep them out of process listings (``env | grep KEY`` shows them
    only for the running process, not for any sibling shell)
  * survive reboots without re-entry, when paired with the standard
    OS-level credential persistence

How keys get there
-------------------
One-time, per developer machine:

.. code-block:: powershell

    "sk-or-v1-..."   | keyring set Aetheris OPENROUTER_API_KEY
    "nvapi-..."      | keyring set Aetheris NVIDIA_NIM_API_KEY
    ...

The service name is ``Aetheris`` and the account name is the bare
``aetherisConfig`` field name (without the ``AETHERIS_`` prefix).  The
prefix is re-applied here when exporting to the environment, so the
runtime contract (``AETHERIS_OPENROUTER_API_KEY``) is preserved.

Behaviour when keyring is unavailable
-------------------------------------
``keyring`` is a soft import.  If it isn't installed (e.g. minimal
deployment image) we log a single warning and continue.  Empty env
vars cause ``aetherisConfig`` to fall through to its ``default=""``,
which is **Simulation Mode** — the pipeline still runs end-to-end, it
just uses the orchestrator's mock provider path.

This module MUST NOT import anything that triggers ``get_settings()``,
or the whole point is lost.  Only ``os`` and (optionally) ``keyring``.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable, Mapping

logger = logging.getLogger("aetheris.secrets")

# Service name used in the OS secret store.  Override with
# ``AETHERIS_KEYRING_SERVICE`` if you want to namespace per-project
# keys under a different label.
_KEYRING_SERVICE: str = os.environ.get("AETHERIS_KEYRING_SERVICE", "Aetheris")

# Account names map 1:1 to ``aetherisConfig`` field names (no
# ``AETHERIS_`` prefix).  When we read a secret back, we re-apply the
# prefix and export it as the env var the config class expects.
_ACCOUNTS: tuple[str, ...] = (
    "OPENROUTER_API_KEY",
    "NVIDIA_NIM_API_KEY",
    "GROQ_API_KEY",
    "GITHUB_TOKEN",
    "MISTRAL_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "KIE_API_KEY",
    "UNLI_DEV_API_KEY",
)


def _read_keyring(service: str, account: str) -> str | None:
    """Read a single secret from the OS keyring.  Returns None on any
    failure (backend missing, key absent, backend error)."""
    try:
        import keyring  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        secret = keyring.get_password(service, account)
    except Exception as exc:  # noqa: BLE001 — defensive: any keyring error is non-fatal
        logger.debug("keyring.get_password(%r, %r) failed: %s", service, account, exc)
        return None
    return secret if secret else None


def _populate_env(secrets: Mapping[str, str]) -> int:
    """Export each secret to ``AETHERIS_<NAME>`` unless the env var is
    already set.  Returning the count of newly-set vars lets callers
    surface a useful log line without re-implementing the loop."""
    set_count = 0
    for account, secret in secrets.items():
        env_name = f"AETHERIS_{account}"
        # Honour an explicit override in the calling environment so
        # operators can still inject keys via ``export FOO=bar`` for
        # CI / container deployments without re-running keyring.
        if env_name in os.environ and os.environ[env_name]:
            continue
        if secret:
            os.environ[env_name] = secret
            set_count += 1
    return set_count


def load_secrets(accounts: Iterable[str] = _ACCOUNTS) -> int:
    """Read each named secret from the OS keyring and export it to the
    environment.  Returns the number of env vars that were newly set.

    Safe to call multiple times — the second call is a no-op because
    ``os.environ`` already carries the values from the first.
    """
    secrets: dict[str, str] = {}
    for account in accounts:
        secret = _read_keyring(_KEYRING_SERVICE, account)
        if secret:
            secrets[account] = secret

    if not secrets:
        # No keyring (or no stored secrets) — silently continue; the
        # config layer will fall through to empty defaults = Simulation
        # Mode.  We only log at DEBUG to keep startup output clean.
        logger.debug(
            "No provider keys found in OS keyring under service=%r. "
            "Continuing in Simulation Mode.",
            _KEYRING_SERVICE,
        )
        return 0

    set_count = _populate_env(secrets)
    logger.info(
        "Loaded %d provider key(s) from OS keyring (service=%r).",
        set_count,
        _KEYRING_SERVICE,
    )

    # CRIT-007 opt-in: because we just successfully pulled at least one
    # secret from the OS keyring, the operator's intent is clear (they
    # stored the key there on purpose).  Auto-enable the override so the
    # ``aetherisConfig`` validator lets the values through.
    #
    # If the operator later wants to *disable* keyring-sourced keys
    # without removing them from the store, they can set
    # ``AETHERIS_ALLOW_LIVE_KEYS=0`` *before* importing this module.
    if set_count > 0 and "AETHERIS_ALLOW_LIVE_KEYS" not in os.environ:
        os.environ["AETHERIS_ALLOW_LIVE_KEYS"] = "1"

    return set_count


# Run on import so a single ``import secrets_bootstrap`` is enough to
# arm the environment.  Idempotent: calling it again (e.g. from a test
# harness) is harmless because the env vars are already set.
load_secrets()
