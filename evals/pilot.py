"""Bounded live pilot: one CUAD query and three fixed golden queries, six configs."""
import argparse
import os
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

import httpx
from config import Settings
from dotenv import load_dotenv
from llm import GroqLLM

from evals import BACKEND, ROOT
from evals.data import Document, digest, load_cuad, load_golden
from evals.report import write_report
from evals.run import evaluate, provenance


class RequestPacer:
    """Space actual HTTP requests, including schema retries, across both clients."""

    def __init__(self, interval: float = 3.0):
        self.interval = interval
        self.last: float | None = None

    def __call__(self, request: httpx.Request) -> None:
        if self.last is not None:
            time.sleep(max(0.0, self.last + self.interval - time.monotonic()))
        self.last = time.monotonic()


def golden_pilot(path: Path) -> list[Document]:
    document = next(d for d in load_golden(path) if d.id == "golden-lease")
    # Deposit exception, termination condition, and a missing term. Fixed before scoring.
    questions = [q for q in document.questions if q.id in {"golden-lease:2", "golden-lease:5", "golden-lease:8"}]
    if len(questions) != 3:
        raise ValueError("The pilot requires the three original lease questions")
    return [replace(document, questions=questions)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("evals/runs/provider-pilot"))
    parser.add_argument("--env-file", type=Path, help="Explicit local config; overrides existing environment values")
    args = parser.parse_args()
    load_dotenv(args.env_file or BACKEND / ".env", override=args.env_file is not None)
    settings = Settings.from_env().model_copy(update={"model_cache_dir": BACKEND / "model-cache"})
    if not settings.groq_api_key:
        parser.error("Configure GROQ_API_KEY locally before running this live pilot")
    golden = ROOT / "evals/fixtures/golden.json"
    documents, dataset = load_cuad(ROOT / "evals/.cache/cuad-data.zip", 1, 1, 42, settings.max_text_chars)
    documents += golden_pilot(golden)
    judge_model = os.getenv("EVAL_JUDGE_MODEL", settings.groq_model)
    manifest = provenance(settings)
    manifest.update(cuad=dataset, golden_sha256=digest(golden),
                    pilot="one seeded CUAD question plus golden-lease questions 2, 5, 8; six configurations",
                    judge_model=judge_model, judge_same_as_generator=judge_model == settings.groq_model,
                    minimum_request_interval_seconds=3.0)
    pacer = RequestPacer()
    statuses: Counter[int] = Counter()

    def observe(response: httpx.Response) -> None:
        statuses[response.status_code] += 1

    provider = GroqLLM(settings, httpx.Client(event_hooks={"request": [pacer], "response": [observe]}))
    judge = GroqLLM(settings.model_copy(update={"groq_model": judge_model}),
                    httpx.Client(event_hooks={"request": [pacer], "response": [observe]}))
    try:
        report = evaluate(documents, settings, args.output, manifest, online=True, llm=provider, judge=judge)
        report["provenance"]["provider_http_status_counts"] = dict(statuses)
        write_report(args.output, report)
    finally:
        provider.close()
        judge.close()
    print(f"{report['status']}: {len(report['rows'])} question/configuration rows. Reports: {args.output}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
