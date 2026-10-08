"""Local Presidio detection and per-request reversible placeholders, never persisted."""

import re
import secrets
from functools import lru_cache
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

from config import Settings
from errors import ServiceError

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=2)
def analyzer(mode: str, model: str) -> "AnalyzerEngine":
    import spacy
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
    from presidio_analyzer.nlp_engine import SpacyNlpEngine
    from presidio_analyzer.predefined_recognizers import (
        CreditCardRecognizer,
        EmailRecognizer,
        IbanRecognizer,
        IpRecognizer,
        PhoneRecognizer,
        SpacyRecognizer,
    )

    # Never let Presidio auto-download a model during a request.
    engine = SpacyNlpEngine(models=[{"lang_code": "en", "model_name": model}])
    # Presidio's annotation is inferred as None although load() also assigns this dictionary.
    engine.nlp = {"en": spacy.blank("en") if mode == "patterns" else spacy.load(model)}  # type: ignore[assignment]
    registry = RecognizerRegistry(supported_languages=["en"])
    for recognizer in [EmailRecognizer(), PhoneRecognizer(), CreditCardRecognizer(), IbanRecognizer(), IpRecognizer()]:
        registry.add_recognizer(recognizer)
    if mode == "standard":
        registry.add_recognizer(SpacyRecognizer(supported_entities=["PERSON", "LOCATION"]))
    for entity, expression in [
        ("IN_PAN", r"\b[A-Z]{5}\d{4}[A-Z]\b"),
        ("IN_AADHAAR", r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b"),
        ("PHONE_NUMBER", r"(?<!\w)(?:\+91[ -]?)?[6-9]\d{9}(?!\w)"),
        ("STREET_ADDRESS", r"\b\d{1,5}\s+(?:[A-Za-z]+\s+){1,5}(?:Street|Road|Lane|Avenue|Marg)\b"),
    ]:
        registry.add_recognizer(PatternRecognizer(
            supported_entity=entity, patterns=[Pattern(name=entity, regex=expression, score=0.85)],
        ))
    return AnalyzerEngine(nlp_engine=engine, registry=registry, supported_languages=["en"], log_decision_process=False)


class RedactionVault:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.prefix = f"PII_{secrets.token_hex(4)}_"
        self.values: dict[str, str] = {}
        self.reverse: dict[tuple[str, str], str] = {}

    def redact(self, text: str) -> str:
        if not text:
            return text
        try:
            engine = analyzer(self.settings.pii_mode, self.settings.pii_model)
            matches = engine.analyze(text=text, language="en", score_threshold=0.5)
        except Exception as exc:
            raise ServiceError(503, "PII redaction is unavailable. Install the configured local model before analysis.") from exc
        # Higher-confidence/longer detections win overlaps. Replacement order is deterministic.
        selected: list[tuple[int, int, str]] = []
        for match in sorted(matches, key=lambda item: (-item.score, -(item.end - item.start), item.start)):
            if any(match.start < end and match.end > start for start, end, _ in selected):
                continue
            selected.append((match.start, match.end, match.entity_type))
        result = text
        for start, end, entity in sorted(selected, reverse=True):
            value = text[start:end]
            key = (entity, value)
            token = self.reverse.get(key)
            if token is None:
                token = f"[{self.prefix}{entity}_{len(self.values) + 1}]"
                self.reverse[key], self.values[token] = token, value
            result = result[:start] + token + result[end:]
        return result

    def restore(self, text: str) -> str:
        # One substitution pass: source text that resembles another placeholder is not re-expanded.
        pattern = re.compile(r"\[" + re.escape(self.prefix) + r"[A-Z_]+_\d+\]")
        return pattern.sub(lambda match: self.values.get(match.group(), "[unrecognized redaction]"), text)

    def restore_model(self, value: T) -> T:
        def restore_value(item: Any) -> Any:
            if isinstance(item, str):
                return self.restore(item)
            if isinstance(item, list):
                return [restore_value(child) for child in item]
            if isinstance(item, dict):
                return {key: restore_value(child) for key, child in item.items()}
            return item
        return type(value).model_validate(restore_value(value.model_dump()))
