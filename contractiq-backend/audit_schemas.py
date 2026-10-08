"""CUAD labels and typed audit/comparison contracts (not legal conclusions)."""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from schemas import DISCLAIMER, DocumentRequest, StrictModel


# CUAD v1 labels, The Atticus Project (CC BY 4.0); see docs/phase-1.md.
class ClauseType(StrEnum):
    DOCUMENT_NAME = "Document Name"
    PARTIES = "Parties"
    AGREEMENT_DATE = "Agreement Date"
    EFFECTIVE_DATE = "Effective Date"
    EXPIRATION_DATE = "Expiration Date"
    RENEWAL_TERM = "Renewal Term"
    NOTICE_PERIOD = "Notice Period To Terminate Renewal"
    GOVERNING_LAW = "Governing Law"
    MOST_FAVORED_NATION = "Most Favored Nation"
    NON_COMPETE = "Non-Compete"
    EXCLUSIVITY = "Exclusivity"
    NO_SOLICIT_CUSTOMERS = "No-Solicit Of Customers"
    COMPETITIVE_EXCEPTION = "Competitive Restriction Exception"
    NO_SOLICIT_EMPLOYEES = "No-Solicit Of Employees"
    NON_DISPARAGEMENT = "Non-Disparagement"
    TERMINATION = "Termination For Convenience"
    ROFR = "Rofr/Rofo/Rofn"
    CHANGE_OF_CONTROL = "Change Of Control"
    ANTI_ASSIGNMENT = "Anti-Assignment"
    REVENUE = "Revenue/Profit Sharing"
    PRICE = "Price Restrictions"
    MINIMUM_COMMITMENT = "Minimum Commitment"
    VOLUME = "Volume Restriction"
    IP_ASSIGNMENT = "Ip Ownership Assignment"
    JOINT_IP = "Joint Ip Ownership"
    LICENSE = "License Grant"
    NON_TRANSFERABLE = "Non-Transferable License"
    AFFILIATE_LICENSOR = "Affiliate License-Licensor"
    AFFILIATE_LICENSEE = "Affiliate License-Licensee"
    UNLIMITED_LICENSE = "Unlimited/All-You-Can-Eat-License"
    PERPETUAL_LICENSE = "Irrevocable Or Perpetual License"
    SOURCE_ESCROW = "Source Code Escrow"
    POST_TERMINATION = "Post-Termination Services"
    AUDIT = "Audit Rights"
    UNCAPPED_LIABILITY = "Uncapped Liability"
    CAPPED_LIABILITY = "Cap On Liability"
    LIQUIDATED_DAMAGES = "Liquidated Damages"
    WARRANTY = "Warranty Duration"
    INSURANCE = "Insurance"
    NOT_TO_SUE = "Covenant Not To Sue"
    THIRD_PARTY = "Third Party Beneficiary"


class Location(StrictModel):
    chunk_id: str
    page: int | None
    section_id: str
    start: int
    end: int
    page_start: int
    page_end: int
    ocr: bool


class CandidateClause(StrictModel):
    type: ClauseType
    quoted_text: str = Field(min_length=1, max_length=1000)
    chunk_id: str
    party: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0, le=1)


class ClauseBatch(StrictModel):
    clauses: list[CandidateClause] = Field(max_length=60)


class ContractClassification(StrictModel):
    contract_type: Literal["lease", "employment", "service", "license", "other"]
    evidence: str = Field(max_length=1000)
    chunk_id: str


class Risk(StrictModel):
    level: Literal["low", "medium", "high"]
    score: int = Field(ge=0, le=100)
    why: str
    rubric_id: str


class Redline(StrictModel):
    original: str
    suggested: str
    rationale: str
    disclaimer: str = DISCLAIMER


class AuditedClause(CandidateClause):
    id: str
    location: Location
    risk: Risk
    redline: Redline | None


class IndiaContext(StrictModel):
    enabled: bool = False
    state: str = Field(default="", max_length=80)
    premises: Literal["residential", "commercial", "unknown"] = "unknown"
    # User-provided context, never an automatic determination of applicable law.
    model_act_applicable: bool = False
    monthly_rent: float | None = Field(default=None, gt=0, le=1e9)
    deposit: float | None = Field(default=None, ge=0, le=1e10)
    enabled_rules: list[Literal["applicability", "deposit", "lock_in", "notice", "stamp", "registration", "escalation"]] = Field(default=[
        "applicability", "deposit", "lock_in", "notice", "stamp", "registration", "escalation",
    ], max_length=7)


class AuditRequest(DocumentRequest):
    india: IndiaContext = Field(default_factory=IndiaContext)


class RuleCheck(StrictModel):
    id: str
    title: str
    status: Literal["review", "not_found", "context_needed", "attention", "within_reference"]
    detail: str
    source_title: str
    source_url: str
    section: str
    evidence: list[Location]
    disclaimer: str = DISCLAIMER


class AuditResponse(StrictModel):
    doc_id: UUID
    contract_type: str
    checklist: list[str]
    clauses: list[AuditedClause]
    overall_risk: Risk | None
    summary: str
    dropped_claims: int
    analyzed_chunks: int
    total_chunks: int
    rule_checks: list[RuleCheck]
    warnings: list[str]
    steps: list[str]
    disclaimer: str = DISCLAIMER


class CompareRequest(StrictModel):
    before_id: UUID
    after_id: UUID


class ClauseChange(StrictModel):
    kind: Literal["added", "removed", "changed"]
    before: AuditedClause | None
    after: AuditedClause | None
    similarity: float | None
    risk_delta: int
    explanation: str


class CompareResponse(StrictModel):
    before_id: UUID
    after_id: UUID
    changes: list[ClauseChange]
    unchanged: int
    overall_risk_delta: int | None
    warnings: list[str]
    disclaimer: str = DISCLAIMER
