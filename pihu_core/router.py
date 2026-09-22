"""Pihu's provider router.

The router chooses providers by capability and availability. It never turns on
paid billing and never relies on the user's PC being online.
"""

from typing import Any

from .providers import ProviderResult, default_ai_providers


class PihuRouter:
    def __init__(self) -> None:
        self.ai_providers = default_ai_providers()

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> ProviderResult:
        """Try configured free-capable AI providers in order.

        Providers are adapters, not the brain. Pihu's orchestration layer will
        later decide whether this call should happen at all and which capability
        pool should receive the task.
        """
        failures: list[str] = []
        for provider in self.ai_providers:
            if not provider.available():
                continue
            result = provider.generate(messages, **kwargs)
            if result.ok:
                return result
            failures.append(f"{provider.name}: {result.error or 'failed'}")

        return ProviderResult(
            ok=False,
            provider="router",
            error="No configured free AI provider is currently available. " + "; ".join(failures),
        )

    def capabilities(self) -> dict[str, list[str]]:
        return {
            "ai": [p.name for p in self.ai_providers if p.available()],
            "image": [],
            "vision": [],
            "speech_to_text": [],
            "text_to_speech": [],
            "search": [],
        }
