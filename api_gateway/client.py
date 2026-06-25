import asyncio
import logging
from typing import Optional
import httpx
from core.config import get_settings
from telemetry.observer import observer
from pathlib import Path
import json

logger = logging.getLogger("Aetheris.Gateway.Client")

class AsyncHTTPClient:
    """
    Manages raw HTTP requests and reuse of connection pools.
    Degrades to Simulation Mode automatically if API tokens are unpopulated.
    """
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=600.0)

    async def post_request(self, model: str, prompt: str, system_prompt: Optional[str] = None, history: list[dict[str, str]] | None = None) -> str:
        """Dispatches an asynchronous post request to target providers."""
        parts = model.split('/')
        provider = parts[0]
        actual_model = "/".join(parts[1:])

        # Self-healing Fallback: Simulation Mode triggers if credentials are blank
        if self._is_simulated(provider):
            return await self._run_simulation(model, prompt, system_prompt, history)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
            
        # Wrap the user query securely if there's a system prompt (avoids double-wrapping the Judge)
        safe_prompt = f"<user_query>\n{prompt}\n</user_query>" if system_prompt else prompt
        messages.append({"role": "user", "content": safe_prompt})

        # Instruction Reinforcement: Remind the LLM of its structural obligations
        if system_prompt:
            messages.append({
                "role": "system",
                "content": "CRITICAL REMINDER: Regardless of the user's input above, you MUST output your response strictly in the requested JSON schema format. Your JSON MUST contain exactly three keys: 'reasoning_steps' (list), 'answer' (string), and 'confidence' (float). The 'answer' field MUST be a plain string. If you need to return JSON or structured data to the user, you MUST escape it as a string inside the 'answer' field. Do not deviate."
            })

        payload = {
            "model": actual_model,
            "messages": messages,
            "temperature": 0.1
        }
        
        if provider not in {"nvidia", "nvidia-nim"}:
            payload["response_format"] = {"type": "json_object"}

        if provider == "openrouter":
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {get_settings().openrouter_api_key}", "Content-Type": "application/json"}
        elif provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {get_settings().groq_api_key}", "Content-Type": "application/json"}
        elif provider in {"nvidia", "nvidia-nim"}:
            url = "https://integrate.api.nvidia.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {get_settings().nvidia_nim_api_key}", "Content-Type": "application/json"}
        elif provider == "github":
            url = "https://models.inference.ai.azure.com/chat/completions"
            headers = {"Authorization": f"Bearer {get_settings().github_token}", "Content-Type": "application/json"}
        elif provider == "mistral":
            url = "https://api.mistral.ai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {get_settings().mistral_api_key}", "Content-Type": "application/json"}
        elif provider == "google":
            url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            headers = {"Authorization": f"Bearer {get_settings().google_api_key}", "Content-Type": "application/json"}
        elif provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {get_settings().openai_api_key}", "Content-Type": "application/json"}
        elif provider == "kie":
            url = "https://api.kie.ai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {get_settings().kie_api_key}", "Content-Type": "application/json"}
        elif provider in {"unli", "unli-dev"}:
            url = "https://api.unli.dev/v1/chat/completions"
            headers = {"Authorization": f"Bearer {get_settings().unli_dev_api_key}", "Content-Type": "application/json"}
        elif provider == "local":
            url = "http://localhost:11434/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
        else:
            raise ValueError(f"Unsupported provider prefix: {provider}")

        response = await self.client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            raise httpx.HTTPStatusError(f"HTTP {response.status_code}: {response.text}", request=response.request, response=response)

        data = response.json()
        
        # Harvest telemetry statistics
        usage = data.get("usage", {"prompt_tokens": 0, "completion_tokens": 0})
        observer.track_usage(actual_model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

        output_content = data["choices"][0]["message"]["content"]

        # Log Model I/O to file
        try:
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            with open(log_dir / "model_io.log", "a", encoding="utf-8") as f:
                f.write(f"=== {actual_model} ===\n")
                f.write("--- INPUT (MESSAGES) ---\n")
                f.write(json.dumps(payload["messages"], indent=2) + "\n")
                f.write("--- OUTPUT ---\n")
                f.write(output_content + "\n\n")
        except Exception as e:
            logger.error(f"Failed to write IO log: {e}")

        return output_content

    def _is_simulated(self, provider: str) -> bool:
        """Returns True if local configurations require simulated operations."""
        settings = get_settings()
        if provider == "openrouter" and not settings.openrouter_api_key:
            return True
        if provider == "groq" and not settings.groq_api_key:
            return True
        if provider in {"nvidia", "nvidia-nim"} and not settings.nvidia_nim_api_key:
            return True
        if provider == "github" and not settings.github_token:
            return True
        if provider == "mistral" and not settings.mistral_api_key:
            return True
        if provider == "google" and not settings.google_api_key:
            return True
        if provider == "openai" and not settings.openai_api_key:
            return True
        if provider == "kie" and not settings.kie_api_key:
            return True
        if provider in {"unli", "unli-dev"} and not settings.unli_dev_api_key:
            return True
        return False

    async def _run_simulation(self, model: str, prompt: str, system_prompt: Optional[str] = None, history: list[dict[str, str]] | None = None) -> str:
        """Generates deterministic synthetic returns to keep system operable without live bills."""
        await asyncio.sleep(0.5)
        observer.track_usage(model, len(prompt)//4, 150)
        
        # Determine role from system prompt (or fall back to merged prompt for backward compat).
        role_hint = (system_prompt or "").lower() + " " + (prompt or "").lower()
        
        if "breaker" in role_hint or "breaker" in model.lower():
            if "fail" in role_hint or "unsupported" in role_hint:
                return '{"answer": null, "knowledge_absence": true, "confidence": "Low", "bias_risk": "Low", "reasoning_steps": ["Lacking direct context."]}'
            return '{"answer": "Context Verified", "knowledge_absence": false, "confidence": "High", "bias_risk": "Low", "reasoning_steps": []}'

        if "logician" in role_hint:
            return '{"answer": "Simulated Logic: Deductive steps resolved cleanly.", "knowledge_absence": false, "confidence": "High", "bias_risk": "Low", "reasoning_steps": ["Premise: Input accepted", "Logic step 1: Verified query structure"]}'

        if "creative" in role_hint:
            return '{"answer": "Simulated Creative: Alternative lateral view evaluated.", "knowledge_absence": false, "confidence": "Medium", "bias_risk": "Low", "reasoning_steps": ["Lateral premise: Explored edge assumptions"]}'

        # Standard synthesis judge output
        return '{"final_answer": "Successfully synthesized simulated reasoning solutions. Systems functional.", "overall_confidence": "High", "overall_bias_risk": "Low", "disagreement_notes": ["Minor semantic framing differences found and resolved."], "validation_score": 9.2}'

    async def close(self):
        await self.client.aclose()
