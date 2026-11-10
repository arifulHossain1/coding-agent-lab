"""Chat with the local Ollama server without interpreting model actions."""

import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaClient:
    """Request non-streaming JSON replies from a locally hosted model."""

    def __init__(self, model: str | None = None, temperature: float = 0.0):
        self.model = model or os.environ.get("OLLAMA_MODEL") or "qwen2.5-coder:7b"
        if not math.isfinite(temperature) or temperature < 0:
            raise ValueError("Temperature must be finite and non-negative")
        self.temperature = temperature

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return reply text unchanged; RepairAgent validates the action JSON."""
        request = Request(
            "http://127.0.0.1:11434/api/chat",
            data=json.dumps({
                "model": self.model, "messages": messages,
                "stream": False, "format": "json",
                "options": {"temperature": self.temperature},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                envelope = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"Local Ollama returned HTTP {exc.code}; check that model {self.model!r} is installed") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Unable to contact local Ollama: {exc}") from exc
        if not isinstance(envelope, dict):
            raise RuntimeError("Invalid Ollama response envelope")
        if envelope.get("error"):
            raise RuntimeError(f"Ollama error: {envelope['error']}")
        message = envelope.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise RuntimeError("Ollama response has no message content")
        return message["content"]
