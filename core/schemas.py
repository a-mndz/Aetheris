"""
aetheris — Adaptive Multi-Model Reasoning Orchestrator
Core data contracts (Pydantic V2 strict models).

These schemas define the structured I/O boundaries between agents,
the signal-evaluation layer, and the final synthesis output.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── Signal State ─────────────────────────────────────────────────────────


class SignalState(BaseModel):
    """
    Real-time evaluation metrics computed by the orchestrator's
    signal-analysis layer.

    .. note::
        Currently unused in the Micro-Mode pipeline (Phase 1).
        Reserved for Phase 2 signal-evaluation integration where
        the orchestrator will compute real-time quality signals
        across agent outputs.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    similarity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Semantic similarity score (0-1).",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (0-1).",
    )
    bias_risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Bias-risk score (0-1).",
    )
    knowledge_absence: bool = Field(
        ...,
        description="Flag indicating knowledge absence.",
    )


# ── Agent Output ─────────────────────────────────────────────────────────


class AgentOutput(BaseModel):
    """
    Structured output contract that every generation agent must conform to.

    Design note: ``strict=True`` is used with a ``mode='before'``
    validator on ``confidence``.  The before-mode validator runs
    *prior* to strict type checking, allowing string-to-float
    coercion (e.g. ``'high'`` → ``0.9``) while still enforcing
    strict types on all other fields.
    """

    model_config = ConfigDict(strict=True)

    @model_validator(mode="before")
    @classmethod
    def map_contract_fields(cls, data: Any) -> Any:
        """Map alternative XML response contract fields and dynamic role XML schemas to standard schema fields."""
        if isinstance(data, dict):
            # 1. Resolve 'confidence'
            if "confidence" in data:
                conf = data["confidence"]
                if isinstance(conf, dict):
                    level = conf.get("level", "medium")
                    if isinstance(level, str):
                        mapping = {"high": 0.9, "medium": 0.5, "low": 0.2}
                        data["confidence"] = mapping.get(level.lower().strip(), 0.5)
                    else:
                        data["confidence"] = 0.5

            # 2. Resolve 'answer'
            if "answer" not in data:
                potential_answers = [
                    "summary", 
                    "draft_answer", 
                    "primary_solution", 
                    "recommendation", 
                    "problem", 
                    "status"
                ]
                for field in potential_answers:
                    if field in data and data[field]:
                        val = data[field]
                        if isinstance(val, str) and val.strip():
                            data["answer"] = val
                            break
                        elif isinstance(val, list) and val:
                            data["answer"] = str(val[0])
                            break
                if "answer" not in data:
                    data["answer"] = "No explicit answer field found in model output."

            # 3. Resolve 'reasoning_steps'
            if "reasoning_steps" not in data:
                potential_steps = [
                    "claims",
                    "logical_analysis",
                    "progress",
                    "tradeoffs",
                    "alternative_solutions",
                    "edge_cases",
                    "requirements"
                ]
                steps = []
                for field in potential_steps:
                    if field in data and data[field]:
                        val = data[field]
                        if isinstance(val, list):
                            for item in val:
                                if isinstance(item, dict):
                                    steps.append(json.dumps(item))
                                else:
                                    steps.append(str(item))
                        elif isinstance(val, str) and val.strip():
                            steps.append(val)
                data["reasoning_steps"] = steps if steps else ["No explicit reasoning steps found."]
        return data

    reasoning_steps: list[str] = Field(
        ...,
        min_length=0,
        description="Reasoning steps/trace of the agent.",
    )
    answer: str = Field(
        ...,
        min_length=0,
        description="Final answer string.",
    )
    confidence: float = Field(
        ...,
        description="Agent self-assessed confidence.",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def convert_confidence(cls, v: Any) -> float:
        """Coerce string confidence metrics from older schemas/simulators into standard floats."""
        if isinstance(v, str):
            mapping = {"high": 0.9, "medium": 0.5, "low": 0.2}
            return mapping.get(v.lower().strip(), 0.5)
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.5


# ── aetheris Final Output ──────────────────────────────────────────────────


class aetherisOutput(BaseModel):
    """
    The final synthesized validation output returned by validation arbitrage.
    """

    model_config = ConfigDict(strict=True)

    @model_validator(mode="before")
    @classmethod
    def map_contract_fields(cls, data: Any) -> Any:
        """Map alternative XML response contract fields to synthesizer schema fields."""
        if isinstance(data, dict):
            if "final_answer" not in data and "summary" in data:
                data["final_answer"] = data["summary"]
            if "overall_confidence" not in data and "confidence" in data:
                conf = data["confidence"]
                if isinstance(conf, (int, float)):
                    if conf >= 0.75:
                        data["overall_confidence"] = "High"
                    elif conf >= 0.4:
                        data["overall_confidence"] = "Medium"
                    else:
                        data["overall_confidence"] = "Low"
                elif isinstance(conf, dict):
                    data["overall_confidence"] = conf.get("level", "Medium")
                else:
                    data["overall_confidence"] = str(conf)
            if "overall_bias_risk" not in data:
                if "warnings" in data:
                    warnings = data["warnings"]
                    data["overall_bias_risk"] = "High" if warnings else "Low"
                else:
                    data["overall_bias_risk"] = "Low"
            if "disagreement_notes" not in data and "warnings" in data:
                warnings = data["warnings"]
                if isinstance(warnings, list):
                    data["disagreement_notes"] = [str(w) for w in warnings]
                elif isinstance(warnings, str):
                    data["disagreement_notes"] = [warnings]
            if "validation_score" not in data:
                if "confidence" in data and isinstance(data["confidence"], (int, float)):
                    data["validation_score"] = float(data["confidence"]) * 10.0
                else:
                    data["validation_score"] = 9.0  # default score
        return data

    final_answer: str = Field(
        ...,
        description="Synthesized response.",
    )
    overall_confidence: str = Field(
        ...,
        description="Overall confidence category (High/Medium/Low).",
    )
    overall_bias_risk: str = Field(
        ...,
        description="Overall bias risk category (Low/Medium/High).",
    )
    disagreement_notes: list[str] = Field(
        default_factory=list,
        description="Disagreements surfaced during arbitration.",
    )
    validation_score: float = Field(
        ...,
        description="Scoring indicating overall logical consistency.",
    )


# ── AETHERIS Shared Schemas ─────────────────────────────────────────────────────


class SessionMetadata(BaseModel):
    """Conversation session metadata shared with API and telemetry layers."""

    model_config = ConfigDict(strict=True)

    session_id: str = Field(..., min_length=1)
    user_id: str | None = None
    created_at: datetime
    last_activity: datetime
    turn_count: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    state: Literal["active", "waiting", "completed", "failed"]


class PipelineResult(BaseModel):
    """Structured result produced by a complete AETHERIS pipeline execution."""

    model_config = ConfigDict(strict=True)

    request_id: str = Field(..., min_length=1)
    session_id: str | None = None
    status: Literal["success", "error", "aborted"]
    final_answer: str
    validation_score: float = Field(..., ge=0.0, le=10.0)
    confidence_delta: float = Field(..., ge=0.0, le=1.0)
    agent_outputs: dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: float = Field(..., ge=0.0)
    security_metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderHealthStatus(BaseModel):
    """Current provider health snapshot used for routing and monitoring."""

    model_config = ConfigDict(strict=True)

    provider_name: str = Field(..., min_length=1)
    status: Literal["healthy", "degraded", "dead"]
    success_rate: float = Field(..., ge=0.0, le=1.0)
    avg_latency_ms: float = Field(..., ge=0.0)
    error_count_24h: int = Field(..., ge=0)
    last_check: datetime


class CheckpointData(BaseModel):
    """Minimal state required to resume a pipeline from a checkpoint."""

    model_config = ConfigDict(strict=True)

    checkpoint_id: str = Field(..., min_length=1)
    request_id: str = Field(..., min_length=1)
    stage: str = Field(..., min_length=1)
    timestamp: datetime
    agent_outputs: dict[str, Any] = Field(default_factory=dict)
    partial_results: dict[str, Any] = Field(default_factory=dict)
