"""Event-driven DAG scheduler for Step 5.

Workers pull work via ``asyncio.Condition`` and respect a caller-provided
concurrency limit (number of workers = semaphore ceiling). No wave loop.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from core.schemas import TaskGraph, TaskNode

NodeExecutor = Callable[[TaskNode, dict[str, Any]], Awaitable[Any]]

_PRIORITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "normal": 2,
    "background": 3,
}


class Scheduler:
    """Dependency-aware event-driven scheduler backed by ``asyncio.Condition``."""

    def __init__(
        self,
        *,
        executor: NodeExecutor,
        concurrency_limit: int = 4,
        starvation_promote_after_seconds: float = 60.0,
    ) -> None:
        self._executor = executor
        self._concurrency_limit = max(1, concurrency_limit)
        self._starvation_promote_after_seconds = starvation_promote_after_seconds
        self._telemetry: dict[str, Any] = {}

    @property
    def telemetry(self) -> dict[str, Any]:
        """``execution.node.*`` / ``scheduler.*`` (RFC-005 §4.1), populated after ``run()``."""
        return dict(self._telemetry)

    async def run(self, graph: TaskGraph) -> dict[str, Any]:
        node_map = {node.task_id: node for node in graph.nodes}
        dependency_counts = {node.task_id: len(node.depends_on) for node in graph.nodes}
        dependents: dict[str, list[str]] = defaultdict(list)
        for node in graph.nodes:
            for dep in node.depends_on:
                dependents[dep].append(node.task_id)

        total = len(graph.nodes)
        ready_queue: list[tuple[float, str]] = []
        ready_at: dict[str, float] = {}
        seen: set[str] = set()
        running: set[str] = set()
        completed: set[str] = set()
        results: dict[str, Any] = {}
        errors: dict[str, BaseException] = {}
        condition = asyncio.Condition()
        cancelled = False
        bootstrapped = False
        counters = {"queued": 0, "started": 0, "completed": 0, "failed": 0}
        promoted: set[str] = set()

        def _enqueue_unlocked(task_id: str) -> None:
            if task_id in seen or task_id in running or task_id in completed:
                return
            seen.add(task_id)
            ready_at[task_id] = time.monotonic()
            ready_queue.append((ready_at[task_id], task_id))
            counters["queued"] += 1

        def _bootstrap_unlocked() -> None:
            nonlocal bootstrapped
            if bootstrapped:
                return
            bootstrapped = True
            for node in graph.nodes:
                if dependency_counts[node.task_id] == 0:
                    _enqueue_unlocked(node.task_id)

        def _sort_ready_unlocked() -> None:
            now = time.monotonic()

            def key(item: tuple[float, str]) -> tuple[int, float, str]:
                ready_time, task_id = item
                node = node_map[task_id]
                priority = node.priority
                if (
                    priority == "background"
                    and (now - ready_time) >= self._starvation_promote_after_seconds
                ):
                    priority = "normal"
                    promoted.add(task_id)
                return (_PRIORITY_ORDER.get(priority, 2), ready_time, task_id)

            ready_queue.sort(key=key)

        async def mark_completed(task_id: str, value: Any) -> None:
            async with condition:
                running.discard(task_id)
                completed.add(task_id)
                counters["completed"] += 1
                results[task_id] = value
                for dependent_id in dependents.get(task_id, []):
                    dependency_counts[dependent_id] -= 1
                    if dependency_counts[dependent_id] == 0:
                        _enqueue_unlocked(dependent_id)
                condition.notify_all()

        async def mark_failed(task_id: str, exc: BaseException) -> None:
            nonlocal cancelled
            async with condition:
                running.discard(task_id)
                counters["failed"] += 1
                errors[task_id] = exc
                cancelled = True
                condition.notify_all()

        async def worker(worker_index: int) -> None:
            while True:
                async with condition:
                    if not bootstrapped:
                        _bootstrap_unlocked()
                    await condition.wait_for(
                        lambda: cancelled
                        or bool(ready_queue)
                        or len(completed) == total
                    )
                    if cancelled or len(completed) == total:
                        return
                    _sort_ready_unlocked()
                    _, task_id = ready_queue.pop(0)
                    running.add(task_id)
                    counters["started"] += 1
                    node = node_map[task_id]

                task_name = f"scheduler-node-{task_id}-worker-{worker_index}"
                try:
                    execution_task = asyncio.create_task(
                        self._executor(node, dict(results)),
                        name=task_name,
                    )
                    try:
                        value = await execution_task
                    except asyncio.CancelledError:
                        execution_task.cancel()
                        raise
                    await mark_completed(task_id, value)
                except BaseException as exc:
                    await mark_failed(task_id, exc)
                    return

        worker_count = min(self._concurrency_limit, max(1, total))
        if total == 0:
            self._telemetry = {
                "execution.node.started": 0,
                "execution.node.completed": 0,
                "execution.node.failed": 0,
                "scheduler.node.queued": 0,
                "scheduler.node.released": 0,
                "scheduler.priority_band": {},
                "scheduler.starvation_promoted": 0,
            }
            return {}
        worker_tasks = [
            asyncio.create_task(worker(index), name=f"scheduler-worker-{index}")
            for index in range(worker_count)
        ]

        try:
            await asyncio.gather(*worker_tasks)
        finally:
            for task in worker_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        priority_band = defaultdict(int)
        for node in graph.nodes:
            priority_band[node.priority] += 1
        self._telemetry = {
            "execution.node.started": counters["started"],
            "execution.node.completed": counters["completed"],
            "execution.node.failed": counters["failed"],
            "scheduler.node.queued": counters["queued"],
            "scheduler.node.released": counters["started"],
            "scheduler.priority_band": dict(priority_band),
            "scheduler.starvation_promoted": len(promoted),
        }

        if errors:
            first_task_id = next(iter(errors))
            raise RuntimeError(f"Scheduler node '{first_task_id}' failed") from errors[first_task_id]
        return results


def run_dag_blocking(
    graph: TaskGraph,
    *,
    executor: NodeExecutor,
    concurrency_limit: int = 4,
    starvation_promote_after_seconds: float = 60.0,
) -> dict[str, Any]:
    scheduler = Scheduler(
        executor=executor,
        concurrency_limit=concurrency_limit,
        starvation_promote_after_seconds=starvation_promote_after_seconds,
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(scheduler.run(graph))
    raise RuntimeError("run_dag_blocking cannot run inside an active event loop")
