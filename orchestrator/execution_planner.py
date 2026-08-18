"""Rule-based ExecutionPlanner for Step 5.

Converts a StrategicPlan or deterministic template into a validated TaskGraph.
"""

from __future__ import annotations

from typing import Any

from core.schemas import PipelineBudget, StrategicPlan, TaskGraph, TaskNode, TaskProfile
from orchestrator.contracts import FailureContract, InputContract, OutputContract
from orchestrator.routing import get_template, validate_or_fallback
from orchestrator.skills import SkillComposer, SkillComposition


def _input_contract(*required_fields: str) -> InputContract:
    return InputContract(required_fields=list(required_fields), allowed_types=["dict"], validation_rules={})


def _output_contract(*produced_fields: str) -> OutputContract:
    return OutputContract(
        produced_fields=list(produced_fields),
        types={field: "string" for field in produced_fields},
    )


def _failure_contract() -> FailureContract:
    return FailureContract(
        failure_modes=["timeout", "validation_error", "provider_down", "rate_limited"],
        response_shape="repair_request",
    )


class ExecutionPlanner:
    """Convert planning inputs into a validated TaskGraph."""

    version = "execution-planner-v1"

    def __init__(self, skill_composer: SkillComposer | None = None) -> None:
        self._skill_composer = skill_composer or SkillComposer()
        self._last_skill_plan: dict[str, SkillComposition] = {}
        self._last_graph_valid: bool = True
        self._last_fallback_used: bool = False

    @property
    def last_skill_plan(self) -> dict[str, SkillComposition]:
        return {
            node_id: composition.model_copy(deep=True)
            for node_id, composition in self._last_skill_plan.items()
        }

    @property
    def last_planner_telemetry(self) -> dict[str, Any]:
        """``planner.output.*`` / ``planner.template.fallback`` (RFC-005 §4.1)."""
        return {
            "planner.output.valid": self._last_graph_valid,
            "planner.output.invalid": not self._last_graph_valid,
            "planner.template.fallback": self._last_fallback_used,
        }

    def create_graph(
        self,
        task_profile: TaskProfile,
        *,
        strategic_plan: StrategicPlan | None = None,
        budget: PipelineBudget | None = None,
        enable_skill_composition: bool = False,
        force_skills: list[str] | None = None,
        block_skills: list[str] | None = None,
    ) -> TaskGraph:
        if strategic_plan is None:
            graph, used_fallback, _errors = validate_or_fallback(
                get_template(task_profile),
                route=task_profile.task_type,
                complexity=task_profile.complexity,
            )
            self._last_fallback_used = used_fallback
            self._last_graph_valid = not used_fallback
            graph.planner_version = self.version
            return self._apply_skill_composition(
                graph,
                task_profile,
                strategic_plan=None,
                enabled=enable_skill_composition,
                force_skills=force_skills,
                block_skills=block_skills,
            )

        graph = self._build_graph_from_strategic_plan(task_profile, strategic_plan, budget or PipelineBudget())  # noqa: E501
        validated_graph, used_fallback, _errors = validate_or_fallback(
            graph,
            route=task_profile.task_type,
            complexity=task_profile.complexity,
        )
        self._last_fallback_used = used_fallback
        self._last_graph_valid = not used_fallback
        validated_graph.planner_version = self.version
        return self._apply_skill_composition(
            validated_graph,
            task_profile,
            strategic_plan=strategic_plan,
            enabled=enable_skill_composition,
            force_skills=force_skills,
            block_skills=block_skills,
        )

    def _apply_skill_composition(
        self,
        graph: TaskGraph,
        task_profile: TaskProfile,
        *,
        strategic_plan: StrategicPlan | None,
        enabled: bool,
        force_skills: list[str] | None,
        block_skills: list[str] | None,
    ) -> TaskGraph:
        if not enabled:
            self._last_skill_plan = {}
            return graph
        graph, skill_plan = self._skill_composer.apply_to_graph(
            graph,
            task_profile,
            strategic_plan=strategic_plan,
            force_skills=force_skills,
            block_skills=block_skills,
        )
        self._last_skill_plan = skill_plan
        return graph

    def _build_graph_from_strategic_plan(
        self,
        task_profile: TaskProfile,
        strategic_plan: StrategicPlan,
        budget: PipelineBudget,
    ) -> TaskGraph:
        nodes: list[TaskNode] = [
            self._make_node(
                "classify",
                "Carry forward the request classification",
                skills=["caveman"],
                tier="fast",
                priority="normal",
                output_fields=("task_profile",),
                expected_tokens=max(50, int(budget.total_tokens * 0.01)),
                expected_latency_ms=10,
            ),
            self._make_node(
                "plan",
                "Materialize the strategic plan into graph-ready tasks",
                depends_on=["classify"],
                skills=strategic_plan.required_skills or ["explainer"],
                tier="default",
                priority="high" if task_profile.complexity in {"high", "critical"} else "normal",
                input_fields=("request", "task_profile"),
                output_fields=("strategic_plan",),
                expected_tokens=max(100, int(budget.total_tokens * 0.05)),
                expected_latency_ms=25,
            ),
        ]

        dependency_anchor = "plan"
        work_node_ids: list[str] = []
        parallel_budget = max(1, min(3, len(strategic_plan.sub_problems)))
        for index, sub_problem in enumerate(strategic_plan.sub_problems, start=1):
            task_id = f"work_{index}"
            depends_on = [dependency_anchor]
            can_parallel = index <= parallel_budget
            if not can_parallel and work_node_ids:
                depends_on = [work_node_ids[-1]]
            work_node_ids.append(task_id)
            nodes.append(
                self._make_node(
                    task_id,
                    sub_problem,
                    depends_on=depends_on,
                    skills=strategic_plan.required_skills or ["explainer"],
                    tier=self._choose_tier(task_profile),
                    priority="high",
                    input_fields=("strategic_plan",),
                    output_fields=(f"sub_result_{index}",),
                    can_run_parallel=can_parallel,
                    expected_tokens=max(150, int(budget.total_tokens * 0.12)),
                    expected_latency_ms=75,
                )
            )

        aggregate_deps = work_node_ids or [dependency_anchor]
        nodes.append(
            self._make_node(
                "final",
                "Assemble the final response from completed work",
                depends_on=aggregate_deps,
                skills=["precision"],
                tier="default",
                priority="high",
                input_fields=tuple(f"sub_result_{index}" for index in range(1, len(work_node_ids) + 1)) or ("strategic_plan",),  # noqa: E501
                output_fields=("final_response",),
                can_run_parallel=False,
                expected_tokens=max(100, int(budget.total_tokens * 0.05)),
                expected_latency_ms=30,
            )
        )

        return TaskGraph(
            nodes=nodes,
            root_task_id="classify",
            final_task_id="final",
            planner_version=self.version,
        )

    def _make_node(
        self,
        task_id: str,
        objective: str,
        *,
        depends_on: list[str] | None = None,
        skills: list[str] | None = None,
        tier: str,
        priority: str,
        input_fields: tuple[str, ...] = ("request",),
        output_fields: tuple[str, ...] = ("result",),
        can_run_parallel: bool | None = None,
        expected_tokens: int | None = None,
        expected_latency_ms: int | None = None,
    ) -> TaskNode:
        deps = depends_on or []
        return TaskNode(
            task_id=task_id,
            objective=objective,
            skills_required=skills or [],
            model_tier=tier,
            depends_on=deps,
            can_run_parallel=(not deps if can_run_parallel is None else can_run_parallel),
            priority=priority,
            input_contract=_input_contract(*input_fields),
            output_contract=_output_contract(*output_fields),
            failure_contract=_failure_contract(),
            expected_tokens=expected_tokens,
            expected_latency_ms=expected_latency_ms,
        )

    @staticmethod
    def _choose_tier(task_profile: TaskProfile) -> str:
        if task_profile.complexity == "critical":
            return "critical"
        if task_profile.complexity == "high":
            return "powerful"
        if task_profile.complexity == "low":
            return "cheap"
        return "default"
