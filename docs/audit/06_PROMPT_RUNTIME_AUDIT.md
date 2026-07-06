# AETHERIS Prompt Runtime Audit — XML Contracts & Execution Pipeline

**Audit Date:** 2026-06-27
**Auditor:** Principal Backend Engineer
**Scope:** Complete static analysis of the XML prompt system, runtime contracts, prompt loading pipeline, execution order validation, and schema enforcement.

---

## Table of Contents

1. [XML Contract Inventory](#1-xml-contract-inventory)
2. [Prompt Loading Architecture](#2-prompt-loading-architecture)
3. [Runtime Contract Analysis](#3-runtime-contract-analysis)
4. [System Prompt Analysis](#4-system-prompt-analysis)
5. [Execution Order Validation](#5-execution-order-validation)
6. [Pipeline Role Enforcement](#6-pipeline-role-enforcement)
7. [JSON Schema Enforcement](#7-json-schema-enforcement)
8. [Pydantic Model Integration](#8-pydantic-model-integration)
9. [Prompt Assembly Performance](#9-prompt-assembly-performance)
10. [Fallback & Error Handling](#10-fallback--error-handling)
11. [Security & Injection Prevention](#11-security--injection-prevention)
12. [Issue Register](#12-issue-register)

---

## 1. XML Contract Inventory

### Runtime Contracts (12 files)

| # | File | Purpose | Loaded | Validated |
|---|------|---------|--------|-----------|
| 00 | `00_agent_runtime.xml` | Base agent runtime behavior | ✅ | ✅ |
| 01 | `01_prompt_loader.xml` | Prompt loading instructions | ✅ | ✅ |
| 02 | `02_response_contract.xml` | Response format requirements | ✅ | ✅ |
| 03 | `03_context_manager.xml` | Context window management | ✅ | ✅ |
| 04 | `04_execution_contract.xml` | Execution constraints, timeouts | ✅ | ✅ |
| 05 | `05_error_handling.xml` | Error handling procedures | ✅ | ✅ |
| 06 | `06_pipeline_state.xml` | Pipeline state machine rules | ✅ | ✅ |
| 07 | `07_memory_manager.xml` | Memory management contract | ✅ | ✅ |
| 08 | `08_stream_contract.xml` | Streaming behavior contract | ✅ | ✅ |
| 09 | `09_provider_contract.xml` | Provider API interaction rules | ✅ | ✅ |
| 10 | `10_security_contract.xml` | Security and input validation | ✅ | ✅ |
| 11 | `11_completion_contract.xml` | Completion and output rules | ✅ | ✅ |

All 12 runtime contracts are loaded and validated for every agent prompt assembly call.

### System Prompts (13 files)

| # | File | Role | Used | Purpose |
|---|------|------|------|---------|
| 01 | `01_prompt_normalizer.xml` | Prompt Normalizer | ❌ | Input normalization |
| 02 | `02_parameter_engine.xml` | Parameter Engine | ❌ | Parameter extraction |
| 03 | `03_conversation_director.xml` | Conversation Director | ❌ | Multi-turn management |
| 04 | `04_breaker.xml` | Breaker | ✅ | Knowledge absence detection |
| 05 | `05_logician.xml` | Logician | ✅ | Deductive reasoning |
| 06 | `06_creative.xml` | Creative | ✅ | Creative reasoning |
| 07 | `07_judge_logic.xml` | Judge Logic | ❌ | Logical consistency evaluation |
| 08 | `08_judge_factual.xml` | Judge Factual | ❌ | Factual accuracy evaluation |
| 09 | `09_synthesizer.xml` | Reasoning Fusion Engine | ✅ | Synthesis & arbitration |
| 10 | `10_reasoning_budget.xml` | Reasoning Budget | ❌ | Token/cost budgeting |
| 11 | `11_streaming.xml` | Streaming Contract | ❌ | Streaming behavior |
| 12 | `12_output_formatter.xml` | Output Formatter | ❌ | Response formatting |
| 13 | `13_json_schema.xml` | JSON Schema | ❌ | Schema enforcement |

Only **4 of 13** system prompts are actively used in the pipeline.

### Fallback Mechanism

When an XML system prompt file is missing or fails validation, `load_system_prompt` (prompt_manager.py:142) falls back to `PERSONA_REGISTRY` (personas.py:224):

```python
fallback = PERSONA_REGISTRY.get(persona_key, "")
```

The persona key is derived from the filename by splitting on `_` and taking the last part:
- `"05_logician.xml"` → `parts[-1].lower()` → `"logician"` → `PERSONA_REGISTRY["logician"]` → `LOGICIAN_PROMPT`
- `"09_synthesizer.xml"` → `parts[-1].lower()` → `"9"` → `PERSONA_REGISTRY.get("9", "")` → **empty string**

**Bug**: The fallback key derivation for `09_synthesizer.xml` produces `"9"` because the filename splits as `["09", "synthesizer.xml"]` and `parts[-1]` is `"synthesizer.xml"`. Actually, the code does:

```python
base_name = os.path.basename(filename)  # e.g., "09_synthesizer.xml"
parts = base_name.replace(".xml", "").split("_")  # ["09", "synthesizer"]
persona_key = parts[-1].lower() if parts else ""  # "synthesizer"
```

Wait — `"09_synthesizer.xml".replace(".xml", "")` = `"09_synthesizer"`, then split on `_` = `["09", "synthesizer"]`, so `parts[-1]` = `"synthesizer"`. The registry does not have a `"synthesizer"` key — it has `"logician"`, `"creative"`, `"breaker"`, `"verifier"`, `"skeptic"`. So the fallback would return empty string.

The `assemble_synthesizer_prompt` function in `prompt_utils.py` uses `"09_synthesizer.xml"` as the filename. If this file exists and validates, the fallback is never triggered. But if the file is missing, the pipeline would get an empty prompt for the synthesizer.

---

## 2. Prompt Loading Architecture

### Loading Sequence

```
assemble_agent_prompt(role, stage, objective, iteration, execution_mode, filename)
    │
    ├─ 1. Build ROLE block (<ROLE>...</ROLE>) — dynamic, ~50 tokens
    │
    ├─ 2. load_runtime_contracts()
    │       │
    │       ├─ os.listdir("prompts/runtime/")
    │       ├─ sort .xml files by name
    │       ├─ for each file:
    │       │       ├─ load_prompt_file_with_validation()
    │       │       │       ├─ load_prompt_file()      — read from disk
    │       │       │       ├─ validate_xml()           — ElementTree parse
    │       │       │       └─ return cleaned content
    │       │       └─ append to list
    │       └─ return list of 12 XML strings
    │
    ├─ 3. load_system_prompt(filename)
    │       │
    │       ├─ load prompt from "prompts/system/{filename}"
    │       ├─ validate XML
    │       ├─ if valid → return XML content
    │       └─ if invalid → PERSONA_REGISTRY fallback
    │
    └─ 4. Combine: ROLE + runtime_contracts + system_prompt
            └─ return "\n\n".join(parts)
```

### XML Validation

The `validate_xml` function (prompt_manager.py:25) uses Python's `xml.etree.ElementTree` parser:

```python
def validate_xml(content: str) -> Tuple[bool, Optional[str]]:
    if not content or not content.strip():
        return False, "Empty XML content"
    try:
        ET.fromstring(content)
        return True, None
    except ET.ParseError as e:
        return False, f"XML parsing error: {str(e)}"
```

**Limitation**: ElementTree validates well-formedness (matching tags, proper nesting), but does **not** validate against an XML Schema (XSD) or DTD. Structural contracts like "must contain `<instructions>` tag inside `<contract>` root" are **not enforced** by the validator. If a runtime contract XML file is missing an expected section, it will still validate as long as it's well-formed XML.

### Markdown Code Fence Stripping

`clean_xml_prompt` (prompt_manager.py:10) removes leading/trailing markdown code fences:

```python
def clean_xml_prompt(content: str) -> str:
    content = content.strip()
    if content.startswith("```xml"):
        content = content[6:].strip()
    elif content.startswith("```"):
        content = content[3:].strip()
    if content.endswith("```"):
        content = content[:-3].strip()
    return content.strip()
```

**Issue**: If the content contains code fences in the middle of the text (e.g., an example XML block within the prompt), they would not be stripped (correctly). However, if a ` ``` ` appears at the end by coincidence (not a closing fence), it would be incorrectly removed.

---

## 3. Runtime Contract Analysis

### Contract Loading Order

The runtime contracts are loaded in alphanumeric file order (00-11):

```
00 → Agent Runtime         (base behavior)
01 → Prompt Loader         (loading instructions)
02 → Response Contract     (response format)
03 → Context Manager       (context window)
04 → Execution Contract    (timeouts, constraints)
05 → Error Handling        (error procedures)
06 → Pipeline State        (state machine)
07 → Memory Manager        (memory rules)
08 → Stream Contract       (streaming behavior)
09 → Provider Contract     (API interaction)
10 → Security Contract     (security rules)
11 → Completion Contract   (output rules)
```

### Content Pattern

Each runtime contract follows this structure (from the code's expectation):

```xml
<contract>
  <name>contract_name</name>
  <description>Contract description</description>
  <instructions>
    <!-- Contract-specific instructions -->
  </instructions>
  <rules>
    <rule>Rule 1</rule>
    <rule>Rule 2</rule>
  </rules>
</contract>
```

### Redundancy Analysis

All 12 contracts are loaded for all agents:

| Agent | Relevant Contracts | Irrelevant Contracts | Waste |
|-------|-------------------|---------------------|-------|
| Breaker | 00, 04, 05, 06, 10 | 01, 02, 03, 07, 08, 09, 11 | ~7 contracts |
| Logician | 00, 02, 03, 04, 05, 06, 07, 10, 11 | 01, 08, 09 | ~3 contracts |
| Creative | 00, 02, 03, 04, 05, 06, 07, 10, 11 | 01, 08, 09 | ~3 contracts |
| Judge | 00, 02, 04, 05, 06, 10, 11 | 01, 03, 07, 08, 09 | ~5 contracts |

The Breaker, designed as a "lightweight, fast pre-filter" with 100ms timeout, receives the full 12-contract context regardless of its simple gatekeeping role.

---

## 4. System Prompt Analysis

### Used Prompts (4 of 13)

#### `04_breaker.xml` → Breaker Agent

**Role**: Knowledge absence detection (gate)
**Key Instructions**:
- Assess if context is sufficient
- For most queries, context is deemed sufficient
- Only abort on specific private/proprietary document requests
- MUST NOT answer the query
- Respond in UNDER 50 WORDS
- Output: `AgentOutput` (reasoning_steps, answer, confidence)

**Confidence Contract**: 1.0 (sufficient) or 0.0 (absent) — no intermediate values.

#### `05_logician.xml` → Logician Agent

**Role**: Deductive logical reasoning
**Key Instructions**:
- Decompose into PREMISE → INFERENCE → CONCLUSION triples
- Flag logical fallacies by standard taxonomy name
- Distinguish DEDUCTIVE vs INDUCTIVE steps
- Single invalid step → confidence ≤ 0.3
- Output: `AgentOutput` with structured reasoning

**Confidence Contract**: Calibrated to weakest link (0.0-1.0).

#### `06_creative.xml` → Creative Agent

**Role**: Explore orthogonal solution spaces
**Key Instructions**:
- Reframe question in TWO fundamentally different ways
- At least THREE edge cases or boundary conditions
- Include BOTH conventional and alternative answers
- Creativity must be grounded and internally consistent
- Output: `AgentOutput` with comparative analysis

**Confidence Contract**: Based on strength of alternative (0.0-1.0).

#### `09_synthesizer.xml` → Reasoning Fusion Engine (Judge)

**Role**: Consensus and synthesis arbitration
**Key Instructions**:
- Evaluate two competing reasoning patterns
- Resolve logical discrepancies
- Output structured `aetherisOutput`
- Provide validation_score from 0.0 to 10.0

### Unused Prompts (9 of 13)

| File | Purpose | Why Unused | Impact |
|------|---------|------------|--------|
| `01_prompt_normalizer.xml` | Normalize user input | Pipeline skips normalization | Raw queries go directly to Breaker |
| `02_parameter_engine.xml` | Extract parameters from query | Pipeline skips parameter extraction | No structured parameter extraction |
| `03_conversation_director.xml` | Manage conversation context | ConversationDirector is Python code, not prompt-driven | No conflict — CD is a code component |
| `07_judge_logic.xml` | Evaluate logical consistency | Pipeline uses combined synthesizer | All judging is done by one agent |
| `08_judge_factual.xml` | Evaluate factual accuracy | Pipeline uses combined synthesizer | No separate factual verification |
| `10_reasoning_budget.xml` | Budget token usage | Pipeline has no budget enforcement | Tokens are unbounded |
| `11_streaming.xml` | Define streaming behavior | Streaming is handled by StreamingManager code | No conflict — streaming is code-driven |
| `12_output_formatter.xml` | Format final output | Formatter is `_build_frontend_payload` | Formatting is code-driven |
| `13_json_schema.xml` | Enforce JSON output schema | JSON schema is enforced by `parse_and_repair` | Schema enforcement is code-driven |

### Persona Registry vs XML Loading

The `PERSONA_REGISTRY` (personas.py:224) contains 5 entries: `verifier`, `skeptic`, `logician`, `creative`, `breaker`. The XML system prompt directory contains 13 files.

The `load_system_prompt` function loads from XML first, then falls back to `PERSONA_REGISTRY`. This means:
- If `04_breaker.xml` exists → XML version is used (overrides `BREAKER_PROMPT` constant)
- If `05_logician.xml` exists → XML version is used (overrides `LOGICIAN_PROMPT` constant)

The XML files are the **authoritative** prompt sources. The Python constants in `personas.py` are **fallbacks** for when XML files are missing.

---

## 5. Execution Order Validation

### Expected Execution Order

The system prompt numbering defines the intended execution order:

```
01 Prompt Normalizer
     ↓
02 Parameter Engine
     ↓
03 Conversation Director
     ↓
04 Breaper → if knowledge absent → ABORT
     ↓
05 Logician (parallel) ──┐
06 Creative (parallel) ──┤
                         ↓
07 Judge Logic
     ↓
08 Judge Factual
     ↓
09 Reasoning Fusion Engine
     ↓
10 Reasoning Budget
     ↓
11 Streaming
     ↓
12 Output Formatter
     ↓
13 JSON Schema
```

### Actual Execution Order (Micro-Mode Pipeline)

```
[No Normalizer]
[No Parameter Engine]
03 Conversation Director    (code-level, not prompt-driven)
     ↓
04 Breaker                 (XML-loaded or persona constant)
     ↓ (if knowledge sufficient)
05 Logician ───────────────┐  (asyncio.gather, parallel)
06 Creative ───────────────┘
     ↓
[No Judge Logic]
[No Judge Factual]
09 Reasoning Fusion Engine  (single combined judge/synthesizer)
     ↓
[No Reasoning Budget]
[No Streaming]
12 Output Formatter         (code-level _build_frontend_payload)
[No JSON Schema]           (code-level parse_and_repair)
```

### Pipeline Stage Mapping

| Stage | Pipeline Code | Prompt | Purpose |
|-------|--------------|--------|---------|
| 1. Normalize | ❌ Missing | `01_prompt_normalizer.xml` | Input normalization |
| 2. Parameters | ❌ Missing | `02_parameter_engine.xml` | Parameter extraction |
| 3. Context | `init_conversation_context` | `03_conversation_director.xml` | Conversation history |
| 4. Breach Check | `execute_breaker_gate` | `04_breaker.xml` | Knowledge absence |
| 5. Generation | `execute_generation_agents` | `05_logician.xml`, `06_creative.xml` | Reasoning |
| 6. Logic Judge | ❌ Missing | `07_judge_logic.xml` | Logical evaluation |
| 7. Factual Judge | ❌ Missing | `08_judge_factual.xml` | Factual verification |
| 8. Synthesis | `arbitrate_and_synthesize` | `09_synthesizer.xml` | Fusion |
| 9. Budget | ❌ Missing | `10_reasoning_budget.xml` | Token budget |
| 10. Streaming | `streaming_manager` | `11_streaming.xml` | Event emission |
| 11. Format | `_build_frontend_payload` | `12_output_formatter.xml` | Output formatting |
| 12. Schema | `parse_and_repair` | `13_json_schema.xml` | JSON validation |

### Identified Gaps

1. **No Prompt Normalizer**: User input is passed directly to the Breaker without normalization (e.g., spell-checking, rephrasing, intent classification).

2. **No Parameter Engine**: Structured parameters are not extracted from the query. The pipeline cannot identify explicit constraints, preferences, or formatting requirements in the user's request.

3. **No Separate Logic Judge**: The combined synthesizer (judge) handles both evaluation and synthesis in one step. There is no dedicated logical consistency evaluation before synthesis.

4. **No Separate Factual Judge**: The combined synthesizer does not perform independent factual verification. The `ClaimManager.validate_claim` placeholder (always returns UNVERIFIED) means factual claims are never actually verified.

5. **No Reasoning Budget**: Token/cost budgeting is not enforced. The pipeline has no mechanism to limit reasoning depth or refuse queries that would exceed a token budget.

---

## 6. Pipeline Role Enforcement

### Breaker Never Answers User Prompts ✅

**Verified**: The Breaker agent is constrained at three levels:

1. **System Prompt** (personas.py:179-218, or `04_breaker.xml`):
   ```
   "You MUST NOT attempt to answer the query yourself."
   "You are a gate, not a generator."
   ```

2. **Output Contract**: Only two allowed responses:
   - `"CONTEXT SUFFICIENT — proceed with generation."` (confidence=1.0)
   - `"KNOWLEDGE ABSENCE DETECTED — aborting pipeline."` (confidence=0.0)
   - No intermediate values permitted

3. **Pipeline Logic** (pipelines.py:50-59, `_is_knowledge_absent`):
   ```python
   def _is_knowledge_absent(breaker_output):
       return (
           _ABSENCE_SENTINEL in breaker_output.answer
           or breaker_output.confidence == 0.0
       )
   ```
   If the breaker does not follow the contract, the sentinel detection acts as a secondary validation.

### Judges Never Generate Answers ✅

**Verified**: The Judge (synthesizer) is constrained:

1. **System Prompt** (from `09_synthesizer.xml` or assembled inline in evaluation.py:65-100):
   ```
   "You are the Senior Synthesizer Arbiter."
   "Your task is to evaluate two competing reasoning patterns..."
   ```

2. **Output Contract** (aetherisOutput schema):
   - `final_answer` — the synthesized response
   - `validation_score` — logical consistency score
   - `overall_confidence` — High/Medium/Low
   - `overall_bias_risk` — Low/Medium/High
   - `disagreement_notes` — list of structural disagreements

3. **Code Enforcement**: The `arbitrate_and_synthesize` function returns `aetherisOutput` which separates the final answer from evaluation metadata. The pipeline uses `final_answer` as the user-facing response.

### Fusion Produces Final Reasoning ✅

**Verified**: The `arbitrate_and_synthesize` function (evaluation.py:24-115):

1. Receives Logician answer (`answer_a`) and Creative answer (`answer_b`)
2. Escapes all inputs via `json.dumps` for injection prevention
3. Constructs an evaluation prompt with structured `<user_query>`, `<logician_argument>`, `<creative_argument>`, `<historic_lessons>` sections
4. Calls the LLM with the synthesizer system prompt
5. Parses the response into `aetherisOutput`
6. Returns structured output with `final_answer`, `validation_score`, `disagreement_notes`

The fusion is the **sole source** of the final answer. Neither Logician nor Creative answers are directly returned to the user.

### Formatter Formats Final Response ✅

**Verified**: `_build_frontend_payload` (pipelines.py:726-761):

1. Converts `MicroModeResult` to frontend-expected shape
2. Decomposes agent outputs via `model_dump()`
3. Extracts `bias_risk` from decision justification via regex
4. Normalizes validation score to 0.0-1.0 range (`score / 10`)
5. Returns structured dict with keys: `status`, `answer`, `confidence_score`, `bias_risk`, `decision`, `agent_outputs`

---

## 7. JSON Schema Enforcement

### Three-Stage Parse Pipeline

`parse_and_repair` (agents/parser.py:93-187):

```
Stage 1: json.loads(raw_llm_string)
    │
    ├── Success → Stage 3
    │
    └── JSONDecodeError
            │
            └── Stage 2: repair_json(raw_llm_string)
                    │
                    ├── Success → json.loads(repaired) → Stage 3
                    │
                    └── Failure → Error dict
                            ├── reasoning_steps: ["PARSE FAILURE..."]
                            ├── answer: "ERROR: Unable to parse LLM output."
                            ├── confidence: 0.0
                            └── _parse_error: {stage, error_type, error_detail, raw_snippet}

Stage 3: target_schema_class.model_validate(parsed_dict)
    │
    ├── Success → T (validated Pydantic model)
    │
    └── ValidationError → Error dict
            └── (same shape as above, with Pydantic error details)
```

### Schema Validation Flow

| Consumer | Parse Function | Target Schema | Fallback |
|----------|---------------|---------------|----------|
| Pipeline | `parse_and_repair` | `AgentOutput` | Error dict → `_ensure_agent_output` constructs minimal `AgentOutput` |
| Evaluation | `parse_and_repair` | `aetherisOutput` | Error dict → `arbitrate_and_synthesize` wraps in safe `aetherisOutput` |
| DecisionEngine | `safe_parse_agent_output` | `AgentOutput` | Dict fallback → constructs `AgentOutput` with ERROR sentinel |

### Error Resilience

The pipeline never crashes due to malformed LLM output. Every parse failure produces a structured error response with:
- Confidence = 0.0
- Error message in the `answer` field
- Detailed `_parse_error` metadata for debugging

### Schema Drift Risk

The `AgentOutput` and `aetherisOutput` schemas are enforced at the parse boundary. However, the LLM is instructed about schema via **system prompts and runtime contracts**, not via structured API parameters. If the prompt text changes but the Pydantic model does not (or vice versa), the pipeline will silently repair or reject outputs rather than failing loudly.

The `response_format: {"type": "json_object"}` header (client.py:59) instructs the API to return JSON, but does not enforce a specific schema. Only NVIDIA NIM and local providers lack this header.

---

## 8. Pydantic Model Integration

### AgentOutput Schema

```python
class AgentOutput(BaseModel):
    model_config = ConfigDict(strict=True)
    
    reasoning_steps: list[str]
    answer: str
    confidence: float  # 0.0-1.0
```

**Pre-validation mapping** (model_validator mode="before"):
- `confidence` dict → float: `{"level": "high"}` → `0.9`
- `confidence` string → float: `"high"` → `0.9`
- `answer` fallback chains: `summary` → `draft_answer` → `primary_solution` → etc.
- `reasoning_steps` fallback chains: `claims` → `logical_analysis` → `progress` → etc.

### aetherisOutput Schema

```python
class aetherisOutput(BaseModel):
    model_config = ConfigDict(strict=True)
    
    final_answer: str
    overall_confidence: str  # "High" / "Medium" / "Low"
    overall_bias_risk: str   # "Low" / "Medium" / "High"
    disagreement_notes: list[str]
    validation_score: float  # 0.0-10.0
```

**Pre-validation mapping** (model_validator mode="before"):
- `final_answer` from `summary` fallback
- `overall_confidence` from numeric `confidence` (≥0.75 → "High", ≥0.4 → "Medium", else "Low")
- `overall_bias_risk` from `warnings` presence
- `disagreement_notes` from `warnings` list
- `validation_score` from `confidence` numeric (multiplied by 10)

### Field Mapping Duplication

Both `AgentOutput.map_contract_fields` and `aetherisOutput.map_contract_fields` implement:
1. Alternative field name resolution
2. Confidence label-to-value conversion
3. Default value assignment

The shared utility `resolve_field` in `core/validators.py:467-500` exists but is not used by either schema.

### Strict Mode Interaction

Both schemas use `ConfigDict(strict=True)`, which means Pydantic V2 will reject type mismatches (e.g., string where float is expected). However, the `mode="before"` model_validator runs **before** strict type checking, allowing coercion. The `confidence` field on `AgentOutput` has an additional `field_validator("confidence", mode="before")` for string-to-float conversion.

**Potential issue**: The `strict=True` mode is bypassed by the pre-validator for confidence. If the pre-validator fails or returns unexpected types, the strict check may then reject the value.

---

## 9. Prompt Assembly Performance

### Per-Request Overhead

| Operation | Count | Estimated Time |
|-----------|-------|---------------|
| File reads (XML) | 12 runtime + 1 system = 13 | ~10-50ms (SSD) |
| XML validations | 13 | ~5-20ms |
| String concatenation | ROLE + 12 contracts + prompt | ~1ms |
| **Total per agent** | | **~15-70ms** |
| **Total per request** (3 agents) | | **~45-210ms** |

This is the prompt assembly overhead **before any LLM call**. For comparison, the Breaker has a 100ms timeout, so prompt assembly alone can consume a significant portion of that budget.

### Caching Opportunity

The runtime contracts (12 XML files) are static. They could be cached in memory:

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_cached_runtime_contracts(prompts_dir: str) -> tuple[str, ...]:
    """Cache runtime contracts until server restart."""
    ...
```

This would eliminate ~10-50ms of file I/O per agent.

### Token Cost Per Agent

| Component | Estimated Tokens |
|-----------|-----------------|
| ROLE block | ~50 tokens |
| 12 runtime contracts | ~2000 tokens |
| System prompt | ~500 tokens |
| **Total per agent** | **~2550 tokens** |
| **Total per request** (3 agents) | **~7650 tokens** |

For a 3-agent pipeline (Breaker, Logician, Creative), approximately **7650 tokens** of context are consumed by system prompts alone, before counting the user query and conversation history.

---

## 10. Fallback & Error Handling

### Prompt-Level Fallbacks

| Fallback | Trigger | Behavior |
|----------|---------|----------|
| `load_system_prompt` → `PERSONA_REGISTRY` | XML file missing or invalid | Returns Python string constant instead of XML |
| `load_system_prompt` → empty string | Key missing in registry | Returns empty string (assembler skips empty parts) |
| `load_prompt_file` → empty string | File not found, permission error, I/O error | Logs warning, returns empty |
| `validate_xml` → invalid | ElementTree parse error | Logs error, returns empty |

### Pipeline-Level Fallbacks

| Fallback | Trigger | Behavior |
|----------|---------|----------|
| `parse_and_repair` → error dict | JSON parse or Pydantic validation failure | Returns structured error with confidence=0.0 |
| `_ensure_agent_output` → minimal AgentOutput | `parse_and_repair` returned dict | Constructs AgentOutput with error sentinel |
| `arbitrate_and_synthesize` → error dict | Judge parse failure | Wraps in safe aetherisOutput with validation_score=0.0 |
| `execute_with_fallback` → next model | Model call fails | Tries next model in chain |
| `_guarded_call` → retry | Exception | Retries up to 3 times with exponential backoff |

### Error Path: Agent Fails

```
gateway.execute_with_fallback() raises Exception
    │
    ├── Pipeline catches → logs error, records in passport
    │
    ├── Without DecisionEngine:
    │       return MicroModeResult(status="error", ...)
    │
    └── With DecisionEngine:
            execute_generation_agents returns (None, None) for failed agents
            ↓
            Judges synthesis receives AgentOutput placeholders
            ↓
            aetherisOutput constructed with fallback values
```

---

## 11. Security & Injection Prevention

### Multi-Layer Protection

| Layer | Mechanism | Enforced At |
|-------|-----------|-------------|
| 1. API Gateway | `SecurityValidator.validate_input` | Request entry (if called) |
| 2. Prompt Boundary | Separate system/user messages | `AsyncHTTPClient.post_request` |
| 3. JSON Escaping | `json.dumps()` wraps user content | `evaluation.py:60-63`, `security.py:272-276` |
| 4. Output Parsing | `parse_and_repair` only accepts JSON | `agents/parser.py` |
| 5. Schema Enforcement | Pydantic `model_validate` | `agents/parser.py:177` |

### Current Protection Gaps

**Layer 1 bypass**: The `SecurityValidator.validate_input` is called in `core/runtime.py` (never executed — dead code path). In the active pipeline path, user input passes through to `gateway.execute_with_fallback` without security validation. The only validation is the injection patterns in `AsyncHTTPClient` — but that's applied to the raw prompt string, not the user input specifically.

**Layer 2 robust**: The system prompt and user prompt are sent as separate messages (system role and user role). This provides a structural boundary that makes injection harder.

**Layer 3 applied only to judge**: `json.dumps()` escaping is only used in `evaluation.py:60-63` for the synthesizer prompt. The Breaker/Logician/Creative prompts use the raw query string via `gateway.execute_with_fallback(prompt=user_query, ...)`.

**Layer 4-5 robust**: All LLM outputs are parsed through `parse_and_repair` which enforces JSON structure and Pydantic schema validation.

### Layer 2: Message Boundary Certificate

The `AsyncHTTPClient.post_request` method (client.py:37-43) builds messages as:
```python
messages = []
if system_prompt:
    messages.append({"role": "system", "content": system_prompt})
messages.append({"role": "user", "content": prompt})
```

This structural separation means the user's input is always in a `"user"` role message, separate from `"system"` role messages. This is the **primary defense** against prompt injection — the model has been trained to respect message role boundaries.

**Instruction reinforcement** (client.py:47-49) adds a second system message after the user message:
```python
messages.append({
    "role": "system",
    "content": "CRITICAL REMINDER: ..."
})
```

This placement **after** the user message is unusual. Most LLM APIs expect all system messages before user messages. Some models may give lower priority to system messages appearing after user input.

---

## 12. Issue Register

### PRM-001: Synthesizer Fallback Key Mismatch

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `agents/prompt_manager.py` |
| **Lines** | 142-175 |
| **Function** | `load_system_prompt` |
| **Description** | The fallback key derivation splits the filename on `_` and takes the last part. For `09_synthesizer.xml`: `["09", "synthesizer"]` → `"synthesizer"`. The `PERSONA_REGISTRY` has keys `"logician"`, `"creative"`, `"breaker"`, `"verifier"`, `"skeptic"` — no `"synthesizer"` key. If the XML file is missing, the fallback returns empty string. |
| **Root Cause** | The registry was not updated when the synthesizer prompt was created as an XML file. |
| **Suggested Fix** | Add `"synthesizer": SYNTHESIZER_PROMPT` to `PERSONA_REGISTRY`, or use a more robust key mapping that strips the numeric prefix. |

### PRM-002: No XML Schema Validation

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `agents/prompt_manager.py` |
| **Lines** | 25-45 |
| **Function** | `validate_xml` |
| **Description** | The XML validator checks well-formedness (matching tags, no syntax errors) but does **not** validate against an XSD schema. Required elements, attributes, and structural constraints are not enforced. A runtime contract XML file with missing `<instructions>` section would pass validation. |
| **Root Cause** | ElementTree does not support XSD validation without additional libraries (lxml). |
| **Suggested Fix** | Add structural validation that checks for expected root element, required child tags, and non-empty content for each runtime contract. |

### PRM-003: Runtime Contracts Not Cached

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `agents/prompt_manager.py` |
| **Lines** | 103-139 |
| **Function** | `load_runtime_contracts` |
| **Description** | All 12 runtime contracts are loaded from disk, parsed, and validated on every `assemble_agent_prompt` call. These files are static and never change during runtime. With 3-4 agent prompts per pipeline request, this results in 36-48 file read + XML validation operations per request. |
| **Root Cause** | No caching mechanism was implemented for static XML files. |
| **Suggested Fix** | Add `functools.lru_cache` to `load_runtime_contracts` to cache the parsed contracts in memory. Clear cache on a configuration reload signal. |

### PRM-004: Instruction Reinforcement Schema Mismatch

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `api_gateway/client.py` |
| **Lines** | 47-49 |
| **Function** | `post_request` |
| **Description** | The "CRITICAL REMINDER" message (added after the user message) instructs output of exactly 3 fields (`reasoning_steps`, `answer`, `confidence` — the AgentOutput schema). However, the Judge (synthesizer) uses **aetherisOutput** schema with 5 different fields. This reminder may confuse the judge model and trigger unnecessary JSON repair. |
| **Root Cause** | Generic schema reinforcement without role awareness. |
| **Suggested Fix** | Make the reinforcement message role-aware. Pass the expected output schema from the caller and conditionally append schema-specific reminders. |

### PRM-005: Unused System Prompts Create Maintenance Burden

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `prompts/system/01-03, 07-08, 10-13` |
| **Lines** | — |
| **Function** | — |
| **Description** | 9 of 13 system prompt XML files are never loaded by the active pipeline. These files represent planned but unimplemented agents (Normalizer, Parameter Engine, separate Judges, Reasoning Budget, Streaming, Output Formatter, JSON Schema). They create confusion about the actual agent architecture and may drift from the active prompts. |
| **Root Cause** | Forward-looking design added prompt files before implementation. |
| **Suggested Fix** | Either (a) remove unused XML files and re-add when agents are implemented, or (b) move to a `prompts/system/unused/` directory with documentation. |

### PRM-006: Breaker Receives Full Runtime Contracts

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `agents/prompt_manager.py` |
| **Lines** | 276-338 |
| **Function** | `assemble_agent_prompt` |
| **Description** | The Breaker agent — designed as a "lightweight, fast" pre-filter with 100ms timeout — receives all 12 runtime contracts (~2000 tokens). This heavy context contradicts the Breaker's design purpose of minimal, fast gatekeeping. |
| **Root Cause** | All agents use the same prompt assembly pipeline without role-specific contract subsets. |
| **Suggested Fix** | Implement role-specific contract selection. The Breaker only needs contracts 00, 04, 05, 06, and 10. Consider a filter that maps role → [relevant contract indices]. |

### PRM-007: Evaluation Prompt Puts User Content in JSON

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `orchestrator/evaluation.py` |
| **Lines** | 60-63 |
| **Function** | `arbitrate_and_synthesize` |
| **Description** | User content is escaped via `json.dumps()` and placed inside an f-string template. While `json.dumps` is a strong injection defense, the template string is a Python f-string which could theoretically be exploited if `json.dumps` fails in unexpected ways. |
| **Root Cause** | Using f-string with escaped variables is the standard pattern, but a template-based approach would be safer. |
| **Suggested Fix** | Use a proper template system (e.g., `string.Template` or `jinja2`) to separate template structure from data. |

### PRM-008: No Conversation History in Judge Prompt

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `orchestrator/evaluation.py` |
| **Lines** | 65-100 |
| **Function** | `arbitrate_and_synthesize` |
| **Description** | The evaluation prompt for the synthesizer judge does not include conversation `history`. The function accepts a `history` parameter but never uses it in the prompt template. The judge evaluates Logician and Creative answers without the context of previous conversation turns. |
| **Root Cause** | History parameter was added to the function signature for future use but was never integrated into the prompt. |
| **Suggested Fix** | Add `<conversation_history>` section to the judge prompt template if history is provided. |

### PRM-009: Confidence Round-Trip Precision Loss

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `agents/prompt_utils.py`, `orchestrator/pipelines.py` |
| **Lines** | `prompt_utils.py:331`, `pipelines.py:744-746` |
| **Function** | `build_decision_dict`, `_build_frontend_payload` |
| **Description** | Confidence values undergo a float-to-score-to-float round trip: `0.75` → `0.75 * 10 = 7.5` (in `build_decision_dict` score_a/score_b) → `7.5 / 10 = 0.75` (in `_build_frontend_payload`). While mathematically reversible, the intermediate representation (`score_a: 7.5`) is semantically misleading — it appears to be a 0-10 scale score but is actually derived from agent self-confidence. |
| **Root Cause** | The frontend expects scores on a 0-10 scale, but agent confidence is 0-1. |
| **Suggested Fix** | Use separate fields: `logician_confidence` (0-1) and `logician_score` (0-10 from judge evaluation). Currently both fields are populated from agent self-confidence. |

### PRM-010: No Load Time Verification in Production

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `agents/prompt_manager.py` |
| **Lines** | 178-273 |
| **Function** | `get_load_order_verification` |
| **Description** | The `get_load_order_verification` function provides a comprehensive prompt hierarchy validation (missing files, XML validity, expected load order). However, it is never called at startup or in any CI/CD pipeline. Prompt file issues would only be discovered at runtime when the pipeline fails to load an expected prompt. |
| **Root Cause** | The verification function was created but never wired into the startup sequence. |
| **Suggested Fix** | Call `get_load_order_verification()` during `initialize_aetheris_components()` and log warnings for any missing or invalid prompt files. Optionally, add a `--verify-prompts` CLI flag. |

---

## Summary

| Category | Status | Issues |
|----------|--------|--------|
| **XML Contract Coverage** | ✅ All 12 runtime contracts loaded and validated | 1 |
| **Schema Validation** | ✅ 3-stage parse pipeline with Pydantic enforcement | 0 |
| **Injection Prevention** | ⚠️ Strong message-boundary protection; security validator bypassed in active path | 1 |
| **Execution Order** | ⚠️ 4 of 13 stages implemented; 9 prompt files unused | 2 |
| **Breaker Gate** | ✅ Never answers prompts (3-layer enforcement) | 0 |
| **Judge Role** | ✅ Never generates answers (schema-enforced) | 0 |
| **Fusion Engine** | ✅ Synthesizer produces final reasoning | 0 |
| **Output Formatter** | ✅ Frontend payload correctly assembled | 1 |
| **Prompt Assembly** | ⚠️ No caching, heavy per-request overhead | 2 |
| **Error Resilience** | ✅ Multi-level fallback chain for all prompt loading | 0 |
| **Security** | ⚠️ Good architecture with inactive validation layer | 1 |
| **Performance** | ⚠️ ~45-210ms prompt assembly overhead per request | 2 |
