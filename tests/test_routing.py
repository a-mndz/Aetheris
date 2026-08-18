from __future__ import annotations

from core.schemas import TaskGraph, TaskNode, TaskProfile
from orchestrator.contracts import OutputContract
from orchestrator.routing import (
    IntentAnalyzer,
    get_template,
    validate_or_fallback,
    validate_task_graph,
)


def _node(task_id: str, *, depends_on: list[str] | None = None) -> TaskNode:
    return TaskNode(
        task_id=task_id,
        objective=f"objective for {task_id}",
        depends_on=depends_on or [],
        output_contract=OutputContract(produced_fields=["result"], types={"result": "string"}),
    )


def test_intent_analyzer_classifies_coding_request() -> None:
    profile = IntentAnalyzer.classify("Fix the traceback in server.py and add a pytest regression test.")

    assert profile.task_type == "coding"
    assert profile.requires_code_context is True
    assert profile.needs_decomposition is True


def test_intent_analyzer_classifies_research_request() -> None:
    profile = IntentAnalyzer.classify("Research current sources comparing vector databases and cite the tradeoffs.")  # noqa: E501

    assert profile.task_type == "research"
    assert profile.requires_rag is True
    assert profile.complexity in {"high", "critical"}


def test_intent_analyzer_classifies_math_request() -> None:
    profile = IntentAnalyzer.classify("Solve the equation 3x + 5 = 17 and verify the result.")

    assert profile.task_type == "math"
    assert profile.requires_math_check is True


def test_intent_analyzer_classifies_creative_request() -> None:
    profile = IntentAnalyzer.classify("Write three tagline options for a security startup brand refresh.")

    assert profile.task_type == "creative"
    assert profile.requires_creativity is True


def test_intent_analyzer_falls_back_to_general_request() -> None:
    profile = IntentAnalyzer.classify("What time does the release window open tomorrow?")

    assert profile.task_type == "general"
    assert profile.complexity == "low"
    assert profile.needs_decomposition is False


def test_route_templates_validate() -> None:
    for route in ["coding", "research", "math", "creative", "general"]:
        graph = get_template(route)
        is_valid, errors = validate_task_graph(graph, complexity="medium")
        assert is_valid, f"{route} template should validate: {errors}"


def test_templates_accept_task_profile_and_validate() -> None:
    for route in ["coding", "research", "math", "creative", "general"]:
        profile = TaskProfile(task_type=route, complexity="medium")
        graph = get_template(profile)
        is_valid, errors = validate_task_graph(graph, complexity="medium")
        assert is_valid, f"{route} template should validate for a TaskProfile: {errors}"
        assert "judge" not in {node.task_id for node in graph.nodes}


def test_high_complexity_profile_adds_route_judge() -> None:
    for complexity in ["high", "critical"]:
        profile = TaskProfile(task_type="coding", complexity=complexity)
        graph = get_template(profile)
        node_ids = {node.task_id for node in graph.nodes}
        assert "judge" in node_ids
        final = next(node for node in graph.nodes if node.task_id == graph.final_task_id)
        assert final.depends_on == ["judge"]
        is_valid, errors = validate_task_graph(graph, complexity=complexity)
        assert is_valid, errors


def test_validate_task_graph_rejects_cycle() -> None:
    graph = TaskGraph(
        nodes=[
            _node("plan", depends_on=["verify"]),
            _node("verify", depends_on=["plan"]),
        ],
        root_task_id="plan",
        final_task_id="verify",
    )

    is_valid, errors = validate_task_graph(graph)
    assert is_valid is False
    assert any("Cycle detected" in error for error in errors)


def test_validate_task_graph_rejects_missing_dependency() -> None:
    graph = TaskGraph(
        nodes=[_node("implement", depends_on=["missing"]), _node("final", depends_on=["implement"])],
        root_task_id="implement",
        final_task_id="final",
    )

    is_valid, errors = validate_task_graph(graph)
    assert is_valid is False
    assert "Missing dependency: implement -> missing" in errors


def test_validate_task_graph_rejects_unknown_skill() -> None:
    graph = TaskGraph(
        nodes=[
            TaskNode(
                task_id="plan",
                objective="plan",
                skills_required=["unknown_skill"],
                output_contract=OutputContract(produced_fields=["result"], types={"result": "string"}),
            ),
            _node("final", depends_on=["plan"]),
        ],
        root_task_id="plan",
        final_task_id="final",
    )

    is_valid, errors = validate_task_graph(graph)
    assert is_valid is False
    assert "Unknown skill 'unknown_skill' on node 'plan'" in errors


def test_validate_task_graph_rejects_missing_final_node() -> None:
    graph = TaskGraph(nodes=[_node("plan")], root_task_id="plan", final_task_id="final")

    is_valid, errors = validate_task_graph(graph)
    assert is_valid is False
    assert "final_task_id 'final' not in nodes" in errors


def test_validate_task_graph_rejects_missing_output_contract() -> None:
    graph = TaskGraph(
        nodes=[TaskNode(task_id="plan", objective="plan"), _node("final", depends_on=["plan"])],
        root_task_id="plan",
        final_task_id="final",
    )

    is_valid, errors = validate_task_graph(graph)
    assert is_valid is False
    assert "Node 'plan' has no output contract" in errors


def test_validate_or_fallback_uses_deterministic_template() -> None:
    invalid_graph = TaskGraph(nodes=[_node("plan")], root_task_id="plan", final_task_id="missing")

    graph, used_fallback, errors = validate_or_fallback(invalid_graph, route="coding", complexity="medium")

    assert used_fallback is True
    assert errors == ["final_task_id 'missing' not in nodes"]
    assert graph.final_task_id == "final"
    assert {node.task_id for node in graph.nodes} >= {"classify", "plan", "implement", "verify", "final"}
