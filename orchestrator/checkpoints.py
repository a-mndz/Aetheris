"""
aetheris — Checkpoint Manager
Save and restore pipeline state for recovery from failures.

Specifications from Requirement 13:
- Save timeout: 5 seconds
- Restore timeout: 10 seconds
- Total checkpoint size limit: 10 MB per request
- Individual agent output size limit: 5 MB
- Retention period: configurable 1 hour to 30 days (default 7 days)
- Storage backends: memory (Phase 1), filesystem, database
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid

from core.validators import (
    utc_now,
    validate_non_empty,
    validate_enum,
    validate_dict,
)
from core.error_handlers import with_timeout

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """A saved pipeline state checkpoint."""
    checkpoint_id: str
    request_id: str
    session_id: Optional[str]
    stage: str
    agent_outputs: dict[str, Any]
    partial_results: dict[str, Any]
    timestamp: datetime = field(default_factory=utc_now)
    expires_at: datetime = field(default_factory=lambda: utc_now() + timedelta(days=7))


class CheckpointManager:
    """
    Save and restore pipeline state for recovery from failures.

    Specifications from Requirement 13:
    - 5-second save timeout
    - 10-second restore timeout
    - 10 MB total size per request, 5 MB per agent output
    - Configurable retention: 1 hour to 30 days (default 7 days)
    - Storage backends: memory, filesystem, database
    """

    # Timeouts (Requirement 13.1, 13.4-13.5)
    SAVE_TIMEOUT_SEC = 5  # 5-second timeout for save operations
    RESTORE_TIMEOUT_SEC = 10  # 10-second timeout for restore operations
    QUERY_TIMEOUT_SEC = 2  # 2-second timeout for query operations
    EXPIRY_CLEANUP_TIMEOUT_SEC = 2  # 2-second timeout for expiry cleanup

    # Size limits (Requirement 13.9)
    MAX_CHECKPOINT_SIZE_MB = 10  # 10 MB total size per request
    MAX_AGENT_OUTPUT_SIZE_MB = 5  # 5 MB per individual agent output

    # Retention (Requirement 13.6-13.7)
    MIN_RETENTION_HOURS = 1  # Minimum 1 hour retention
    MAX_RETENTION_DAYS = 30  # Maximum 30 days retention
    DEFAULT_RETENTION_DAYS = 7  # Default 7 days retention

    MAX_CHECKPOINTS_PER_REQUEST = 10

    def __init__(self, storage_backend: str = "memory", retention_days: int = 7):
        """Initialize with storage backend: 'memory', 'filesystem', or 'database'.

        Args:
            storage_backend: 'memory' (default), 'filesystem' (JSON files), or 'database' (PostgreSQL)
            retention_days: Checkpoint retention period (1-30 days, default 7)
        """
        validate_enum(storage_backend, ("memory", "filesystem", "database"), "storage_backend")
        self.storage_backend = storage_backend
        # Clamp retention_days to range [1/24, 30] (1 hour minimum, 30 days maximum)
        self.retention_days = max(
            self.MIN_RETENTION_HOURS / 24,
            min(retention_days, self.MAX_RETENTION_DAYS)
        )
        # In-memory storage: request_id -> list of checkpoints
        self.checkpoints: dict[str, list[Checkpoint]] = {}
        logger.info(
            "Initialized CheckpointManager with backend=%s, retention_days=%.2f",
            storage_backend,
            self.retention_days,
        )

    async def save_checkpoint(
        self,
        request_id: str,
        session_id: Optional[str],
        stage: str,
        agent_outputs: dict[str, Any],
        partial_results: dict[str, Any],
    ) -> str:
        """Save a checkpoint within 5 seconds, return checkpoint_id.

        Truncates outputs exceeding 5 MB with truncation marker.
        Fails gracefully if timeout or storage error, logs error and continues.
        """
        validate_non_empty(request_id, "request_id")
        validate_non_empty(stage, "stage")
        validate_dict(agent_outputs, "agent_outputs")
        validate_dict(partial_results, "partial_results")

        # Generate unique checkpoint_id
        checkpoint_id = str(uuid.uuid4())

        # Check total checkpoint size (rough estimate in bytes) before truncation
        total_size = self._estimate_checkpoint_size(agent_outputs, partial_results)
        max_bytes = self.MAX_CHECKPOINT_SIZE_MB * 1024 * 1024
        if total_size > max_bytes:
            logger.warning(
                "Checkpoint size %.2f MB exceeds limit %d MB for request %s, rejecting",
                total_size / (1024 * 1024),
                self.MAX_CHECKPOINT_SIZE_MB,
                request_id,
                extra={"request_id": request_id, "session_id": session_id, "stage": "checkpoint_save"}
            )
            raise ValueError(
                f"Checkpoint size {total_size / (1024 * 1024):.2f} MB exceeds "
                f"limit {self.MAX_CHECKPOINT_SIZE_MB} MB"
            )

        # Truncate agent outputs exceeding 5 MB limit
        truncated_outputs = self._truncate_agent_outputs(agent_outputs)

        # Create checkpoint with expiry
        expires_at = utc_now() + timedelta(days=self.retention_days)
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            request_id=request_id,
            session_id=session_id,
            stage=stage,
            agent_outputs=truncated_outputs,
            partial_results=partial_results,
            timestamp=utc_now(),
            expires_at=expires_at,
        )

        # Simulate save with timeout (in-memory store is fast, but we still enforce timeout)
        result = await with_timeout(
            self._store_checkpoint(checkpoint),
            timeout_sec=self.SAVE_TIMEOUT_SEC,
            operation_name="Checkpoint save",
            default=checkpoint_id,
            stage=f"checkpoint.{stage}",
        )
        logger.info(
            "Saved checkpoint %s for request %s at stage %s",
            checkpoint_id,
            request_id,
            stage,
            extra={"request_id": request_id, "session_id": session_id, "stage": "checkpoint_save"}
        )
        return checkpoint_id

    async def restore_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Restore a checkpoint by ID within 10 seconds."""
        validate_non_empty(checkpoint_id, "checkpoint_id")

        result = await with_timeout(
            self._retrieve_checkpoint(checkpoint_id),
            timeout_sec=self.RESTORE_TIMEOUT_SEC,
            operation_name="Checkpoint restore",
            default=None,
        )
        if result is None:
            logger.warning("Checkpoint %s not found", checkpoint_id, extra={"checkpoint_id": checkpoint_id, "stage": "checkpoint_restore"})
        else:
            logger.info("Restored checkpoint %s", checkpoint_id, extra={"checkpoint_id": checkpoint_id, "stage": "checkpoint_restore"})
        return result

    async def get_latest_checkpoint(self, request_id: str) -> Optional[Checkpoint]:
        """Retrieve the most recent checkpoint for a request."""
        validate_non_empty(request_id, "request_id")

        checkpoints = self.checkpoints.get(request_id.strip(), [])
        if not checkpoints:
            return None
        # Return the most recent checkpoint (sorted by timestamp descending)
        latest = max(checkpoints, key=lambda cp: cp.timestamp)
        return latest

    async def list_checkpoints(
        self,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> list[Checkpoint]:
        """List checkpoints filtered by request_id or session_id within 2 seconds."""
        result = await with_timeout(
            self._list_checkpoints_impl(request_id, session_id),
            timeout_sec=self.QUERY_TIMEOUT_SEC,
            operation_name="Checkpoint query",
            default=[],
        )
        return result or []

    async def expire_checkpoints(self) -> int:
        """Remove expired checkpoints within 2 seconds, return count removed."""
        result = await with_timeout(
            self._expire_checkpoints_impl(),
            timeout_sec=self.EXPIRY_CLEANUP_TIMEOUT_SEC,
            operation_name="Checkpoint expiry cleanup",
            default=0,
        )
        return result or 0

    async def delete_checkpoints(self, request_id: str) -> int:
        """Delete all checkpoints for a request, return count deleted."""
        validate_non_empty(request_id, "request_id")

        request_id = request_id.strip()
        if request_id in self.checkpoints:
            count = len(self.checkpoints[request_id])
            del self.checkpoints[request_id]
            logger.info(
                "Deleted %d checkpoints for request %s",
                count,
                request_id,
                extra={"request_id": request_id, "stage": "checkpoint_delete"}
            )
            return count
        return 0

    # Private helper methods

    async def _store_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Store checkpoint in backend (memory for Phase 1)."""
        if self.storage_backend == "memory":
            request_id = checkpoint.request_id
            if request_id not in self.checkpoints:
                self.checkpoints[request_id] = []
            # Enforce max checkpoints per request
            if len(self.checkpoints[request_id]) >= self.MAX_CHECKPOINTS_PER_REQUEST:
                # Remove oldest checkpoint
                oldest = min(self.checkpoints[request_id], key=lambda cp: cp.timestamp)
                self.checkpoints[request_id].remove(oldest)
                logger.debug(
                    "Removed oldest checkpoint %s for request %s to stay within limit",
                    oldest.checkpoint_id,
                    request_id,
                )
            self.checkpoints[request_id].append(checkpoint)
        else:
            # For filesystem/database backends, raise NotImplementedError for now
            raise NotImplementedError(
                f"Storage backend '{self.storage_backend}' not yet implemented"
            )

    async def _retrieve_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Retrieve checkpoint by ID from backend."""
        if self.storage_backend == "memory":
            for request_checkpoints in self.checkpoints.values():
                for checkpoint in request_checkpoints:
                    if checkpoint.checkpoint_id == checkpoint_id:
                        return checkpoint
            return None
        else:
            raise NotImplementedError(
                f"Storage backend '{self.storage_backend}' not yet implemented"
            )

    async def _list_checkpoints_impl(
        self,
        request_id: Optional[str],
        session_id: Optional[str],
    ) -> list[Checkpoint]:
        """List checkpoints with optional filters."""
        if self.storage_backend == "memory":
            results: list[Checkpoint] = []
            for req_id, checkpoints in self.checkpoints.items():
                if request_id is not None and req_id != request_id:
                    continue
                for checkpoint in checkpoints:
                    if session_id is not None and checkpoint.session_id != session_id:
                        continue
                    results.append(checkpoint)
            # Sort by timestamp descending
            results.sort(key=lambda cp: cp.timestamp, reverse=True)
            return results
        else:
            raise NotImplementedError(
                f"Storage backend '{self.storage_backend}' not yet implemented"
            )

    async def _expire_checkpoints_impl(self) -> int:
        """Remove expired checkpoints from backend."""
        if self.storage_backend == "memory":
            now = utc_now()
            expired_count = 0
            expired_request_ids = []
            for request_id, checkpoints in self.checkpoints.items():
                # Find expired checkpoints
                expired_checkpoints = [
                    cp for cp in checkpoints if cp.expires_at < now
                ]
                for cp in expired_checkpoints:
                    checkpoints.remove(cp)
                    expired_count += 1
                if not checkpoints:
                    expired_request_ids.append(request_id)
            # Clean up empty request entries
            for request_id in expired_request_ids:
                del self.checkpoints[request_id]
            return expired_count
        else:
            raise NotImplementedError(
                f"Storage backend '{self.storage_backend}' not yet implemented"
            )

    def _truncate_agent_outputs(self, agent_outputs: dict[str, Any]) -> dict[str, Any]:
        """Truncate agent outputs exceeding 5 MB limit."""
        max_bytes = self.MAX_AGENT_OUTPUT_SIZE_MB * 1024 * 1024
        truncated = {}
        for agent_name, output in agent_outputs.items():
            # Estimate size of output
            try:
                output_bytes = len(json.dumps(output, default=str).encode("utf-8"))
            except Exception:
                # If serialization fails, treat as zero size
                output_bytes = 0
            if output_bytes > max_bytes:
                # Truncate with marker
                if isinstance(output, str):
                    truncated[agent_name] = (
                        output[:1000] + "[TRUNCATED: exceeded 5 MB limit]"
                    )
                else:
                    truncated[agent_name] = (
                        f"[TRUNCATED: exceeded 5 MB limit] Original size: {output_bytes} bytes"
                    )
                logger.warning(
                    "Truncated agent output for %s: %d bytes > %d bytes limit",
                    agent_name,
                    output_bytes,
                    max_bytes,
                    extra={"agent_name": agent_name, "stage": "checkpoint_save"}
                )
            else:
                truncated[agent_name] = output
        return truncated

    def _estimate_checkpoint_size(
        self,
        agent_outputs: dict[str, Any],
        partial_results: dict[str, Any],
    ) -> int:
        """Estimate checkpoint size in bytes (rough estimate)."""
        # Serialize to JSON and count bytes
        data = {
            "agent_outputs": agent_outputs,
            "partial_results": partial_results,
        }
        try:
            return len(json.dumps(data, default=str).encode("utf-8"))
        except Exception:
            # Fallback estimate: 100 bytes per item
            return (len(agent_outputs) + len(partial_results)) * 100