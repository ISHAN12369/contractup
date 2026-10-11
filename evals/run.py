"""Run production retrieval against fixed labels; provider evaluation is opt-in."""
import argparse
import hashlib
import importlib.metadata
import os
import platform
import subprocess
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chunking import split_pages
from config import Settings
from dotenv import load_dotenv
from llm import GroqLLM, StructuredLLM
from rag_pipeline import RAGService
from retrieval import Hit, OnnxReranker, Reranker, Retriever
from schemas import ChatRequest
from storage import EMBEDDING_MODEL, ChromaIndex, DocumentStore, VectorIndex

from evals import BACKEND, ROOT
from evals.data import Document, Span, digest, load_cuad, load_golden
from evals.judge import RUBRIC_VERSION, judge_answer
from evals.metrics import extraction, retrieval
from evals.report import write_report

STRATEGIES = ("dense", "hybrid", "hybrid_rerank")
CHUNKERS = ("recursive", "clause")


class ObservedRetriever(Retriever):
    last_hits: list[Hit]

    def search(self, doc_id: str, question: str, strategy: str | None = None) -> list[Hit]:
        self.last_hits = super().search(doc_id, question, strategy)
        return self.last_hits


def provenance(settings: Settings) -> dict[str, Any]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, stderr=subprocess.DEVNULL))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "unavailable", None
    code = [*Path(__file__).parent.glob("*.py"), *BACKEND.glob("*.py")]
    versions = {name: importlib.metadata.version(name) for name in
                ("fastembed", "onnxruntime", "chromadb", "langchain-text-splitters", "langgraph", "presidio-analyzer", "pydantic")}
    # Bind results to source bytes even when the run precedes the phase commit.
    return {"git_commit": commit, "working_tree_dirty": dirty,
            "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sorted(code)},
            "python": platform.python_version(), "platform": platform.platform(), "packages": versions,
            "embedding_model": EMBEDDING_MODEL, "reranker_model": settings.reranker_model,
            "model_artifact_sha256": {str(p.relative_to(settings.model_cache_dir)): digest(p)
                                      for p in settings.model_cache_dir.rglob("*.onnx")},
            "retrieval_candidates": settings.retrieval_candidates, "chunk_size": 1000, "chunk_overlap": 150,
            "rrf_constant": 60, "k": 4, "relevance_coverage": 0.5, "extraction_iou": 0.5,
            "generator_model": settings.groq_model, "judge_rubric": RUBRIC_VERSION,
            "pii_mode": settings.pii_mode, "pii_model": settings.pii_model,
            "limits": {name: getattr(settings, name) for name in
                       ("max_text_chars", "max_chunks", "map_batch_chars", "analysis_timeout_seconds", "audit_max_clauses")}}


def evaluate(documents: list[Document], settings: Settings, output: Path, manifest: dict[str, Any], *,
             online: bool = False, index: VectorIndex | None = None, reranker: Reranker | None = None,
             llm: StructuredLLM | None = None, judge: StructuredLLM | None = None) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    index = index or ChromaIndex(settings.model_cache_dir)
    reranker = reranker or OnnxReranker(settings)
    owned_llm = GroqLLM(settings) if llm is None else None
    provider = llm or owned_llm
    assert provider is not None
    report: dict[str, Any] = {"schema_version": 1, "status": "running",
        "started_at_utc": datetime.now(UTC).isoformat(), "provenance": manifest,
        "provider_evaluation": "requested" if online else "not run: pass --online with a locally configured GROQ_API_KEY",
        "documents": [{"id": d.id, "source": d.source, "chars": len(d.text),
                       "sha256": hashlib.sha256(d.text.encode()).hexdigest(), "questions": len(d.questions),
                       "gold_clauses": len(d.clauses) if d.clauses is not None else None} for d in documents],
        "rows": [], "audits": []}
    try:
        with tempfile.TemporaryDirectory(prefix="contractiq-eval-", dir=output.resolve()) as workspace:
            for chunker in CHUNKERS:
                options = settings.model_copy(update={"chunking_strategy": chunker, "data_dir": Path(workspace),
                                                      "document_ttl_seconds": 86_400})
                store = DocumentStore(options, index)
                for doc in documents:
                    print(f"Evaluating {chunker}: {doc.source}/{doc.id}", flush=True)
                    doc_id = None
                    try:
                        if len(doc.text) > options.max_text_chars:
                            raise ValueError("Evaluation document exceeds deployed text limit")
                        chunks = split_pages(doc.pages, options)
                        metadata = store.create(doc.id + ".txt", len(doc.text), chunks, pages=doc.pages)
                        doc_id = str(metadata.doc_id)
                        for strategy in STRATEGIES:
                            strategy_options = options.model_copy(update={"retriever_strategy": strategy})
                            service = RAGService(strategy_options, store, provider)
                            observer = ObservedRetriever(strategy_options, store, reranker)
                            service.retriever = observer
                            for question in doc.questions:
                                row: dict[str, Any] = {"source": doc.source, "document": doc.id, "question_id": question.id,
                                    "config": f"{chunker}+{strategy}", "unanswerable": question.unanswerable,
                                    "gold_spans": [asdict(span) for span in question.spans], "retrieval": None,
                                    "generation": {"status": "not_run"}, "chunk_count": len(chunks)}
                                try:
                                    hits = observer.search(doc_id, question.question)
                                    ranked = [Span(hit.chunk.start, hit.chunk.end) for hit in hits]
                                    row.update(retrieval=retrieval(question.spans, ranked),
                                               ranked=[{"chunk_id": hit.chunk.id, "start": hit.chunk.start,
                                                        "end": hit.chunk.end, "score": hit.score} for hit in hits])
                                except Exception as exc:
                                    row["retrieval_error"] = type(exc).__name__
                                if online:
                                    try:
                                        response = service.get_answer(ChatRequest(doc_id=metadata.doc_id, question=question.question))
                                        scores = judge_answer(question.question, response.answer,
                                                              [hit.chunk.text for hit in observer.last_hits],
                                                              strategy_options, judge or provider)
                                        row["generation"] = {"status": "ok", "answer": response.answer,
                                                             "scores": scores, "sources": [s.model_dump() for s in response.sources]}
                                    except Exception as exc:
                                        row["generation"] = {"status": "failed", "error_type": type(exc).__name__}
                                report["rows"].append(row)
                            write_report(output, report)
                        if doc.clauses is not None:
                            audit_row: dict[str, Any] = {"document": doc.id, "chunker": chunker, "status": "not_run"}
                            if online:
                                try:
                                    audit = RAGService(options, store, provider).audit(doc_id)
                                    predictions = [Span(c.location.start, c.location.end, c.type.value) for c in audit.clauses]
                                    audit_row.update(status="ok", counts=extraction(doc.clauses, predictions),
                                                     predictions=[asdict(span) for span in predictions],
                                                     dropped_claims=audit.dropped_claims)
                                except Exception as exc:
                                    audit_row.update(status="failed", error_type=type(exc).__name__)
                            report["audits"].append(audit_row)
                    except Exception as exc:
                        # A failed document still contributes visible rows for every intended query.
                        existing = {(r["config"], r["question_id"]) for r in report["rows"]}
                        for strategy in STRATEGIES:
                            for question in doc.questions:
                                config = f"{chunker}+{strategy}"
                                if (config, question.id) not in existing:
                                    report["rows"].append({"source": doc.source, "document": doc.id,
                                        "question_id": question.id, "config": config, "unanswerable": question.unanswerable,
                                        "retrieval": None, "retrieval_error": type(exc).__name__,
                                        "generation": {"status": "failed" if online else "not_run"}})
                        if doc.clauses is not None and not any(a["document"] == doc.id and a["chunker"] == chunker for a in report["audits"]):
                            report["audits"].append({"document": doc.id, "chunker": chunker, "status": "failed", "error_type": type(exc).__name__})
                    finally:
                        if doc_id:
                            store.delete(doc_id)
                    write_report(output, report)
        failures = any("retrieval_error" in r or r["generation"]["status"] == "failed" for r in report["rows"])
        failures |= any(a["status"] == "failed" for a in report["audits"])
        report["status"] = "completed_with_errors" if failures else "completed"
        report["completed_at_utc"] = datetime.now(UTC).isoformat()
        write_report(output, report)
        return report
    finally:
        if owned_llm:
            owned_llm.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cuad", type=Path, default=Path("evals/.cache/cuad-data.zip"))
    parser.add_argument("--golden", type=Path, default=Path("evals/fixtures/golden.json"))
    parser.add_argument("--private", type=Path, help="Optional local-only golden-format cases; use an ignored output directory")
    parser.add_argument("--cuad-limit", type=int, default=10, help="0 selects all length-eligible test documents")
    parser.add_argument("--questions-per-doc", type=int, default=0, help="0 selects every answerable CUAD category")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("evals/runs/local"))
    parser.add_argument("--online", action="store_true", help="Send PII-redacted evidence to configured Groq generator/judge; may incur cost")
    args = parser.parse_args()
    if args.cuad_limit < 0 or args.questions_per_doc < 0:
        parser.error("Sampling limits must be nonnegative")
    load_dotenv(BACKEND / ".env")
    settings = Settings.from_env().model_copy(update={"model_cache_dir": BACKEND / "model-cache"})
    if args.online and not settings.groq_api_key:
        parser.error("--online requires GROQ_API_KEY configured locally; offline retrieval remains available")
    documents, dataset = load_cuad(args.cuad, args.cuad_limit, args.questions_per_doc, args.seed, settings.max_text_chars)
    documents += load_golden(args.golden)
    if args.private:
        if args.online:
            parser.error("Private cases are local retrieval only; omit --online")
        if not args.output.resolve().is_relative_to((ROOT / "evals/runs").resolve()):
            parser.error("Private results must stay under ignored evals/runs/")
        documents += load_golden(args.private, source="private")
    identifiers = [d.id for d in documents]
    if len(identifiers) != len(set(identifiers)):
        parser.error("Document IDs must be unique across datasets")
    manifest = provenance(settings)
    manifest.update(cuad=dataset, golden_sha256=digest(args.golden), command_arguments=vars(args).copy())
    manifest["command_arguments"] = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    judge_model = os.getenv("EVAL_JUDGE_MODEL", settings.groq_model)
    manifest["judge_model"] = judge_model
    manifest["judge_same_as_generator"] = judge_model == settings.groq_model
    started = time.monotonic()
    judge = GroqLLM(settings.model_copy(update={"groq_model": judge_model})) if args.online else None
    try:
        result = evaluate(documents, settings, args.output, manifest, online=args.online, judge=judge)
    finally:
        if judge:
            judge.close()
    print(f"{result['status']}: {len(result['rows'])} question/configuration rows in {time.monotonic() - started:.1f}s. Reports: {args.output}")
    return 1 if result["status"] != "completed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
