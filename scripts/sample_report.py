"""Render an explicitly synthetic audit for PDF layout review; no provider calls."""
import sys
import time
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contractiq-backend"))

from audit import verify_candidates
from audit_schemas import AuditResponse, CandidateClause, ClauseType
from product_schemas import SavedAudit
from reports import render_report
from risk import overall
from schemas import Chunk

text = "Liability is unlimited. The tenant shall maintain insurance. Either party may terminate with 45 days written notice."
chunk = Chunk(id="c00000", text=text, page=1, section_id="Review sample", end=len(text), page_end=len(text))
candidates = [CandidateClause(type=kind, quoted_text=quote, chunk_id=chunk.id, party="Tenant", confidence=0.8)
              for kind, quote in [(ClauseType.UNCAPPED_LIABILITY, "Liability is unlimited."),
                                  (ClauseType.INSURANCE, "The tenant shall maintain insurance."),
                                  (ClauseType.TERMINATION, "Either party may terminate with 45 days written notice.")]]
clauses, dropped = verify_candidates(candidates, [chunk])
audit = AuditResponse(doc_id=UUID("39b49d8b-5442-4a5f-a070-e2f2bb6ac000"), contract_type="lease",
    checklist=["liability", "insurance", "notice"], clauses=clauses, overall_risk=overall(clauses),
    summary="Synthetic demonstration: three source-located clauses for review.", dropped_claims=dropped,
    analyzed_chunks=1, total_chunks=1, rule_checks=[], steps=["synthetic fixture", "verify"],
    warnings=["This is a synthetic layout example, not a real contract audit or model-quality result.",
              "Priority scores use deterministic heuristics. Confidence values in this sample are fixtures."])
saved = SavedAudit(audit=audit, filename="Synthetic lease - demonstration only.txt", generated_at=time.time(), expires_at=time.time() + 3600)
target = ROOT / "output/pdf/contractiq-sample.pdf"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(render_report(saved))
print(target)
