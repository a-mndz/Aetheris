"""
Aetheris — Adaptive Multi-Model Reasoning Orchestrator
Validation arbitration & synthesis judge.

Invokes a dedicated judge model to score logical consistency between
two competing agent outputs and formulate an authoritative consensus.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from core.schemas import AetherisOutput
from agents.parser import parse_and_repair
from agents.prompt_manager import assemble_agent_prompt
from api_gateway.strategy import ProviderStrategy
from api_gateway.rate_limiter import AsyncAPIGateway, ProviderPool

logger = logging.getLogger("Aetheris.Orchestrator.Evaluation")


async def arbitrate_and_synthesize(
    query: str,
    answer_a: str,
    answer_b: str,
    gateway: AsyncAPIGateway,
    strategy: ProviderStrategy,
    pool: Optional[ProviderPool] = None,
    lessons: str = "",
    history: list[dict[str, str]] | None = None,
) -> AetherisOutput | dict:
    """
    Invokes the synthesizer judge to score logical consistency
    and formulate the authoritative consensus response.

    Parameters
    ----------
    query:
        The original user query.
    answer_a:
        Logician agent's answer.
    answer_b:
        Creative agent's answer.
    gateway:
        The async API gateway for making model calls.
    strategy:
        Provider strategy for model selection.
    pool:
        Optional provider pool for health tracking.  If omitted the
        gateway's internal default pool is used (not recommended).
    lessons:
        Historical loop-failure lessons to inject.
    """
    # Escape user-controlled content to prevent prompt injection.
    # json.dumps wraps values in quotes and escapes special characters,
    # making it structurally impossible for user input to break out of
    # the delimited sections.
    safe_query = json.dumps(query)
    safe_answer_a = json.dumps(answer_a)
    safe_answer_b = json.dumps(answer_b)
    safe_lessons = json.dumps(lessons if lessons else "None. This is the primary loop execution.")

    evaluation_prompt = f"""\
You are the Senior Synthesizer Arbiter. Your task is to evaluate two competing reasoning
patterns from agent nodes, resolve any logical discrepancies, and output a singular
authoritative response.

<user_query>
{safe_query}
</user_query>

<logician_argument>
{safe_answer_a}
</logician_argument>

<creative_argument>
{safe_answer_b}
</creative_argument>

<historic_lessons>
{safe_lessons}
</historic_lessons>

INSTRUCTIONS:
1. Resolve contradictions logically.
2. Formulate your 'final_answer' as a comprehensive, conversational response (like a helpful AI assistant). You MUST include and discuss any valid alternatives or trade-offs proposed by the Creative agent in your final answer! Do not truncate them.
3. Provide validation_score from 0.0 to 10.0 indicating overall logical consistency.
4. State structural disagreements clearly in 'disagreement_notes'.

Output strictly in raw JSON following the AetherisOutput schema layout:
{{
  "final_answer": "<your_synthesized_response>",
  "overall_confidence": "High/Medium/Low",
  "overall_bias_risk": "Low/Medium/High",
  "disagreement_notes": ["Note 1", "Note 2"],
  "validation_score": 9.5
}}
"""

    logger.info("Calling Synthesizer validation judge...")
    system_prompt = assemble_agent_prompt(
        role="Reasoning Fusion Engine",
        pipeline_stage="Synthesis",
        objective="Consensus and Synthesis Arbitration",
        iteration=1,
        execution_mode=strategy.mode.value,
        system_prompt_filename="09_synthesizer.xml"
    )

    raw_judge_output = await gateway.execute_with_fallback(
        prompt=evaluation_prompt,
        system_prompt=system_prompt,
        role="judge",
        strategy=strategy,
        pool=pool,
        history=history,
    )

    return parse_and_repair(raw_judge_output, AetherisOutput)
