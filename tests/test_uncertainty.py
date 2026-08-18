from __future__ import annotations

from core.schemas import Prediction, PredictionInterval, StageAssessment, TaskProfile
from orchestrator.uncertainty import UncertaintyEngine


def test_uncertainty_engine_emits_clarification_request_for_ambiguous_prompt() -> None:
    engine = UncertaintyEngine()

    decision = engine.evaluate(
        user_query="Fix this.",
        task_profile=TaskProfile(task_type="coding", complexity="medium", requires_code_context=True),
        available_context_keys=[],
    )

    assert decision.outcome == "ask_user_clarification"
    assert decision.clarification_request is not None
    assert decision.clarification_request.status == "needs_clarification"
    assert "target file or function" in decision.clarification_request.missing_context


def test_uncertainty_engine_requests_retrieval_when_prediction_requires_it() -> None:
    engine = UncertaintyEngine()
    prediction = Prediction(
        expected_cost=PredictionInterval(value=0.1),
        expected_latency_ms=PredictionInterval(value=1000),
        expected_tokens=PredictionInterval(value=1000),
        expected_confidence=PredictionInterval(value=0.8),
        probability_of_retrieval_needed=0.9,
    )

    decision = engine.evaluate(
        user_query="Research the latest tradeoffs.",
        task_profile=TaskProfile(task_type="research", complexity="high", requires_rag=True),
        prediction=prediction,
        available_context_keys=["task_profile"],
    )

    assert decision.outcome == "run_retrieval"


def test_uncertainty_engine_requests_additional_checker_on_light_contradiction() -> None:
    engine = UncertaintyEngine()
    assessment = StageAssessment(
        confidence=0.92,
        calibration=0.84,
        agreement=0.5,
        contradiction_score=0.03,
    )

    decision = engine.evaluate(
        user_query="Verify the result.",
        task_profile=TaskProfile(task_type="math", complexity="medium", requires_math_check=True),
        stage_assessment=assessment,
        available_context_keys=["task_profile", "strategic_plan"],
    )

    assert decision.outcome == "run_additional_checker"


def test_uncertainty_engine_can_synthesize_with_uncertainty() -> None:
    engine = UncertaintyEngine()
    assessment = StageAssessment(
        confidence=0.8,
        calibration=0.6,
        unsupported_claim_count=1,
    )

    decision = engine.evaluate(
        user_query="Summarize what we know so far.",
        task_profile=TaskProfile(task_type="general", complexity="medium"),
        stage_assessment=assessment,
        available_context_keys=["task_profile"],
    )

    assert decision.outcome == "synthesize_with_uncertainty"
