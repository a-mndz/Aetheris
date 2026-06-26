"""
aetheris — AETHERIS Central Orchestration Module

Factory function that instantiates all AETHERIS components, wires their
dependencies, and returns a dictionary mapping component names to instances.

This module is the single entry point for bootstrapping the complete
AETHERIS architecture so that main.py and other consumers do not need to
know the internal wiring of each component.
"""

from __future__ import annotations

import logging
from typing import Any

from core.passport import ExecutionPassport
from core.runtime import RuntimeEngine
from core.security import SecurityValidator
from orchestrator.checkpoints import CheckpointManager
from orchestrator.claims import ClaimManager
from orchestrator.conversation import ConversationDirector
from orchestrator.decisions import DecisionEngine, DecisionStrategy
from orchestrator.memory_manager import MemoryManager, SummarizationStrategy
from orchestrator.reasoning_graph import ReasoningGraph
from orchestrator.state_machine import StateMachine
from orchestrator.streaming import StreamingManager

logger = logging.getLogger(__name__)


def initialize_aetheris_components() -> dict[str, Any]:
    """Instantiate all AETHERIS components and wire their dependencies.

    Returns
    -------
    dict[str, Any]
        Mapping of component name to its instance.  Keys are:

        - ``security_validator``      – SecurityValidator
        - ``conversation_director``   – ConversationDirector
        - ``state_machine``           – StateMachine (factory; callers create per-request)
        - ``checkpoint_manager``      – CheckpointManager
        - ``memory_manager``          – MemoryManager
        - ``reasoning_graph``         – ReasoningGraph
        - ``claim_manager``           – ClaimManager
        - ``decision_engine``         – DecisionEngine
        - ``streaming_manager``       – StreamingManager
        - ``resource_manager``        – ResourceManager (from api_gateway.rate_limiter)
        - ``runtime_engine``          – RuntimeEngine
    """
    # ── Security ─────────────────────────────────────────────────────
    security_validator = SecurityValidator()
    logger.info("SecurityValidator initialized.")

    # ── Conversation ─────────────────────────────────────────────────
    conversation_director = ConversationDirector()
    logger.info("ConversationDirector initialized.")

    # ── Checkpoints ──────────────────────────────────────────────────
    checkpoint_manager = CheckpointManager(storage_backend="memory", retention_days=7)
    logger.info("CheckpointManager initialized (backend=memory, retention=7d).")

    # ── Memory ───────────────────────────────────────────────────────
    memory_manager = MemoryManager(
        strategy=SummarizationStrategy.TRUNCATION,
        context_limit=128_000,
    )
    logger.info("MemoryManager initialized (strategy=truncation, limit=128k).")

    # ── Knowledge Graph ──────────────────────────────────────────────
    reasoning_graph = ReasoningGraph()
    logger.info("ReasoningGraph initialized.")

    # ── Claim Manager ────────────────────────────────────────────────
    claim_manager = ClaimManager()
    logger.info("ClaimManager initialized.")

    # ── Streaming ────────────────────────────────────────────────────
    streaming_manager = StreamingManager()
    logger.info("StreamingManager initialized.")

    # ── Decision Engine ──────────────────────────────────────────────
    decision_engine = DecisionEngine(
        strategy=DecisionStrategy.PARALLEL,
        streaming_manager=streaming_manager,
    )
    logger.info("DecisionEngine initialized (strategy=PARALLEL, streaming=True).")

    # ── Resource Manager ─────────────────────────────────────────────
    # Import at function level to avoid circular imports
    from api_gateway.rate_limiter import ResourceManager

    resource_manager = ResourceManager()
    logger.info("ResourceManager initialized.")

    # ── Runtime Engine ───────────────────────────────────────────────
    runtime_engine = RuntimeEngine(
        security_validator=security_validator,
        streaming_manager=streaming_manager,
        resource_manager=resource_manager,
    )
    logger.info("RuntimeEngine initialized (wired: security, streaming, resource).")

    components: dict[str, Any] = {
        "security_validator": security_validator,
        "conversation_director": conversation_director,
        "checkpoint_manager": checkpoint_manager,
        "memory_manager": memory_manager,
        "reasoning_graph": reasoning_graph,
        "claim_manager": claim_manager,
        "decision_engine": decision_engine,
        "streaming_manager": streaming_manager,
        "resource_manager": resource_manager,
        "runtime_engine": runtime_engine,
    }

    logger.info(
        "AETHERIS components initialized: %s",
        ", ".join(sorted(components.keys())),
    )
    return components


def create_request_passport(
    session_id: str | None = None,
    user_id: str | None = None,
) -> ExecutionPassport:
    """Create a new ExecutionPassport for a single request.

    Parameters
    ----------
    session_id:
        Optional conversation session identifier.
    user_id:
        Optional authenticated user identifier.

    Returns
    -------
    ExecutionPassport
        A fresh passport with a UUID v4 request_id and ISO 8601 timestamp.
    """
    return ExecutionPassport(session_id=session_id, user_id=user_id)


def create_request_state_machine(request_id: str) -> StateMachine:
    """Create a StateMachine bound to a specific request.

    Parameters
    ----------
    request_id:
        The passport request_id this state machine tracks.

    Returns
    -------
    StateMachine
        A new state machine initialised to the IDLE state.
    """
    return StateMachine(request_id=request_id)
