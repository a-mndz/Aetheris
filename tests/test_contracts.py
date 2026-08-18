from __future__ import annotations

from core.schemas import TaskNode
from orchestrator.contracts import (
    FailureContract,
    InputContract,
    OutputContract,
    classify_failure,
    to_failure_response,
    validate_inputs,
    validate_outputs,
)


def _node() -> TaskNode:
    return TaskNode(
        task_id="work_1",
        objective="do the work",
        input_contract=InputContract(required_fields=["strategic_plan", "sub_result_0"]),
        output_contract=OutputContract(produced_fields=["sub_result_1"], types={"sub_result_1": "string"}),
        failure_contract=FailureContract(failure_modes=["timeout"], response_shape="repair_request"),
    )


def test_ambient_input_satisfied_but_produced_missing() -> None:
    # strategic_plan is ambient (always supplied); sub_result_0 must come upstream.
    violations = validate_inputs(_node(), incoming_outputs={})
    assert [v.field for v in violations] == ["sub_result_0"]


def test_input_satisfied_when_upstream_produced() -> None:
    assert validate_inputs(_node(), {"sub_result_0": "x"}) == []


def test_missing_output_flagged() -> None:
    assert [v.field for v in validate_outputs(_node(), {})] == ["sub_result_1"]
    assert validate_outputs(_node(), {"sub_result_1": "done"}) == []


def test_output_type_mismatch_flagged() -> None:
    violations = validate_outputs(_node(), {"sub_result_1": {"not": "text"}})
    assert [(violation.kind, violation.field) for violation in violations] == [
        ("type_mismatch", "sub_result_1")
    ]


def test_failure_classification_recoverable_vs_not() -> None:
    assert classify_failure("timeout").failure_class == "recoverable"
    assert classify_failure("timeout").action == "retry_with_backoff"
    assert classify_failure("auth_error").failure_class == "non_recoverable"
    # unlisted mode fails safe (non_recoverable), not open.
    assert classify_failure("who_knows").failure_class == "non_recoverable"


def test_to_failure_response_shape() -> None:
    resp = to_failure_response(_node(), "timeout")
    assert resp == {
        "task_id": "work_1",
        "status": "failed",
        "failure_mode": "timeout",
        "failure_class": "recoverable",
        "action": "retry_with_backoff",
        "response_shape": "repair_request",
    }
