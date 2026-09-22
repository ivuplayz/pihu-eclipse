"""Provider abstractions for Pihu-BreakThough.

This module deliberately keeps provider-specific details behind one interface.
Adding or removing a provider must not require changes to Pihu's brain.
"""

from dataclasses import dataclass
from typing import Any, Optional

import requests

from . import config


@dataclass
class ProviderResult:
    ok: bool
    provider: str
    text: str = ""
    error: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class AIProvider:
    name = "base"

    def available(self) -> bool:
        return False

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> ProviderResult:
        raise NotImplementedError


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self) -> None:
        self.client = None
        if config.GEMINI_API_KEY:
            try:
                from google import genai
                self.client = genai.Client(api_key=config.GEMINI_API_KEY)
            except Exception:
                self.client = None

    def available(self) -> bool:
        return self.client is not None

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> ProviderResult:
        if not self.available():
            return ProviderResult(False, self.name, error="Gemini is not configured.")
        try:
            prompt = "\n\n".join(
                f"{item['role'].upper()}: {item['content']}" for item in messages
            )
            response = self.client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
            )
            text = getattr(response, "text", None) or ""
            if not text:
                return ProviderResult(False, self.name, error="Gemini returned no text.")
            return ProviderResult(True, self.name, text=text)
        except Exception as exc:
            return ProviderResult(False, self.name, error=str(exc))


class GroqProvider(AIProvider):
    name = "groq"

    def available(self) -> bool:
        return bool(config.GROQ_API_KEY)

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> ProviderResult:
        if not self.available():
            return ProviderResult(False, self.name, error="Groq is not configured.")
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.GROQ_MODEL,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", 0.7),
                },
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            text = payload["choices"][0]["message"]["content"]
            return ProviderResult(True, self.name, text=text)
        except Exception as exc:
            return ProviderResult(False, self.name, error=str(exc))


class HuggingFaceProvider(AIProvider):
    name = "huggingface"

    def available(self) -> bool:
        return bool(config.HF_API_KEY and config.HF_MODEL)

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> ProviderResult:
        if not self.available():
            return ProviderResult(False, self.name, error="Hugging Face is not configured.")
        try:
            response = requests.post(
                "https://router.huggingface.co/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.HF_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.HF_MODEL,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", 0.7),
                },
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            text = payload["choices"][0]["message"]["content"]
            return ProviderResult(True, self.name, text=text)
        except Exception as exc:
            return ProviderResult(False, self.name, error=str(exc))


class OllamaProvider(AIProvider):
    name = "ollama"

    def available(self) -> bool:
        # This is deliberately an optional provider. Cloud Pihu never depends on it.
        try:
            response = requests.get(
                f"{config.OLLAMA_BASE_URL}/api/tags",
                timeout=2,
            )
            return response.ok
        except requests.RequestException:
            return False

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> ProviderResult:
        if not self.available():
            return ProviderResult(False, self.name, error="Local Ollama is offline.")
        try:
            prompt = "\n\n".join(
                f"{item['role'].upper()}: {item['content']}" for item in messages
            )
            response = requests.post(
                f"{config.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": config.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            text = response.json().get("response", "")
            return ProviderResult(bool(text), self.name, text=text, error=None if text else "No local response.")
        except Exception as exc:
            return ProviderResult(False, self.name, error=str(exc))



def default_ai_providers() -> list[AIProvider]:
    """Return providers in preferred order. Local Ollama is always last."""
    return [
        GeminiProvider(),
        GroqProvider(),
        HuggingFaceProvider(),
        OllamaProvider(),
    ]
