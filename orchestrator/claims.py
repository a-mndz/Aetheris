"""
aetheris — Adaptive Multi-Model Reasoning Orchestrator
Claim Manager: extracts and validates factual claims from agent outputs
to detect hallucinations and unsupported assertions.

Integrates with the ReasoningGraph to store validated claims and track
provenance for audit and learning.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from orchestrator.reasoning_graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    ReasoningGraph,
    _generate_id,
    _utc_now,
)

logger = logging.getLogger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────────


class ClaimType(str, Enum):
    FACTUAL = "factual"
    LOGICAL = "logical"
    OPINION = "opinion"
    SPECULATION = "speculation"


class ValidationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"
    PENDING = "pending"


# ── Data Classes ───────────────────────────────────────────────────────────


@dataclass
class Claim:
    claim_id: str
    content: str
    claim_type: ClaimType
    confidence: float
    source_agent: str
    validation_status: ValidationStatus = ValidationStatus.PENDING
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


# ── Claim Manager ──────────────────────────────────────────────────────────


class ClaimManager:
    """Extract, classify, and validate factual claims from agent outputs.

    Uses regex-based extraction and keyword-matching classification.
    Validates claims with placeholder logic (future: Wikipedia API or
    fact-checking service) and stores validated claims in the
    ReasoningGraph for future reference and audit.
    """

    # Regex patterns for extracting sentences that look like claims.
    # Matches sentences containing copular/linking verbs or modal verbs
    # that typically introduce assertions.
    _CLAIM_PATTERNS: list[re.Pattern[str]] = [
        re.compile(
            r"(?:^|[.!?]\s+)(?:.*?\b(is|are|was|were|has|have|will|can|could|should|may|might)\b.+?[.!?])",
            re.IGNORECASE,
        ),
    ]

    # Keywords for claim type classification.
    _LOGICAL_KEYWORDS: frozenset[str] = frozenset({
        "if", "then", "therefore", "because", "implies",
        "thus", "hence", "consequently", "so",
    })
    _OPINION_KEYWORDS: frozenset[str] = frozenset({
        "should", "better", "prefer", "believe", "think",
        "recommend", "opinion", "best", "worst",
    })
    _SPECULATION_KEYWORDS: frozenset[str] = frozenset({
        "might", "could", "possibly", "may", "perhaps",
        "probably", "likely", "unlikely", "speculate",
    })

    # Simple sentence splitter – handles period/question/exclamation
    # followed by a space or end-of-string.
    _SENTENCE_SPLITTER: re.Pattern[str] = re.compile(r"(?<=[.!?])\s+")

    # ── Extraction ───────────────────────────────────────────────────

    def extract_claims(self, text: str, agent_name: str) -> list[Claim]:
        """Extract potential claims from *text* produced by *agent_name*.

        A claim is any sentence that contains a linking verb, auxiliary
        verb, or modal verb that suggests an assertion about the world.

        Returns a (possibly empty) list of :class:`Claim` instances with
        ``PENDING`` validation status.
        """
        if not text or not text.strip():
            return []

        sentences = self._split_sentences(text)
        claims: list[Claim] = []

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if self._sentence_looks_like_claim(sentence):
                claim_type = self.classify_claim_type(sentence)
                claim = Claim(
                    claim_id=_generate_id(),
                    content=sentence,
                    claim_type=claim_type,
                    confidence=0.5,  # default until validation
                    source_agent=agent_name,
                    validation_status=ValidationStatus.PENDING,
                )
                claims.append(claim)

        logger.debug(
            "Extracted %d claims from agent '%s'", len(claims), agent_name,
            extra={"stage": "claims_manager", "agent": agent_name, "num_claims": len(claims)}
        )
        return claims

    # ── Classification ───────────────────────────────────────────────

    def classify_claim_type(self, claim_text: str) -> ClaimType:
        """Classify a claim sentence by type using keyword heuristics.

        Classification order (first match wins):
        1. LOGICAL  – contains logical connectors
        2. OPINION  – contains opinion markers
        3. SPECULATION – contains speculation markers
        4. FACTUAL  – default when no specific keywords match
        """
        lower = claim_text.lower()
        words = set(lower.split())

        if words & self._LOGICAL_KEYWORDS:
            return ClaimType.LOGICAL
        if words & self._OPINION_KEYWORDS:
            return ClaimType.OPINION
        if words & self._SPECULATION_KEYWORDS:
            return ClaimType.SPECULATION
        return ClaimType.FACTUAL

    # ── Validation ───────────────────────────────────────────────────

    def validate_claim(self, claim: Claim) -> ValidationStatus:
        """Validate a claim against available knowledge.

        Phase 1 placeholder: returns ``UNVERIFIED`` with confidence < 0.5
        for all claims.  Future: integrate Wikipedia API or a dedicated
        fact-checking service.
        """
        # Placeholder validation – all claims are unverified initially.
        claim.validation_status = ValidationStatus.UNVERIFIED
        claim.confidence = 0.3
        logger.debug(
            "Claim %s validated as UNVERIFIED (confidence=%.2f)",
            claim.claim_id,
            claim.confidence,
            extra={"stage": "claims_manager", "claim_id": claim.claim_id, "confidence": claim.confidence, "status": "unverified"}
        )
        return claim.validation_status

    # ── Storage ──────────────────────────────────────────────────────

    def store_claim(
        self,
        claim: Claim,
        reasoning_graph: ReasoningGraph,
    ) -> str:
        """Store a validated claim in the ReasoningGraph.

        Creates a ``CLAIM`` node and, if supporting evidence nodes exist,
        ``SUPPORTS`` edges from the claim to those nodes.

        Returns the graph ``node_id`` of the stored claim.
        """
        node = GraphNode(
            node_id=claim.claim_id,
            node_type=NodeType.CLAIM,
            content=claim.content,
            metadata={
                "claim_type": claim.claim_type.value,
                "confidence": claim.confidence,
                "source_agent": claim.source_agent,
                "validation_status": claim.validation_status.value,
                "provenance": dict(claim.provenance),
            },
        )
        node_id = reasoning_graph.add_node(node)

        # Link to any existing reasoning steps that share keywords
        claim_words = set(claim.content.lower().split())
        for existing in list(reasoning_graph._nodes.values()):
            if existing.node_id == node_id:
                continue
            if existing.node_type in (NodeType.CLAIM, NodeType.REASONING_STEP):
                existing_words = set(existing.content.lower().split())
                overlap = len(claim_words & existing_words)
                if overlap >= 3:
                    edge = GraphEdge(
                        source_id=node_id,
                        target_id=existing.node_id,
                        edge_type=EdgeType.SUPPORTS,
                        weight=min(1.0, overlap / 10.0),
                    )
                    reasoning_graph.add_edge(edge)

        logger.debug("Stored claim %s in reasoning graph as node %s", claim.claim_id, node_id, extra={"stage": "claims_manager", "claim_id": claim.claim_id, "node_id": node_id})
        return node_id

    # ── Provenance ───────────────────────────────────────────────────

    def track_claim_provenance(
        self,
        claim: Claim,
        source: str,
        timestamp: datetime,
        validation_method: str,
    ) -> None:
        """Record provenance metadata for *claim*.

        Provenance tracks where the claim came from, when it was
        extracted, and how it was validated.
        """
        claim.provenance = {
            "source": source,
            "timestamp": timestamp.isoformat(),
            "validation_method": validation_method,
        }
        logger.debug(
            "Tracked provenance for claim %s: source=%s method=%s",
            claim.claim_id,
            source,
            validation_method,
            extra={"stage": "claims_manager", "claim_id": claim.claim_id, "source": source, "method": validation_method}
        )

    # ── Querying ─────────────────────────────────────────────────────

    def get_unverified_claims(
        self,
        agent_name: Optional[str] = None,
        claims: Optional[list[Claim]] = None,
    ) -> list[Claim]:
        """Return claims that have not yet been verified.

        If *agent_name* is provided, only claims from that agent are
        returned.  Pass an external *claims* list to search; otherwise
        the method returns an empty list (claims are stored externally
        by the caller or in the reasoning graph).
        """
        if claims is None:
            return []

        result = [
            c for c in claims
            if c.validation_status == ValidationStatus.UNVERIFIED
        ]
        if agent_name:
            result = [c for c in result if c.source_agent == agent_name]

        return result

    # ── Internal helpers ─────────────────────────────────────────────

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split *text* into sentences on period/question/exclamation marks."""
        parts = ClaimManager._SENTENCE_SPLITTER.split(text)
        return [p.strip() for p in parts if p.strip()]

    @classmethod
    def _sentence_looks_like_claim(cls, sentence: str) -> bool:
        """Return True if *sentence* contains a verb suggesting an assertion."""
        lower = sentence.lower()
        # Check for common assertion verbs via simple substring search
        assertion_markers = (
            " is ", " are ", " was ", " were ",
            " has ", " have ", " will ", " can ",
            " could ", " should ", " may ", " might ",
            " produces ", " creates ", " enables ",
            " provides ", " supports ", " indicates ",
        )
        return any(marker in lower for marker in assertion_markers)
