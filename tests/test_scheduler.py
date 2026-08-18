from __future__ import annotations

import asyncio

import pytest

from core.schemas import TaskGraph, TaskNode
from orchestrator.contracts import OutputContract
from orchestrator.scheduler import Scheduler


def _node(
    task_id: str,
    *,
    depends_on: list[str] | None = None,
    priority: str = "normal",
    can_run_parallel: bool = True,
) -> TaskNode:
    return TaskNode(
        task_id=task_id,
        objective=f"objective for {task_id}",
        depends_on=depends_on or [],
        priority=priority,
        can_run_parallel=can_run_parallel,
        output_contract=OutputContract(produced_fields=["result"], types={"result": "string"}),
    )


async def _executor(node: TaskNode, prior_results: dict[str, object]) -> str:
    await asyncio.sleep(0)
    return node.task_id


@pytest.mark.asyncio
async def test_scheduler_telemetry_counts_started_completed_failed() -> None:
    async def executor(node: TaskNode, prior_results: dict[str, object]) -> str:
        if node.task_id == "boom":
            raise RuntimeError("planned failure")
        return node.task_id

    graph = TaskGraph(
        nodes=[_node("a"), _node("b"), _node("boom", depends_on=["a"], can_run_parallel=False)],
        root_task_id="a",
        final_task_id="boom",
    )
    scheduler = Scheduler(executor=executor, concurrency_limit=2)

    with pytest.raises(RuntimeError):
        await scheduler.run(graph)

    telemetry = scheduler.telemetry
    assert telemetry["execution.node.completed"] == 2  # a, b
    assert telemetry["execution.node.failed"] == 1  # boom
    assert telemetry["execution.node.started"] == 3  # all three entered a worker


@pytest.mark.asyncio
async def test_scheduler_telemetry_queued_equals_released_for_linear_graph() -> None:
    graph = TaskGraph(
        nodes=[
            _node("plan"),
            _node("implement", depends_on=["plan"], can_run_parallel=False),
            _node("verify", depends_on=["implement"], can_run_parallel=False),
        ],
        root_task_id="plan",
        final_task_id="verify",
    )
    scheduler = Scheduler(executor=_executor, concurrency_limit=3)

    await scheduler.run(graph)

    telemetry = scheduler.telemetry
    assert telemetry["scheduler.node.queued"] == 3
    assert telemetry["scheduler.node.released"] == 3
    assert telemetry["scheduler.node.queued"] == telemetry["scheduler.node.released"]


@pytest.mark.asyncio
async def test_scheduler_telemetry_priority_band_histogram_matches_graph() -> None:
    graph = TaskGraph(
        nodes=[
            _node("a", priority="critical"),
            _node("b", priority="high"),
            _node("c", priority="normal", depends_on=["a"], can_run_parallel=False),
            _node("d", priority="normal", depends_on=["b"], can_run_parallel=False),
        ],
        root_task_id="a",
        final_task_id="d",
    )
    scheduler = Scheduler(executor=_executor, concurrency_limit=4)

    await scheduler.run(graph)

    band = scheduler.telemetry["scheduler.priority_band"]
    assert band == {"critical": 1, "high": 1, "normal": 2}
    assert scheduler.telemetry["scheduler.starvation_promoted"] >= 0
