from __future__ import annotations

from core.schemas import OutputContract, PipelineBudget, TaskGraph, TaskNode, TaskProfile
from orchestrator.prediction import PredictionLayer


def _graph() -> TaskGraph:
    return TaskGraph(
        nodes=[
            TaskNode(
                task_id="plan",
                objective="Plan the task",
                expected_tokens=300,
                expected_latency_ms=50,
                output_contract=OutputContract(
                    produced_fields=["plan"],
                    types={"plan": "string"},
                ),
            ),
            TaskNode(
                task_id="research",
                objective="Research the topic",
                expected_tokens=900,
                expected_latency_ms=150,
                depends_on=["plan"],
                output_contract=OutputContract(
                    produced_fields=["notes"],
                    types={"notes": "string"},
                ),
            ),
        ],
        root_task_id="plan",
        final_task_id="research",
    )


def test_prediction_layer_uses_graph_and_task_profile_priors() -> None:
    layer = PredictionLayer()
    profile = TaskProfile(task_type="research", complexity="high")

    prediction = layer.predict(
        profile,
        graph=_graph(),
        budget=PipelineBudget(total_tokens=15_000),
    )

    assert prediction.expected_tokens.value >= 1200
    assert prediction.expected_latency_ms.value >= 200
    assert prediction.probability_of_repair == 0.30
    assert prediction.probability_of_retrieval_needed == 0.90
    assert prediction.calibration_confidence >= 0.20


def test_prediction_layer_records_expected_vs_actual_telemetry() -> None:
    layer = PredictionLayer()
    profile = TaskProfile(task_type="coding", complexity="medium")
    prediction = layer.predict(profile, graph=_graph(), budget=PipelineBudget(total_tokens=15_000))

    telemetry = layer.record_actuals(
        prediction,
        actual_cost=prediction.expected_cost.value,
        actual_latency_ms=prediction.expected_latency_ms.value - 100,
        actual_tokens=int(prediction.expected_tokens.value - 50),
        actual_confidence=0.82,
    )

    assert telemetry["prediction.cost.actual"] == prediction.expected_cost.value
    assert telemetry["prediction.cost.within_upper_bound"] is True
    assert telemetry["prediction.tokens.actual"] == int(prediction.expected_tokens.value - 50)
    assert "prediction.calibration_confidence" in telemetry
