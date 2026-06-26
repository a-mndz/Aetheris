"""
aetheris — Adaptive Multi-Model Reasoning Orchestrator
Epistemic memory: failure-tracking bus for loop-failure avoidance.

Tracks failed pipeline executions so subsequent runs for similar queries
can avoid repeating the same mistakes.
"""

from __future__ import annotations

from collections import deque
from typing import List, Dict


class EpistemicMemory:
    """
    Stateful memory manager tracking loop failures, invalid reasoning
    patterns, and negative model behaviors to avoid recursive errors.

    Parameters
    ----------
    max_entries:
        Maximum number of failure records to retain (sliding window).
        Oldest entries are evicted when the limit is reached.
    """

    def __init__(self, max_entries: int = 200) -> None:
        self.failed_loops: deque[Dict[str, str]] = deque(maxlen=max_entries)

    def record_failure(self, query: str, explanation: str, score: float) -> None:
        """Stores a failed loop execution fingerprint."""
        self.failed_loops.append({
            "query": query,
            "query_lower": query.strip().lower(),
            "explanation": explanation,
            "score": str(score),
        })

    def get_lessons_learned(self, query: str) -> str:
        """
        Retrieves lessons learned to pass back to the active prompt generator.

        Matching uses case-insensitive substring containment so minor
        rephrasing of the same query still retrieves relevant lessons.
        """
        query_normalised = query.strip().lower()
        matching_failures = [
            f for f in self.failed_loops
            if (
                f["query_lower"] == query_normalised
                or query_normalised in f["query_lower"]
                or f["query_lower"] in query_normalised
            )
        ]
        if not matching_failures:
            return ""

        compiled = ["HISTORICAL MISTAKES IDENTIFIED IN PREVIOUS ATTEMPTS:"]
        for idx, item in enumerate(matching_failures, 1):
            compiled.append(f"{idx}. Loop failure score {item['score']}: Error explanation: {item['explanation']}")
        return "\n".join(compiled)

    def reset(self) -> None:
        self.failed_loops.clear()


# Global Epistemic Memory Bus
epistemic_memory = EpistemicMemory()
