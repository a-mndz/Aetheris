"""Deterministic prediction layer for cost, latency, token, and confidence estimates."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.schemas import PipelineBudget, Prediction, PredictionInterval, TaskGraph, TaskProfile

LOGGER = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CALIBRATION_PATH = (
    _REPO_ROOT / "config" / "capabilities" / "prediction_calibration.json"
)
_FALLBACK_CALIBRATION = {
    "defaults": {
        "expected_cost_usd": {"value": 0.01, "variance": 0.0001, "std_dev": 0.01, "sample_size": 0},
        "expected_latency_ms": {"value": 4000, "variance": 2250000, "std_dev": 1500, "sample_size": 0},
        "expected_tokens": {"value": 1200, "variance": 250000, "std_dev": 500, "sample_size": 0},
        "expected_confidence": {"value": 0.70, "variance": 0.01, "std_dev": 0.10, "sample_size": 0},
        "probability_of_failure": 0.05,
        "probability_of_repair": 0.15,
        "probability_of_retrieval_needed": 0.10,
        "probability_of_clarification_needed": 0.05,
        "probability_of_consensus_disagreement": 0.20,
        "expected_repair_count": 0,
        "calibration_confidence": 0.20,
    },
    "by_complexity": {
        "low": {"expected_tokens_multiplier": 0.5, "expected_latency_multiplier": 0.5, "probability_of_repair": 0.05},  # noqa: E501
        "medium": {"expected_tokens_multiplier": 1.0, "expected_latency_multiplier": 1.0, "probability_of_repair": 0.15},  # noqa: E501
        "high": {"expected_tokens_multiplier": 2.0, "expected_latency_multiplier": 2.0, "probability_of_repair": 0.30},  # noqa: E501
        "critical": {"expected_tokens_multiplier": 3.5, "expected_latency_multiplier": 3.0, "probability_of_repair": 0.40},  # noqa: E501
    },
    "by_task_type": {
        "general": {"probability_of_retrieval_needed": 0.10},
        "coding": {"probability_of_retrieval_needed": 0.05, "probability_of_repair": 0.30},
        "research": {"probability_of_retrieval_needed": 0.90},
        "math": {"probability_of_retrieval_needed": 0.05, "probability_of_consensus_disagreement": 0.30},
        "creative": {"probability_of_retrieval_needed": 0.05, "probability_of_consensus_disagreement": 0.35},
    },
}


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


class PredictionLayer:
    """Provide conservative request priors with simple graph-aware adjustments."""

    version = "prediction-layer-v1"

    def __init__(self, *, calibration_path: str | Path | None = None) -> None:
        self._calibration_path = (
            Path(calibration_path) if calibration_path is not None else _DEFAULT_CALIBRATION_PATH
        )
        self._config = self._load_calibration(self._calibration_path)

    @staticmethod
    def _load_calibration(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Falling back to built-in prediction priors: %s", exc)
            return _FALLBACK_CALIBRATION

        if not isinstance(payload, dict):
            return _FALLBACK_CALIBRATION
        return {key: value for key, value in payload.items() if not key.startswith("_")}

    @staticmethod
    def _interval(payload: dict[str, Any]) -> PredictionInterval:
        return PredictionInterval(
            value=float(payload.get("value", 0.0)),
            variance=float(payload.get("variance", 0.0)),
            std_dev=float(payload.get("std_dev", 0.0)),
            sample_size=int(payload.get("sample_size", 0)),
        )

    def predict(
        self,
        task_profile: TaskProfile,
        *,
        graph: TaskGraph | None = None,
        budget: PipelineBudget | None = None,
    ) -> Prediction:
        """Generate deterministic priors from config, task profile, and graph hints."""

        defaults = self._config.get("defaults", _FALLBACK_CALIBRATION["defaults"])
        complexity = self._config.get("by_complexity", {}).get(
            task_profile.complexity,
            _FALLBACK_CALIBRATION["by_complexity"]["medium"],
        )
        task_type = self._config.get("by_task_type", {}).get(
            task_profile.task_type,
            _FALLBACK_CALIBRATION["by_task_type"]["general"],
        )

        expected_tokens = self._interval(defaults["expected_tokens"])
        expected_latency = self._interval(defaults["expected_latency_ms"])
        expected_cost = self._interval(defaults["expected_cost_usd"])
        expected_confidence = self._interval(defaults["expected_confidence"])

        complexity_token_multiplier = float(complexity.get("expected_tokens_multiplier", 1.0))
        complexity_latency_multiplier = float(complexity.get("expected_latency_multiplier", 1.0))
        expected_tokens.value *= complexity_token_multiplier
        expected_tokens.std_dev *= complexity_token_multiplier
        expected_tokens.variance *= complexity_token_multiplier**2
        expected_latency.value *= complexity_latency_multiplier
        expected_latency.std_dev *= complexity_latency_multiplier
        expected_latency.variance *= complexity_latency_multiplier**2
        expected_cost.value *= complexity_token_multiplier
        expected_cost.std_dev *= complexity_token_multiplier
        expected_cost.variance *= complexity_token_multiplier**2

        node_count = len(graph.nodes) if graph is not None else 0
        graph_tokens = float(sum(node.expected_tokens or 0 for node in graph.nodes)) if graph else 0.0
        graph_latency = float(sum(node.expected_latency_ms or 0 for node in graph.nodes)) if graph else 0.0

        if graph_tokens > 0:
            expected_tokens.value = max(expected_tokens.value, graph_tokens)
            expected_tokens.std_dev = max(expected_tokens.std_dev, graph_tokens * 0.15)
            expected_tokens.variance = max(expected_tokens.variance, expected_tokens.std_dev**2)
        if graph_latency > 0:
            expected_latency.value = max(expected_latency.value, graph_latency)
            expected_latency.std_dev = max(expected_latency.std_dev, graph_latency * 0.20)
            expected_latency.variance = max(expected_latency.variance, expected_latency.std_dev**2)

        if budget is not None:
            expected_tokens.value = min(expected_tokens.value, float(budget.total_tokens))
            expected_tokens.std_dev = min(
                expected_tokens.std_dev,
                max(1.0, float(budget.total_tokens) - expected_tokens.value),
            )
            expected_tokens.variance = min(expected_tokens.variance, expected_tokens.std_dev**2)

        base_confidence = expected_confidence.value
        confidence_penalty = {
            "low": 0.02,
            "medium": 0.05,
            "high": 0.12,
            "critical": 0.18,
        }.get(task_profile.complexity, 0.05)
        expected_confidence.value = _clamp_probability(base_confidence - confidence_penalty)

        probability_of_failure = defaults.get("probability_of_failure", 0.0)
        probability_of_repair = task_type.get(
            "probability_of_repair",
            complexity.get("probability_of_repair", defaults.get("probability_of_repair", 0.0)),
        )
        probability_of_retrieval_needed = task_type.get(
            "probability_of_retrieval_needed",
            defaults.get("probability_of_retrieval_needed", 0.0),
        )
        probability_of_clarification_needed = defaults.get(
            "probability_of_clarification_needed",
            0.0,
        )
        probability_of_consensus_disagreement = task_type.get(
            "probability_of_consensus_disagreement",
            defaults.get("probability_of_consensus_disagreement", 0.0),
        )

        expected_repair_count = int(
            round(max(defaults.get("expected_repair_count", 0), probability_of_repair * max(1, node_count)))
        )
        calibration_confidence = float(defaults.get("calibration_confidence", 0.0))
        if graph_tokens > 0 and graph_latency > 0:
            calibration_confidence = _clamp_probability(calibration_confidence + 0.10)

        return Prediction(
            expected_cost=expected_cost,
            expected_latency_ms=expected_latency,
            expected_tokens=expected_tokens,
            expected_confidence=expected_confidence,
            probability_of_failure=_clamp_probability(float(probability_of_failure)),
            probability_of_repair=_clamp_probability(float(probability_of_repair)),
            probability_of_retrieval_needed=_clamp_probability(float(probability_of_retrieval_needed)),
            probability_of_clarification_needed=_clamp_probability(float(probability_of_clarification_needed)),
            probability_of_consensus_disagreement=_clamp_probability(float(probability_of_consensus_disagreement)),
            expected_repair_count=max(0, expected_repair_count),
            calibration_confidence=calibration_confidence,
        )

    def record_actuals(
        self,
        prediction: Prediction,
        *,
        actual_cost: float,
        actual_latency_ms: float,
        actual_tokens: int,
        actual_confidence: float,
    ) -> dict[str, float | bool]:
        """Emit expected-vs-actual telemetry using the RFC metric namespace."""

        return {
            "prediction.cost.predicted": prediction.expected_cost.value,
            "prediction.cost.actual": float(actual_cost),
            "prediction.cost.delta": float(actual_cost) - prediction.expected_cost.value,
            "prediction.cost.within_upper_bound": float(actual_cost) <= prediction.expected_cost.upper_bound,
            "prediction.latency.predicted": prediction.expected_latency_ms.value,
            "prediction.latency.actual": float(actual_latency_ms),
            "prediction.latency.delta": float(actual_latency_ms) - prediction.expected_latency_ms.value,
            "prediction.latency.within_upper_bound": float(actual_latency_ms) <= prediction.expected_latency_ms.upper_bound,  # noqa: E501
            "prediction.tokens.predicted": prediction.expected_tokens.value,
            "prediction.tokens.actual": int(actual_tokens),
            "prediction.tokens.delta": int(actual_tokens) - prediction.expected_tokens.value,
            "prediction.tokens.within_upper_bound": float(actual_tokens) <= prediction.expected_tokens.upper_bound,  # noqa: E501
            "prediction.confidence.predicted": prediction.expected_confidence.value,
            "prediction.confidence.actual": float(actual_confidence),
            "prediction.confidence.delta": float(actual_confidence) - prediction.expected_confidence.value,
            "prediction.calibration_confidence": prediction.calibration_confidence,
            "prediction.repair.likelihood": prediction.probability_of_repair,
        }
