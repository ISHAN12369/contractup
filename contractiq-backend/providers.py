"""Bounded provider fallback; never mix a partial stream with a second provider."""
import time
from collections.abc import Callable, Iterator
from threading import Event
from typing import TypeVar

from pydantic import BaseModel

from config import Settings
from errors import ServiceError
from llm import GroqLLM
from telemetry import provider_span

T = TypeVar("T", bound=BaseModel)


class ProviderChain:
    def __init__(self, providers: list[GroqLLM]):
        if not providers:
            raise ValueError("At least one provider is required")
        self.providers = providers

    def close(self) -> None:
        for provider in self.providers:
            provider.close()

    def generate(self, schema: type[T], prompt: str, *, deadline: float,
                 validate: Callable[[T], None] | None = None) -> T:
        for index, provider in enumerate(self.providers):
            budget = deadline if index == len(self.providers) - 1 else time.monotonic() + max(0, deadline - time.monotonic()) / 2
            try:
                with provider_span(provider.name, provider.settings.groq_model) as usage:
                    try:
                        return provider.generate(schema, prompt, deadline=budget, validate=validate)
                    finally:
                        usage.update(provider.usage)
            except ServiceError as exc:
                if exc.status not in {502, 503, 504} or index == len(self.providers) - 1 or time.monotonic() >= deadline:
                    raise
        raise ServiceError(503, "The analysis providers are unavailable.")

    def stream_json(self, schema: type[BaseModel], prompt: str, *, deadline: float, cancelled: Event) -> Iterator[str]:
        for index, provider in enumerate(self.providers):
            emitted = False
            budget = deadline if index == len(self.providers) - 1 else time.monotonic() + max(0, deadline - time.monotonic()) / 2
            try:
                with provider_span(provider.name, provider.settings.groq_model) as usage:
                    try:
                        for delta in provider.stream_json(schema, prompt, deadline=budget, cancelled=cancelled):
                            if cancelled.is_set():
                                return
                            emitted = emitted or bool(delta)
                            yield delta
                    finally:
                        usage.update(provider.usage)
                return
            except ServiceError as exc:
                if emitted or cancelled.is_set() or exc.status not in {502, 503, 504} or index == len(self.providers) - 1:
                    raise


def create_provider(settings: Settings) -> ProviderChain:
    providers = [GroqLLM(settings)]
    if settings.fallback_api_key:
        fallback = settings.model_copy(update={"groq_api_key": settings.fallback_api_key,
            "groq_model": settings.fallback_model, "structured_mode": settings.fallback_structured_mode})
        providers.append(GroqLLM(fallback, base_url=settings.fallback_base_url, name="fallback"))
    return ProviderChain(providers)
