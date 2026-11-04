"""AI provider abstraction. Claude is primary; others can be added behind the same interface.
Never fabricates output: without credentials it raises AINotConfigured."""
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings


class AINotConfigured(RuntimeError):
    pass


class AIProvider(Protocol):
    name: str

    async def complete(self, system: str, prompt: str, max_tokens: int = 1000) -> str: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, transport: httpx.AsyncBaseTransport | None = None):
        self.api_key, self.model, self.transport = api_key, model, transport

    async def complete(self, system: str, prompt: str, max_tokens: int = 1000) -> str:
        async with httpx.AsyncClient(timeout=60, transport=self.transport) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                json={"model": self.model, "max_tokens": max_tokens, "system": system,
                      "messages": [{"role": "user", "content": prompt}]},
            )
            resp.raise_for_status()
            return "".join(b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text")


def get_ai_provider(settings: Settings | None = None) -> AIProvider:
    s = settings or get_settings()
    if not s.anthropic_api_key:
        raise AINotConfigured("ANTHROPIC_API_KEY is not set.")
    return AnthropicProvider(s.anthropic_api_key, s.anthropic_model)
