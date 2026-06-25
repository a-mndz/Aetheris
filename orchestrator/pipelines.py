"""
Aetheris — Adaptive Multi-Model Reasoning Orchestrator
Pipeline: Micro-Mode execution path.
"""

from __future__ import annotations

import asyncio
import logging
from difflib import SequenceMatcher
from typing import Any, AsyncGenerator, TypedDict

from agents.parser import parse_and_repair
from agents.prompt_manager import assemble_agent_prompt
from api_gateway.rate_limiter import AsyncAPIGateway, ProviderPool
from api_gateway.strategy import ProviderStrategy
from core.schemas import AgentOutput
from orchestrator.evaluation import arbitrate_and_synthesize
from orchestrator.memory import epistemic_memory

logger = logging.getLogger(__name__)


# ── Result Types ─────────────────────────────────────────────────────────

class MicroModeResult(TypedDict):
    status: str
    winning_answer: str
    validation_score: float
    diversity_metric: float
    judge_decision: dict[str, Any] | None
    logician_output: AgentOutput | dict[str, Any] | None
    creative_output: AgentOutput | dict[str, Any] | None


# ── Knowledge-Absence Detection ─────────────────────────────────────────

_ABSENCE_SENTINEL = "KNOWLEDGE ABSENCE DETECTED"


def _is_knowledge_absent(breaker_output: AgentOutput | dict[str, Any]) -> bool:
    if isinstance(breaker_output, AgentOutput):
        return (
            _ABSENCE_SENTINEL in breaker_output.answer
            or breaker_output.confidence == 0.0
        )

    answer = breaker_output.get("answer", "")
    confidence = breaker_output.get("confidence", 0.0)
    return _ABSENCE_SENTINEL in answer or confidence == 0.0


# ── Prompt Assembly ──────────────────────────────────────────────────────

# Agent prompts are passed as separate system_prompt + prompt
# to the gateway, which sends them as distinct messages (role=system, role=user).
# This structural boundary reduces prompt-injection risk: the user query is a
# separate message object rather than text interpolated into the system prompt.


# ── Pipeline ─────────────────────────────────────────────────────────────

async def run_micro_mode(
    user_query: str,
    gateway: AsyncAPIGateway,
    strategy: ProviderStrategy,
    pool: ProviderPool,
    history: list[dict[str, str]] | None = None,
) -> MicroModeResult:
    """
    Execute the **micro-mode** pipeline.
    """
    logger.info("Micro-mode pipeline started for query: %.120s", user_query)

    # Assemble layered system prompts
    breaker_sys = assemble_agent_prompt(
        role="Breaker",
        pipeline_stage="Pre-Filter",
        objective="Knowledge Absence Detection",
        iteration=1,
        execution_mode=strategy.mode.value,
        system_prompt_filename="04_breaker.xml"
    )
    logician_sys = assemble_agent_prompt(
        role="Logician",
        pipeline_stage="Generation",
        objective="Logical Validation",
        iteration=1,
        execution_mode=strategy.mode.value,
        system_prompt_filename="05_logician.xml"
    )
    creative_sys = assemble_agent_prompt(
        role="Creative",
        pipeline_stage="Generation",
        objective="Creative Expansion",
        iteration=1,
        execution_mode=strategy.mode.value,
        system_prompt_filename="06_creative.xml"
    )

    try:
        breaker_raw = await gateway.execute_with_fallback(
            prompt=user_query,
            system_prompt=breaker_sys,
            role="breaker",
            strategy=strategy,
            pool=pool,
            history=history,
        )
    except Exception as exc:
        logger.error("Breaker gate call failed: %s: %s", type(exc).__name__, exc)
        return MicroModeResult(
            status="error",
            winning_answer=f"Pipeline error at Breaker gate: {exc}",
            validation_score=0.0,
            diversity_metric=0.0,
            judge_decision=None,
            logician_output=None,
            creative_output=None,
        )

    breaker_output = parse_and_repair(breaker_raw, AgentOutput)

    if _is_knowledge_absent(breaker_output):
        reason = (
            breaker_output.answer
            if isinstance(breaker_output, AgentOutput)
            else breaker_output.get("answer", "Unknown parse failure")
        )
        logger.warning("Breaker gate ABORTED pipeline: %s", reason)
        return MicroModeResult(
            status="aborted",
            winning_answer=reason,
            validation_score=0.0,
            diversity_metric=0.0,
            judge_decision=None,
            logician_output=None,
            creative_output=None,
        )

    logger.info("Breaker gate passed — proceeding to generation.")

    # ── Step 2: Concurrent Logician + Creative generation ────────────
    logger.info("Step 2/4 — Launching Logician and Creative agents concurrently.")

    logician_result, creative_result = await asyncio.gather(
        gateway.execute_with_fallback(
            prompt=user_query,
            system_prompt=logician_sys,
            role="generation",
            strategy=strategy,
            pool=pool,
            history=history,
        ),
        gateway.execute_with_fallback(
            prompt=user_query,
            system_prompt=creative_sys,
            role="generation",
            strategy=strategy,
            pool=pool,
            history=history,
        ),
        return_exceptions=True,
    )

    # Handle exceptions
    if isinstance(logician_result, BaseException):
        logger.error("Logician generation failed: %s", logician_result)
        return MicroModeResult(
            status="error",
            winning_answer=f"Logician generation failed: {logician_result}",
            validation_score=0.0,
            diversity_metric=0.0,
            judge_decision=None,
            logician_output=None,
            creative_output=None,
        )

    if isinstance(creative_result, BaseException):
        logger.error("Creative generation failed: %s", creative_result)
        return MicroModeResult(
            status="error",
            winning_answer=f"Creative generation failed: {creative_result}",
            validation_score=0.0,
            diversity_metric=0.0,
            judge_decision=None,
            logician_output=None,
            creative_output=None,
        )

    # Both succeeded — parse raw strings into structured outputs.
    logician_output = parse_and_repair(logician_result, AgentOutput)
    creative_output = parse_and_repair(creative_result, AgentOutput)

    logger.info(
        "Both generations parsed — Logician type=%s, Creative type=%s.",
        type(logician_output).__name__,
        type(creative_output).__name__,
    )

    logician_agent = _ensure_agent_output(logician_output, "Logician")
    creative_agent = _ensure_agent_output(creative_output, "Creative")

    # Guard: if either agent produced an error sentinel, skip the judge.
    if logician_agent.answer.startswith("ERROR:") and creative_agent.answer.startswith("ERROR:"):
        logger.error("Both agent outputs are parse-failure sentinels — skipping judge.")
        return MicroModeResult(
            status="error",
            winning_answer="Both generation agents failed to produce valid output.",
            validation_score=0.0,
            diversity_metric=0.0,
            judge_decision=None,
            logician_output=logician_output,
            creative_output=creative_output,
        )

    # ── Step 3: Validation & Synthesis Judge ──────────────────────────
    logger.info("Step 3/4 — Submitting generations to validation arbitrage judge.")

    # Retrieve memory failures/lessons learned for the active prompt
    lessons = epistemic_memory.get_lessons_learned(user_query)

    try:
        final_output = await arbitrate_and_synthesize(
            query=user_query,
            answer_a=logician_agent.answer,
            answer_b=creative_agent.answer,
            gateway=gateway,
            strategy=strategy,
            pool=pool,
            lessons=lessons,
            history=history,
        )
    except Exception as exc:
        logger.error("Synthesis judge failed: %s", exc)
        return MicroModeResult(
            status="error",
            winning_answer=f"Logic judge evaluation failed: {exc}",
            validation_score=0.0,
            diversity_metric=0.0,
            judge_decision=None,
            logician_output=logician_output,
            creative_output=creative_output,
        )

    # Guard: parse_and_repair can return a dict on parse failure.
    if isinstance(final_output, dict):
        logger.error("Judge output parse failure: %s", final_output)
        return MicroModeResult(
            status="error",
            winning_answer=f"Judge output unparseable: {final_output.get('answer', 'unknown')}",
            validation_score=0.0,
            diversity_metric=0.0,
            judge_decision=None,
            logician_output=logician_output,
            creative_output=creative_output,
        )

    # Stateful failure tracking (epistemic loop failures)
    if final_output.validation_score < 7.0:
        logger.warning(
            "Low validation score (%f) detected. Recording failure pattern.",
            final_output.validation_score,
        )
        epistemic_memory.record_failure(
            query=user_query,
            explanation=", ".join(final_output.disagreement_notes) or "Low validation score.",
            score=final_output.validation_score,
        )

    # ── Step 4: Assemble result ──────────────────────────────────────
    logger.info("Step 4/4 — Assembling final micro-mode result.")

    decision_dict = {
        "verdict": "synthesized",
        "score_a": final_output.validation_score,
        "score_b": final_output.validation_score,
        "justification": (
            f"Confidence: {final_output.overall_confidence} | "
            f"Bias Risk: {final_output.overall_bias_risk} | "
            f"Disagreements: {', '.join(final_output.disagreement_notes) if final_output.disagreement_notes else 'None'}"
        ),
    }

    diversity_metric = _calculate_diversity_metric(logician_agent, creative_agent)

    return MicroModeResult(
        status="success",
        winning_answer=final_output.final_answer,
        validation_score=final_output.validation_score,
        diversity_metric=diversity_metric,
        judge_decision=decision_dict,
        logician_output=logician_output,
        creative_output=creative_output,
    )


async def stream_micro_mode(
    user_query: str,
    gateway: AsyncAPIGateway,
    strategy: ProviderStrategy,
    pool: ProviderPool,
    history: list[dict[str, str]] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Streaming variant of :func:`run_micro_mode`.

    Yields granular per-agent SSE events so the frontend can render
    real-time progress for each agent independently.

    Event types emitted:
        agent_started, progress, reasoning_summary, draft_answer,
        agent_completed, error, result
    """
    logger.info("Streaming micro-mode pipeline started for query: %.120s", user_query)

    # ── Helper: serialise an AgentOutput (or dict) for the wire ──────
    def _serialise(obj: Any) -> dict[str, Any]:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        return obj if isinstance(obj, dict) else {}

    # ── Helper: extract confidence label from a parsed agent output ──
    def _confidence_label(agent_out: AgentOutput | dict[str, Any]) -> str:
        if isinstance(agent_out, AgentOutput):
            c = agent_out.confidence
        else:
            c = agent_out.get("confidence", 0.0)
        if c >= 0.75:
            return "High"
        if c >= 0.4:
            return "Medium"
        return "Low"

    # Assemble layered system prompts
    breaker_sys = assemble_agent_prompt(
        role="Breaker",
        pipeline_stage="Pre-Filter",
        objective="Knowledge Absence Detection",
        iteration=1,
        execution_mode=strategy.mode.value,
        system_prompt_filename="04_breaker.xml"
    )
    logician_sys = assemble_agent_prompt(
        role="Logician",
        pipeline_stage="Generation",
        objective="Logical Validation",
        iteration=1,
        execution_mode=strategy.mode.value,
        system_prompt_filename="05_logician.xml"
    )
    creative_sys = assemble_agent_prompt(
        role="Creative",
        pipeline_stage="Generation",
        objective="Creative Expansion",
        iteration=1,
        execution_mode=strategy.mode.value,
        system_prompt_filename="06_creative.xml"
    )

    # ── Step 1: Breaker gate ─────────────────────────────────────────
    yield {"event": "agent_started", "agent": "Breaker"}
    yield {"event": "progress", "agent": "Breaker", "step": 1, "total_steps": 3, "message": "Reading request..."}
    yield {"event": "progress", "agent": "Breaker", "step": 2, "total_steps": 3, "message": "Checking knowledge context..."}

    try:
        breaker_raw = await gateway.execute_with_fallback(
            prompt=user_query,
            system_prompt=breaker_sys,
            role="breaker",
            strategy=strategy,
            pool=pool,
            history=history,
        )
    except Exception as exc:
        logger.error("Breaker gate call failed: %s: %s", type(exc).__name__, exc)
        yield {
            "event": "error",
            "stage": "breaker",
            "agent": "Breaker",
            "message": f"Pipeline error at Breaker gate: {exc}",
        }
        return

    breaker_output = parse_and_repair(breaker_raw, AgentOutput)

    if _is_knowledge_absent(breaker_output):
        reason = (
            breaker_output.answer
            if isinstance(breaker_output, AgentOutput)
            else breaker_output.get("answer", "Unknown parse failure")
        )
        logger.warning("Breaker gate ABORTED pipeline: %s", reason)
        yield {"event": "agent_completed", "agent": "Breaker", "confidence": "Low", "final_answer": reason, "status": "aborted"}
        yield {
            "event": "result",
            "payload": _build_frontend_payload(
                MicroModeResult(
                    status="aborted",
                    winning_answer=reason,
                    validation_score=0.0,
                    diversity_metric=0.0,
                    judge_decision=None,
                    logician_output=None,
                    creative_output=None,
                )
            ),
        }
        return

    yield {"event": "progress", "agent": "Breaker", "step": 3, "total_steps": 3, "message": "Context verified"}
    breaker_data = _serialise(breaker_output)
    yield {
        "event": "reasoning_summary",
        "agent": "Breaker",
        "section": "Evidence Used",
        "content": breaker_data.get("reasoning_steps", []),
    }
    yield {"event": "agent_completed", "agent": "Breaker", "confidence": _confidence_label(breaker_output), "final_answer": breaker_data.get("answer", "")}
    logger.info("Breaker gate passed — proceeding to generation.")

    # ── Step 2: Concurrent Logician + Creative generation ────────────
    yield {"event": "agent_started", "agent": "Logician"}
    yield {"event": "agent_started", "agent": "Creative"}
    yield {"event": "progress", "agent": "Logician", "step": 1, "total_steps": 4, "message": "Decomposing premises..."}
    yield {"event": "progress", "agent": "Creative", "step": 1, "total_steps": 4, "message": "Reframing question..."}

    # Use an asyncio.Queue so we can yield events as each agent finishes
    agent_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def _run_agent(name: str, system_prompt: str) -> None:
        """Execute a single generation agent and push result onto the queue."""
        try:
            result = await gateway.execute_with_fallback(
                prompt=user_query,
                system_prompt=system_prompt,
                role="generation",
                strategy=strategy,
                pool=pool,
                history=history,
            )
            await agent_queue.put((name, result))
        except Exception as exc:
            await agent_queue.put((name, exc))

    logician_task = asyncio.create_task(_run_agent("Logician", logician_sys))
    creative_task = asyncio.create_task(_run_agent("Creative", creative_sys))

    # Collect results as they arrive
    agent_results: dict[str, Any] = {}
    for _ in range(2):
        name, result = await agent_queue.get()
        if isinstance(result, BaseException):
            logger.error("%s generation failed: %s", name, result)
            yield {
                "event": "error",
                "stage": "agents",
                "agent": name,
                "message": f"{name} generation failed: {result}",
            }
            # Cancel the other task and bail out
            logician_task.cancel()
            creative_task.cancel()
            return

        agent_results[name] = result
        step_num = 3  # post-LLM processing step
        yield {"event": "progress", "agent": name, "step": step_num, "total_steps": 4, "message": "Parsing response..."}

        parsed = parse_and_repair(result, AgentOutput)
        agent_out = _ensure_agent_output(parsed, name)
        agent_results[f"{name}_parsed"] = parsed
        agent_results[f"{name}_agent"] = agent_out
        data = _serialise(parsed)

        yield {
            "event": "reasoning_summary",
            "agent": name,
            "section": "Evidence Used",
            "content": data.get("reasoning_steps", []),
        }
        yield {"event": "draft_answer", "agent": name, "content": data.get("answer", "")}
        yield {"event": "progress", "agent": name, "step": 4, "total_steps": 4, "message": "Analysis complete"}
        yield {
            "event": "agent_completed",
            "agent": name,
            "confidence": _confidence_label(parsed),
            "final_answer": data.get("answer", ""),
        }

    logician_output = agent_results["Logician_parsed"]
    creative_output = agent_results["Creative_parsed"]
    logician_agent = agent_results["Logician_agent"]
    creative_agent = agent_results["Creative_agent"]

    # Guard: if both agents produced error sentinels, skip the judge.
    if logician_agent.answer.startswith("ERROR:") and creative_agent.answer.startswith("ERROR:"):
        logger.error("Both agent outputs are parse-failure sentinels — skipping judge.")
        yield {
            "event": "error",
            "stage": "agents",
            "message": "Both generation agents failed to produce valid output.",
        }
        return

    # ── Step 3: Validation & Synthesis Judge ──────────────────────────
    yield {"event": "agent_started", "agent": "Judge"}
    yield {"event": "progress", "agent": "Judge", "step": 1, "total_steps": 4, "message": "Comparing outputs..."}
    yield {"event": "progress", "agent": "Judge", "step": 2, "total_steps": 4, "message": "Evaluating evidence..."}

    lessons = epistemic_memory.get_lessons_learned(user_query)

    try:
        final_output = await arbitrate_and_synthesize(
            query=user_query,
            answer_a=logician_agent.answer,
            answer_b=creative_agent.answer,
            gateway=gateway,
            strategy=strategy,
            pool=pool,
            lessons=lessons,
            history=history,
        )
    except Exception as exc:
        logger.error("Synthesis judge failed: %s", exc)
        yield {
            "event": "error",
            "stage": "judge",
            "agent": "Judge",
            "message": f"Logic judge evaluation failed: {exc}",
        }
        return

    if isinstance(final_output, dict):
        logger.error("Judge output parse failure: %s", final_output)
        yield {
            "event": "error",
            "stage": "judge",
            "agent": "Judge",
            "message": f"Judge output unparseable: {final_output.get('answer', 'unknown')}",
        }
        return

    yield {"event": "progress", "agent": "Judge", "step": 3, "total_steps": 4, "message": "Synthesizing verdict..."}

    # Stateful failure tracking
    if final_output.validation_score < 7.0:
        logger.warning(
            "Low validation score (%f) detected. Recording failure pattern.",
            final_output.validation_score,
        )
        epistemic_memory.record_failure(
            query=user_query,
            explanation=", ".join(final_output.disagreement_notes) or "Low validation score.",
            score=final_output.validation_score,
        )

    yield {
        "event": "reasoning_summary",
        "agent": "Judge",
        "section": "Verdict",
        "content": final_output.disagreement_notes if final_output.disagreement_notes else ["No disagreements identified"],
    }
    yield {"event": "draft_answer", "agent": "Judge", "content": final_output.final_answer}
    yield {"event": "progress", "agent": "Judge", "step": 4, "total_steps": 4, "message": "Judgment complete"}
    yield {
        "event": "agent_completed",
        "agent": "Judge",
        "confidence": final_output.overall_confidence,
        "final_answer": final_output.final_answer,
    }

    # ── Step 4: Assemble result ──────────────────────────────────────
    decision_dict = {
        "verdict": "synthesized",
        "score_a": final_output.validation_score,
        "score_b": final_output.validation_score,
        "justification": (
            f"Confidence: {final_output.overall_confidence} | "
            f"Bias Risk: {final_output.overall_bias_risk} | "
            f"Disagreements: {', '.join(final_output.disagreement_notes) if final_output.disagreement_notes else 'None'}"
        ),
    }

    diversity_metric = _calculate_diversity_metric(logician_agent, creative_agent)

    result = MicroModeResult(
        status="success",
        winning_answer=final_output.final_answer,
        validation_score=final_output.validation_score,
        diversity_metric=diversity_metric,
        judge_decision=decision_dict,
        logician_output=logician_output,
        creative_output=creative_output,
    )

    yield {"event": "result", "payload": _build_frontend_payload(result)}


def _build_frontend_payload(result: MicroModeResult) -> dict[str, Any]:
    """Convert a MicroModeResult into the shape the frontend expects."""
    import re

    serialized: dict[str, Any] = dict(result)
    for key in ("logician_output", "creative_output"):
        val = serialized.get(key)
        if val is not None and hasattr(val, "model_dump"):
            serialized[key] = val.model_dump()

    decision = serialized.get("judge_decision")
    bias_risk = "Unknown"
    if decision:
        if "justification" in decision:
            m = re.search(r"Bias Risk:\s*(.*?)\s*\|", decision["justification"])
            if m:
                bias_risk = m.group(1)
        if "score_a" in decision and decision["score_a"] is not None:
            decision["score_a"] = decision["score_a"] / 10.0
        if "score_b" in decision and decision["score_b"] is not None:
            decision["score_b"] = decision["score_b"] / 10.0

    validation_score = serialized.get("validation_score")
    confidence_score = (validation_score / 10.0) if validation_score is not None else 0.0

    return {
        "status": serialized.get("status"),
        "answer": serialized.get("winning_answer"),
        "confidence_score": confidence_score,
        "bias_risk": bias_risk,
        "decision": decision,
        "agent_outputs": {
            "logician": serialized.get("logician_output"),
            "creative": serialized.get("creative_output"),
        },
    }


# ── Private Helpers ──────────────────────────────────────────────────────

def _ensure_agent_output(
    parsed: AgentOutput | dict[str, Any],
    label: str,
) -> AgentOutput:
    if isinstance(parsed, AgentOutput):
        return parsed

    logger.warning(
        "%s agent output was an error dict — constructing minimal AgentOutput.",
        label,
    )
    return AgentOutput(
        reasoning_steps=parsed.get(
            "reasoning_steps",
            [f"PARSE FAILURE for {label} agent."],
        ),
        answer=parsed.get("answer", f"ERROR: {label} agent output unparsable."),
        confidence=parsed.get("confidence", 0.0),
    )


def _calculate_diversity_metric(
    logician_agent: AgentOutput,
    creative_agent: AgentOutput,
) -> float:
    """Return a bounded lexical/output divergence score for two agent answers."""
    answer_a = logician_agent.answer.strip().lower()
    answer_b = creative_agent.answer.strip().lower()
    if not answer_a and not answer_b:
        return 0.0

    lexical_distance = 1.0 - SequenceMatcher(None, answer_a, answer_b).ratio()
    confidence_delta = abs(logician_agent.confidence - creative_agent.confidence)
    score = (lexical_distance * 0.8) + (confidence_delta * 0.2)
    return round(max(0.0, min(1.0, score)), 4)
