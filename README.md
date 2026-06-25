# Aetheris — Adaptive Multi-Model Reasoning Orchestrator

> **[ACTIVE DEVELOPMENT]** A resilient multi-agent reasoning engine that orchestrates LLM agents through a validation-arbitration pipeline, utilizing dynamic runtime prompt layering, and automatically falling back across providers when models fail.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Pydantic V2](https://img.shields.io/badge/Pydantic-V2-e92063.svg)](https://docs.pydantic.dev/)

---

## What is Aetheris?

Aetheris is an advanced **multi-agent reasoning orchestrator** designed to produce high-quality, validated responses by running multiple AI agents in parallel and utilizing a synthesis judge to arbitrate the final result.

Instead of relying on a single raw model call, Aetheris executes a robust **four-stage pipeline**:

1. **Breaker Gate** — A lightweight pre-filter checks if the system has sufficient context to answer. If not, it aborts immediately.
2. **Logician Agent** — Generates a strictly deductive, logically valid answer.
3. **Creative Agent** — Generates an orthogonal, lateral-thinking answer exploring edge cases and alternatives.
4. **Synthesis Judge** — Evaluates both answers for logical consistency, resolves contradictions, and produces a single authoritative response with a validation score.

The entire pipeline is **async-native**, runs with **bounded concurrency**, and **automatically falls back** across multiple LLM providers if a model is down, rate-limited, or returns garbage.

---

## Technical Stack & Built-With

* **Core Backend:** Python 3.11+ (`asyncio`, `httpx.AsyncClient`)
* **API Framework:** FastAPI & Uvicorn for asynchronous server endpoints
* **Data Validation:** Pydantic V2 & Pydantic-Settings for config validation and data contracts
* **Output Processing:** `json-repair` for parsing and correcting malformed JSON LLM outputs
* **Prompt Layout:** Strictly validated XML formats layered dynamically at runtime
* **Frontend Web Dashboard:** Glassmorphism UI built with modern HTML5, CSS3 (Vanilla), and Vanilla JS
* **LLM Providers:** Native integration with OpenRouter, Groq, NVIDIA NIM, GitHub Models, and local Ollama

---

## Core Features & Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────┐
│   User      │────▶│  FastAPI Server │────▶│  Breaker     │
│  (Browser)  │     │  / CLI REPL     │     │  Gate        │
└─────────────┘     └─────────────────┘     └──────────────┘
                                                     │
                              ┌──────────────────────┘
                              ▼
              ┌─────────────────────────────┐
              │  Logician Agent  │  Creative │
              │  (deductive)     │  Agent    │
              │                  │ (lateral) │
              └────────┬─────────┴─────┬─────┘
                       │                 │
                       ▼                 ▼
              ┌─────────────────────────────┐
              │    Synthesis Judge           │
              │  (arbitrate + validate)     │
              └──────────────┬──────────────┘
                             │
                             ▼
              ┌─────────────────────────────┐
              │  Final Answer + Score +     │
              │  Agent Reasoning (expandable)│
              └─────────────────────────────┘
```

### 1. Dynamic Runtime Prompt Layering
To enforce system instructions and role boundaries, Aetheris dynamically layers prompts before sending payloads to the LLM:

* **Layer 1: `<ROLE>` Block** — Dynamically injected metadata defining the current role, active pipeline stage, objective, iteration count, and execution mode.
* **Layer 2: Runtime Prompts (`prompts/runtime/`)** — Global runtime constraints loaded and appended sequentially (`00_agent_runtime.xml`, `01_prompt_loader.xml`, `02_response_contract.xml`, `03_context_manager.xml`, etc.).
* **Layer 3: Agent Persona Prompts (`prompts/system/`)** — The specific instruction set matching the active agent (e.g. `05_logician.xml` or `06_creative.xml`).

All prompt templates are formatted in clean, single-root XML structures for structural validation and machine-readability.

### 2. Multi-Model Fallback & Circuit Breaking
* **Priority Routing:** If the primary model for a stage fails or times out, the system automatically escalates to a fallback provider chain.
* **Circuit Breaker:** Tracks failures per provider. If a provider fails 3 consecutive times, it enters cooldown (`DEAD`) and is bypassed for 60 seconds.
* **Simulation Mode:** Automatically matches environment variables. If no API keys are present, the system runs with deterministic mock responses to enable cost-free development.

---

## Advantages

| Feature | Why it matters |
|---------|---------------|
| **Validation Arbitrage** | Two agents (Logician + Creative) reason independently; the Judge resolves contradictions and scores consistency. You get a confidence score, not just a guess. |
| **Provider Resilience** | Supports OpenRouter, Groq, NVIDIA NIM, GitHub Models, and local Ollama. If one provider is down, the pipeline automatically tries the next. |
| **Circuit Breaker + Cooldown** | Dead providers are automatically excluded. No manual intervention needed when a service is rate-limited or flaky. |
| **Zero-cost Testing** | Simulation mode works without any API keys. Test the full pipeline, UI, and error paths locally for free. |
| **Structured, Typed Outputs** | Every agent response is validated against Pydantic V2 schemas. Malformed JSON is auto-repaired before validation. |
| **Dark-mode Web UI** | A premium glassmorphism chat interface with animated pipeline progress, expandable agent reasoning, telemetry dashboard, and responsive design. |
| **Async-Native** | Built on `asyncio`, `httpx.AsyncClient`, and `FastAPI`. Handles concurrent agent calls without blocking. |
| **Three Operating Modes** | `FREE` (open-weight models only), `HYBRID` (premium + free fallback), `PAID` (top-tier models only). Switch without code changes. |

---

## Installation

### 1. Clone the repository
```bash
git clone <repository-url>
cd aetheris
```

### 2. Create a virtual environment
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables (optional)
Create a `.env` file in the project root:
```bash
# OpenRouter (recommended — gives access to 100+ models)
AETHERIS_OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx

# Groq (fast inference)
AETHERIS_GROQ_API_KEY=gsk_xxxxxxxx

# NVIDIA NIM
AETHERIS_NVIDIA_NIM_API_KEY=nvapi-xxxxxxxx

# GitHub Models
AETHERIS_GITHUB_TOKEN=ghp_xxxxxxxx

# Logging
AETHERIS_LOG_LEVEL=INFO
```
*(Note: If you leave keys blank, the system defaults to Simulation Mode).*

---

## How to Run

### Terminal REPL (default)
```bash
python main.py
```

### Web UI
```bash
python main.py --web
```
Then open your browser at `http://localhost:8000`.

---

## Project Structure

```
aetheris/
├── main.py                    # CLI entry point (REPL + --web flag)
├── server.py                  # FastAPI web server
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (gitignored)
├── .gitignore
│
├── core/
│   ├── config.py              # Pydantic-Settings configuration loader
│   └── schemas.py             # Pydantic V2 data contracts (AgentOutput, AetherisOutput)
│
├── api_gateway/
│   ├── client.py              # HTTPX AsyncClient + simulation mode
│   ├── rate_limiter.py        # Semaphore, circuit breaker, retry-with-backoff
│   └── strategy.py            # FREE / HYBRID / PAID model mapping
│
├── agents/
│   ├── parser.py              # JSON repair + Pydantic validation pipeline
│   └── personas.py            # System prompts (Breaker, Logician, Creative, etc.)
│
├── orchestrator/
│   ├── pipelines.py           # Micro-Mode async execution pipeline
│   ├── evaluation.py          # Synthesis judge (arbitrate + validate)
│   └── memory.py              # Epistemic failure-tracking bus
│
├── prompts/
│   ├── runtime/               # Config contracts loaded dynamically
│   └── system/                # Agent personas (Logician, Breaker, etc.)
│
├── telemetry/
│   └── observer.py            # Token/cost tracking & session reports
│
└── web/
    └── index.html             # Single-page dark-mode chat UI
```

---

## Operating Modes

| Mode | Models Used | Cost | Best For |
|------|------------|------|----------|
| `FREE` | Llama 3, Mistral, Gemma | $0 | Testing, development, low-stakes queries |
| `HYBRID` | Claude 3.5 Sonnet + GPT-4o-mini + Llama 3 fallback | Low | Balanced quality and cost |
| `PAID` | Claude 3.5 Sonnet + GPT-4o + Llama 3.1 70B | Higher | Maximum accuracy, production use |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ImportError: No module named 'json_repair'` | Run `pip install -r requirements.txt` |
| All queries return `"KNOWLEDGE ABSENCE DETECTED"` | The Breaker agent is conservative. Try queries with more factual grounding. |
| Provider shows `DEAD` in status | The provider hit 3 failures. It will auto-recover after 60 seconds. Check your API key. |
| Web UI shows 404 | Ensure `web/index.html` exists. The server serves it from the `web/` directory. |

---

## License

MIT License — see LICENSE file for details.
