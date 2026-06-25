import logging
from typing import Dict

logger = logging.getLogger("Aetheris.Telemetry")

# Accurate industry pricing rates per 1,000,000 tokens (Standardized pricing in USD)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "llama-3-8b-instruct": {"input": 0.05, "output": 0.08},
    "qwen-2-7b-instruct": {"input": 0.05, "output": 0.05},
    "llama3-8b-8192": {"input": 0.05, "output": 0.08},
    "llama3-70b-instruct": {"input": 0.59, "output": 0.79},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "default": {"input": 0.10, "output": 0.20}
}

class TelemetryObserver:
    """
    Monitors execution latencies, token consumption metrics, and query costs.
    """
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.accumulated_cost_usd = 0.0
        self.transaction_count = 0

    def track_usage(self, model_string: str, input_tokens: int, output_tokens: int):
        """Calculates exact usage costs and aggregates telemetry data."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.transaction_count += 1

        # Match model signature to pricing cards
        model_key = "default"
        for key in MODEL_PRICING.keys():
            if key in model_string.lower():
                model_key = key
                break

        rates = MODEL_PRICING[model_key]
        cost = ((input_tokens / 1_000_000) * rates["input"]) + ((output_tokens / 1_000_000) * rates["output"])
        self.accumulated_cost_usd += cost

        logger.info(
            f"[METRIC] Model: {model_string} | Tokens: I={input_tokens}/O={output_tokens} | Cost: ${cost:.6f}"
        )

    def print_session_report(self):
        """Outputs summary metrics for system auditing."""
        print("\n" + "="*50)
        print("Aetheris TELEMETRY SESSION REPORT")
        print("="*50)
        print(f"Total Model Calls:   {self.transaction_count}")
        print(f"Total Input Tokens:  {self.total_input_tokens}")
        print(f"Total Output Tokens: {self.total_output_tokens}")
        print(f"Total Cost (USD):    ${self.accumulated_cost_usd:.6f}")
        print("="*50 + "\n")

# Global Telemetry Observer
observer = TelemetryObserver()
