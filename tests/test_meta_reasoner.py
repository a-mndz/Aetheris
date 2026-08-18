from __future__ import annotations

import asyncio

import pytest

from core.schemas import PipelineBudget, StageAssessment, TaskGraph, TaskNode, TaskProfile
from orchestrator.contracts import OutputContract
from orchestrator.meta_reasoner import MetaReasoner
from orchestrator.scheduler import Scheduler


def _node(
    task_id: str,
    *,
    depends_on: list[str] | None = None,
    priority: str = "normal",
    tier: str = "default",
    skills: list[str] | None = None,
    objective: str | None = None,
) -> TaskNode:
    return TaskNode(
        task_id=task_id,
        objective=objective or task_id,
        depends_on=depends_on or [],
        priority=priority,
        model_tier=tier,
        skills_required=skills or ["precision"],
        output_contract=OutputContract(produced_fields=["result"], types={"result": "string"}),
    )


def test_meta_reasoner_early_exit_passes_all_thresholds() -> None:
    meta = MetaReasoner()
    assessment = StageAssessment(
        confidence=0.98,
        calibration=0.90,
        evidence_strength=0.75,
        agreement=0.70,
        stability=0.60,
        reasoning_quality="strong",
        evidence_count=2,
        contradiction_score=0.0,
        unsupported_claim_count=0,
    )

    decision = meta.evaluate_early_exit(assessment, route="research", complexity="medium")

    assert decision.can_exit_early is True
    assert decision.recommended_judge_count == 0
    assert decision.thresholds_failed == []


def test_meta_reasoner_early_exit_escalates_on_contradiction() -> None:
    meta = MetaReasoner()
    assessment = StageAssessment(
        confidence=0.99,
        calibration=0.95,
        evidence_strength=0.80,
        agreement=0.80,
        stability=0.70,
        reasoning_quality="strong",
        evidence_count=2,
        contradiction_score=0.20,
        unsupported_claim_count=1,
    )

    decision = meta.evaluate_early_exit(assessment, route="research", complexity="medium")

    assert decision.can_exit_early is False
    assert decision.triggered_by_contradiction is True
    assert decision.escalate_complexity_to == "high"
    assert decision.recommended_judge_count == 4


def test_meta_reasoner_respects_mutation_bounds_and_records_audit_trail() -> None:
    meta = MetaReasoner()
    profile = TaskProfile(task_type="coding", complexity="low")
    graph = TaskGraph(
        nodes=[
            _node("classify", priority="normal", tier="critical", skills=["caveman"]),
            _node("redundant_a", depends_on=["classify"], priority="background", tier="critical", objective="same", skills=["precision"]),  # noqa: E501
            _node("redundant_b", depends_on=["redundant_a"], priority="background", tier="critical", objective="same", skills=["precision"]),  # noqa: E501
            _node("verify", depends_on=["redundant_b"], priority="background", tier="critical"),
            _node("final", depends_on=["verify"], priority="high", tier="critical", skills=["precision"]),
        ],
        root_task_id="classify",
        final_task_id="final",
    )
    budget = PipelineBudget(pressure="critical")
    decision = meta.evaluate_early_exit(
        StageAssessment(
            confidence=0.98,
            calibration=0.90,
            evidence_strength=0.60,
            agreement=0.70,
            stability=0.60,
            reasoning_quality="strong",
            evidence_count=1,
            contradiction_score=0.0,
            unsupported_claim_count=0,
        ),
        route="coding",
        complexity="low",
    )

    result = meta.optimize_graph(graph, task_profile=profile, budget=budget, early_exit=decision)

    assert result.mutations_applied <= 3
    assert len(result.mutation_audit_trail) <= 3
    assert any(record.mutation_type in {"skip_stage", "downgrade_tier", "merge_nodes", "reorder"} for record in result.mutation_audit_trail)  # noqa: E501


@pytest.mark.asyncio
async def test_scheduler_auto_promotes_starved_background_tasks() -> None:
    order: list[str] = []

    async def executor(node: TaskNode, prior_results: dict[str, object]) -> str:
        order.append(node.task_id)
        await asyncio.sleep(0.01)
        return node.task_id

    graph = TaskGraph(
        nodes=[
            _node("background", priority="background"),
            _node("normal", priority="normal"),
        ],
        root_task_id="background",
        final_task_id="normal",
    )
    scheduler = Scheduler(
        executor=executor,
        concurrency_limit=1,
        starvation_promote_after_seconds=0.0,
    )

    await scheduler.run(graph)

    assert order == ["background", "normal"]
