"""Deterministic routing and graph-template fallback logic.

This module implements the token-free ``IntentAnalyzer`` from RFC-002 and the
TaskGraph validation / template fallback rules from RFC-003.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable

from core.schemas import TaskGraph, TaskNode, TaskProfile
from orchestrator.contracts import FailureContract, InputContract, OutputContract
from orchestrator.skills import KNOWN_SKILL_NAMES

RouteName = str
ComplexityName = str

_ROUTE_PATTERNS: dict[RouteName, tuple[str, ...]] = {
    "coding": (
        r"\b(?:stack trace|traceback|exception|error code|compile error|lint)\b",
        r"\b(?:repo|repository|codebase|refactor|debug|implement|function|class|method|endpoint|sql|query)\b",
        r"\b(?:pytest|unittest|alembic|migration|dockerfile|typescript|javascript|python|fastapi|react)\b",
        r"(?:^|\s)(?:src|tests|docs|config|api_gateway|orchestrator|core)[/\\]",
        r"\b[a-z0-9_./\\-]+\.(?:py|ts|tsx|js|jsx|sql|json|yaml|yml|toml|md)\b",
        r"\b(?:git|npm|pnpm|pip|pytest|uvicorn)\b",
    ),
    "research": (
        r"\b(?:according to|cite|citation|citations|reference|references|sources?)\b",
        r"\b(?:study|studies|paper|papers|survey|literature|evidence|current events?)\b",
        r"\b(?:summarize|compare|research|investigate|find sources?|background)\b",
    ),
    "math": (
        r"\b(?:equation|formula|solve|proof|prove|derivative|integral|matrix|vector|probability|theorem)\b",
        r"\b(?:calculate|compute|simplify|differentiate|integrate)\b",
        r"(?:\d+\s*[+\-*/=]\s*\d+|\b(?:sin|cos|tan|log)\s*\()",
    ),
    "creative": (
        r"\b(?:brand|branding|logo|headline|tagline|campaign|copy|story|poem|script|narrative)\b",
        r"\b(?:design|concept|voice|tone|slogan|character|dialogue|name ideas?)\b",
        r"\b(?:brainstorm|rewrite for tone|creative direction)\b",
    ),
}

_CRITICAL_PATTERNS: tuple[str, ...] = (
    r"\b(?:security|credential|credentials|secret|token|password|auth bypass|exploit|cve)\b",
    r"\b(?:finance|financial|medical|legal|compliance|regulatory)\b",
    r"\b(?:production|prod)\b.*\b(?:incident|outage|database|data loss|migration)\b",
    r"\b(?:drop database|delete production|rm\s+-rf|destructive)\b",
)

_HIGH_PATTERNS: tuple[str, ...] = (
    r"\b(?:multi-step|multiple constraints|cross-functional|distributed|architecture)\b",
    r"\b(?:migrate|migration|rollout|performance audit|security audit)\b",
    r"\b(?:high ambiguity|ambiguous|tradeoff|compare approaches)\b",
    r"\b(?:current|latest)\b.*\b(?:sources?|research|compare|tradeoffs?)\b",
    r"\b(?:fix|implement|debug|refactor)\b.*\b(?:test|regression|verify)\b",
)

_LOW_PATTERNS: tuple[str, ...] = (
    r"\b(?:what is|who is|define|quickly|simple|short answer|briefly)\b",
)

_DECOMPOSITION_HINTS: tuple[str, ...] = (
    r"\b(?:and then|step by step|phases?|roadmap|plan)\b",
    r"\b(?:compare|tradeoff|evaluate|investigate)\b",
    r"\b(?:multiple|several|across)\b",
)

_KNOWN_SKILLS: frozenset[str] = frozenset(KNOWN_SKILL_NAMES)

_KNOWN_TIERS: frozenset[str] = frozenset({"default", "fast", "powerful", "cheap", "critical"})

_NODE_CAP_BY_COMPLEXITY: dict[ComplexityName, int] = {
    "low": 5,
    "medium": 8,
    "high": 12,
    "critical": 16,
}


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _count_matches(text: str, patterns: Iterable[str]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text))


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


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


def _node(
    task_id: str,
    objective: str,
    *,
    depends_on: list[str] | None = None,
    skills: list[str] | None = None,
    tier: str = "default",
    priority: str = "normal",
    input_fields: tuple[str, ...] = ("request",),
    output_fields: tuple[str, ...] = ("result",),
) -> TaskNode:
    deps = depends_on or []
    return TaskNode(
        task_id=task_id,
        objective=objective,
        skills_required=skills or [],
        model_tier=tier,
        depends_on=deps,
        can_run_parallel=not deps,
        priority=priority,
        input_contract=_input_contract(*input_fields),
        output_contract=_output_contract(*output_fields),
        failure_contract=_failure_contract(),
    )


class IntentAnalyzer:
    """Deterministic, token-free request classifier."""

    @classmethod
    def detect_route(cls, query: str) -> RouteName:
        query_lower = query.lower()
        scores = Counter(
            {
                route: _count_matches(query_lower, patterns)
                for route, patterns in _ROUTE_PATTERNS.items()
            }
        )
        route, score = scores.most_common(1)[0] if scores else ("general", 0)
        return route if score > 0 else "general"

    @classmethod
    def score_complexity(cls, query: str, route: RouteName | None = None) -> ComplexityName:
        query_lower = query.lower()
        inferred_route = route or cls.detect_route(query)

        if _matches_any(query_lower, _CRITICAL_PATTERNS):
            return "critical"
        if _matches_any(query_lower, _HIGH_PATTERNS):
            return "high"

        complexity_points = 0
        if _matches_any(query_lower, _LOW_PATTERNS):
            complexity_points -= 1
        if _matches_any(query_lower, _DECOMPOSITION_HINTS):
            complexity_points += 2
        if inferred_route in {"coding", "research", "math"}:
            complexity_points += 1
        if len(re.findall(r"[,;:]", query)) >= 2:
            complexity_points += 1
        if _word_count(query_lower) >= 35:
            complexity_points += 1

        if complexity_points >= 3:
            return "high"
        if complexity_points <= 0:
            return "low"
        return "medium"

    @classmethod
    def needs_decomposition(cls, query: str, route: RouteName | None = None, complexity: ComplexityName | None = None) -> bool:  # noqa: E501
        inferred_route = route or cls.detect_route(query)
        inferred_complexity = complexity or cls.score_complexity(query, inferred_route)
        if inferred_complexity in {"high", "critical"}:
            return True
        query_lower = query.lower()
        if _matches_any(query_lower, _DECOMPOSITION_HINTS):
            return True
        return inferred_route in {"research", "coding"} and (
            _word_count(query_lower) >= 12
            or len(re.findall(r"\band\b", query_lower)) >= 1
        )

    @classmethod
    def classify(cls, query: str) -> TaskProfile:
        route = cls.detect_route(query)
        complexity = cls.score_complexity(query, route)
        return TaskProfile(
            task_type=route,
            complexity=complexity,
            criticality="high" if complexity == "critical" else "low",
            needs_decomposition=cls.needs_decomposition(query, route, complexity),
            requires_rag=route == "research",
            requires_code_context=route == "coding",
            requires_math_check=route == "math",
            requires_creativity=route == "creative",
        )


def build_coding_template() -> TaskGraph:
    return TaskGraph(
        nodes=[
            _node("classify", "Classify the coding request", skills=["caveman"], tier="fast", output_fields=("task_profile",)),  # noqa: E501
            _node(
                "plan",
                "Create an implementation plan",
                depends_on=["classify"],
                skills=["coder"],
                input_fields=("request", "task_profile"),
                output_fields=("implementation_plan",),
            ),
            _node(
                "code_context",
                "Gather the relevant code context",
                depends_on=["classify"],
                skills=["coder"],
                tier="fast",
                input_fields=("request", "task_profile"),
                output_fields=("code_context",),
            ),
            _node(
                "implement",
                "Implement the requested code changes",
                depends_on=["plan", "code_context"],
                skills=["coder"],
                priority="high",
                input_fields=("implementation_plan", "code_context"),
                output_fields=("implementation_result",),
            ),
            _node(
                "verify",
                "Verify the code behavior",
                depends_on=["implement"],
                skills=["precision"],
                input_fields=("implementation_result",),
                output_fields=("verification_result",),
            ),
            _node(
                "final",
                "Produce the final coding response",
                depends_on=["verify"],
                input_fields=("verification_result",),
                output_fields=("final_response",),
            ),
        ],
        root_task_id="classify",
        final_task_id="final",
    )


def build_research_template() -> TaskGraph:
    return TaskGraph(
        nodes=[
            _node("classify", "Classify the research request", skills=["caveman"], tier="fast", output_fields=("task_profile",)),  # noqa: E501
            _node(
                "plan",
                "Plan the research approach",
                depends_on=["classify"],
                skills=["researcher"],
                input_fields=("request", "task_profile"),
                output_fields=("research_plan",),
            ),
            _node(
                "retrieve",
                "Retrieve candidate sources",
                depends_on=["plan"],
                skills=["researcher"],
                input_fields=("research_plan",),
                output_fields=("candidate_sources",),
            ),
            _node(
                "rank_sources",
                "Rank and filter sources",
                depends_on=["retrieve"],
                skills=["precision"],
                tier="fast",
                input_fields=("candidate_sources",),
                output_fields=("ranked_sources",),
            ),
            _node(
                "synthesize",
                "Synthesize the research findings",
                depends_on=["rank_sources"],
                skills=["academic", "researcher"],
                priority="high",
                input_fields=("ranked_sources",),
                output_fields=("synthesized_findings",),
            ),
            _node(
                "evidence_check",
                "Check that claims are supported by evidence",
                depends_on=["synthesize"],
                skills=["precision", "researcher"],
                input_fields=("synthesized_findings",),
                output_fields=("evidence_report",),
            ),
            _node(
                "final",
                "Produce the final research response",
                depends_on=["evidence_check"],
                input_fields=("evidence_report",),
                output_fields=("final_response",),
            ),
        ],
        root_task_id="classify",
        final_task_id="final",
    )


def build_math_template() -> TaskGraph:
    return TaskGraph(
        nodes=[
            _node("classify", "Classify the math request", skills=["caveman"], tier="fast", output_fields=("task_profile",)),  # noqa: E501
            _node(
                "plan",
                "Plan the solution approach",
                depends_on=["classify"],
                skills=["precision"],
                input_fields=("request", "task_profile"),
                output_fields=("solution_plan",),
            ),
            _node(
                "solve",
                "Solve the problem step by step",
                depends_on=["plan"],
                skills=["precision"],
                priority="high",
                input_fields=("solution_plan",),
                output_fields=("solution_steps",),
            ),
            _node(
                "independent_check",
                "Independently verify the solution",
                depends_on=["solve"],
                skills=["precision"],
                input_fields=("solution_steps",),
                output_fields=("checked_solution",),
            ),
            _node(
                "contradiction_check",
                "Detect contradictions or invalid reasoning",
                depends_on=["independent_check"],
                skills=["precision"],
                input_fields=("checked_solution",),
                output_fields=("contradiction_report",),
            ),
            _node(
                "final",
                "Produce the final math response",
                depends_on=["contradiction_check"],
                input_fields=("contradiction_report",),
                output_fields=("final_response",),
            ),
        ],
        root_task_id="classify",
        final_task_id="final",
    )


def build_creative_template() -> TaskGraph:
    return TaskGraph(
        nodes=[
            _node("classify", "Classify the creative request", skills=["caveman"], tier="fast", output_fields=("task_profile",)),  # noqa: E501
            _node(
                "plan",
                "Plan the creative direction",
                depends_on=["classify"],
                skills=["explainer"],
                input_fields=("request", "task_profile"),
                output_fields=("creative_brief",),
            ),
            _node(
                "ideate",
                "Generate creative options",
                depends_on=["plan"],
                skills=["explainer"],
                priority="high",
                input_fields=("creative_brief",),
                output_fields=("creative_options",),
            ),
            _node(
                "critique",
                "Apply taste and constraint critique",
                depends_on=["ideate"],
                skills=["devils_advocate"],
                input_fields=("creative_options",),
                output_fields=("creative_review",),
            ),
            _node(
                "final",
                "Produce the final creative response",
                depends_on=["critique"],
                input_fields=("creative_review",),
                output_fields=("final_response",),
            ),
        ],
        root_task_id="classify",
        final_task_id="final",
    )


def build_general_template() -> TaskGraph:
    return TaskGraph(
        nodes=[
            _node("classify", "Classify the general request", skills=["caveman"], tier="fast", output_fields=("task_profile",)),  # noqa: E501
            _node(
                "plan",
                "Plan the response approach",
                depends_on=["classify"],
                skills=["explainer"],
                input_fields=("request", "task_profile"),
                output_fields=("response_plan",),
            ),
            _node(
                "respond",
                "Generate the direct response",
                depends_on=["plan"],
                priority="high",
                input_fields=("response_plan",),
                output_fields=("draft_response",),
            ),
            _node(
                "final",
                "Produce the final general response",
                depends_on=["respond"],
                input_fields=("draft_response",),
                output_fields=("final_response",),
            ),
        ],
        root_task_id="classify",
        final_task_id="final",
    )


_ROUTE_TEMPLATES: dict[RouteName, Callable[[], TaskGraph]] = {
    "coding": build_coding_template,
    "research": build_research_template,
    "math": build_math_template,
    "creative": build_creative_template,
    "general": build_general_template,
}


def _add_judge_before_final(graph: TaskGraph, route: RouteName) -> TaskGraph:
    """Splice one route-specific judge between the verifier(s) and final.

    Implements RFC-002 §9's "optional judge" band — only for high/critical
    complexity — without duplicating a Logician+Creative judge onto every
    route. Templates are freshly built per call, so mutating the nodes is safe.
    """

    final = next(node for node in graph.nodes if node.task_id == graph.final_task_id)
    judge = _node(
        "judge",
        f"Judge the {route} response quality before finalizing",
        depends_on=list(final.depends_on),
        skills=["devils_advocate"],
        input_fields=("result",),
        output_fields=("judge_report",),
    )
    final.depends_on = ["judge"]
    final.can_run_parallel = False
    graph.nodes.insert(len(graph.nodes) - 1, judge)
    return graph


def get_template(route: RouteName | TaskProfile) -> TaskGraph:
    """Build the deterministic template for a route or ``TaskProfile``.

    Accepts a bare route name (back-compat) or a ``TaskProfile``. When given a
    profile, high/critical complexity adds a route-specific judge (RFC-002 §9).
    """

    profile = route if isinstance(route, TaskProfile) else None
    route_name = profile.task_type if profile is not None else route

    graph = _ROUTE_TEMPLATES.get(route_name, build_general_template)()
    if profile is not None and profile.complexity in {"high", "critical"}:
        graph = _add_judge_before_final(graph, route_name)
    return graph


def _find_cycle(nodes: list[TaskNode]) -> list[str] | None:
    node_ids = {node.task_id for node in nodes}
    deps: dict[str, list[str]] = {
        node.task_id: [dep for dep in node.depends_on if dep in node_ids]
        for node in nodes
    }
    white, gray, black = 0, 1, 2
    colour: dict[str, int] = {node_id: white for node_id in node_ids}
    parent: dict[str, str | None] = {node_id: None for node_id in node_ids}

    def dfs(node_id: str) -> list[str] | None:
        colour[node_id] = gray
        for dep in deps.get(node_id, []):
            if colour[dep] == gray:
                path = [dep, node_id]
                current = parent[node_id]
                while current is not None and current != dep:
                    path.append(current)
                    current = parent[current]
                path.append(dep)
                return list(reversed(path))
            if colour[dep] == white:
                parent[dep] = node_id
                cycle_path = dfs(dep)
                if cycle_path:
                    return cycle_path
        colour[node_id] = black
        return None

    for node_id in node_ids:
        if colour[node_id] == white:
            cycle_path = dfs(node_id)
            if cycle_path:
                return cycle_path
    return None


def _missing_dependencies(nodes: list[TaskNode]) -> list[str]:
    node_ids = {node.task_id for node in nodes}
    missing: list[str] = []
    for node in nodes:
        for dep in node.depends_on:
            if dep not in node_ids:
                missing.append(f"{node.task_id} -> {dep}")
    return missing


def validate_task_graph(graph: TaskGraph, complexity: ComplexityName = "medium") -> tuple[bool, list[str]]:
    """Validate a TaskGraph per RFC-003 §2.3."""

    errors: list[str] = []
    nodes = graph.nodes
    node_ids = {node.task_id for node in nodes}

    if not nodes:
        return False, ["Graph has no nodes"]

    if not graph.final_task_id:
        errors.append("Graph has no final_task_id")
    elif graph.final_task_id not in node_ids:
        errors.append(f"final_task_id '{graph.final_task_id}' not in nodes")

    if graph.root_task_id and graph.root_task_id not in node_ids:
        errors.append(f"root_task_id '{graph.root_task_id}' not in nodes")

    if len(node_ids) != len(nodes):
        errors.append("Graph contains duplicate task_id values")

    for node in nodes:
        if not node.objective.strip():
            errors.append(f"Node '{node.task_id}' has no objective")
        if node.output_contract is None or not node.output_contract.produced_fields:
            errors.append(f"Node '{node.task_id}' has no output contract")
        for skill in node.skills_required:
            if skill not in _KNOWN_SKILLS:
                errors.append(f"Unknown skill '{skill}' on node '{node.task_id}'")
        if node.model_tier not in _KNOWN_TIERS:
            errors.append(f"Unknown model tier '{node.model_tier}' on node '{node.task_id}'")

    errors.extend(f"Missing dependency: {missing}" for missing in _missing_dependencies(nodes))

    cycle = _find_cycle(nodes)
    if cycle:
        errors.append(f"Cycle detected: {' -> '.join(cycle)}")

    complexity_cap = _NODE_CAP_BY_COMPLEXITY.get(complexity, _NODE_CAP_BY_COMPLEXITY["medium"])
    if len(nodes) > complexity_cap:
        errors.append(f"Node count {len(nodes)} exceeds complexity cap {complexity_cap}")

    return len(errors) == 0, errors


def validate_or_fallback(
    graph: TaskGraph,
    *,
    route: RouteName,
    complexity: ComplexityName = "medium",
) -> tuple[TaskGraph, bool, list[str]]:
    """Return ``graph`` when valid, otherwise the deterministic route template."""

    is_valid, errors = validate_task_graph(graph, complexity=complexity)
    if is_valid:
        return graph, False, []
    return get_template(route), True, errors
