"""Paginated audit PDF from a server-owned snapshot; never interpret document markup."""
from datetime import UTC, datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from product_schemas import SavedAudit

FONT = "ContractIQVera"
if FONT not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont(FONT, str(Path(reportlab.__file__).parent / "fonts/Vera.ttf")))


def safe_text(text: str) -> str:
    supported = pdfmetrics.getFont(FONT).face.charToGlyph
    text = "".join(char if ord(char) in supported or char == "\n" else f"[U+{ord(char):04X}]" for char in text)
    return escape(text).replace("\n", "<br/>")


def render_report(saved: SavedAudit) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=48, leftMargin=48,
        topMargin=58, bottomMargin=54, title="ContractIQ audit report", author="ContractIQ")
    body = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=14, spaceAfter=9,
                          textColor=colors.HexColor("#222222"), splitLongWords=True)
    heading = ParagraphStyle("heading", parent=body, fontSize=15, leading=20, spaceBefore=15,
                             spaceAfter=10, keepWithNext=True, textColor=colors.HexColor("#a33324"))
    title = ParagraphStyle("title", parent=heading, fontSize=28, leading=34)
    story: list[Any] = []

    def paragraph(value: str, style: ParagraphStyle = body) -> None:
        story.append(Paragraph(safe_text(value), style))

    audit = saved.audit
    paragraph("CONTRACTIQ", title)
    paragraph("Contract audit / review priorities", heading)
    paragraph(saved.filename)
    paragraph(f"Report generated: {datetime.fromtimestamp(saved.generated_at, UTC):%Y-%m-%d %H:%M UTC}")
    paragraph(audit.disclaimer)
    paragraph(f"Contract type: {audit.contract_type} | Coverage: {audit.analyzed_chunks}/{audit.total_chunks} chunks | Unsupported claims dropped: {audit.dropped_claims}")
    paragraph(audit.summary)
    paragraph("Review-priority overview", heading)
    for level in ("high", "medium", "low"):
        paragraph(f"{level.upper()}: {sum(clause.risk.level == level for clause in audit.clauses)} extracted clauses")
    paragraph(f"Overall priority: {audit.overall_risk.score}/100 ({audit.overall_risk.level}). {audit.overall_risk.why}" if audit.overall_risk else "Overall priority: not assessed. Missing findings do not establish safety.")
    paragraph("Scores use a heuristic review rubric, not a probability of harm or a legal verdict. Model confidence is uncalibrated. Unextracted clauses are not scored.")
    paragraph("Clause findings", heading)
    if not audit.clauses:
        paragraph("No source-located clauses were returned. This does not establish absence or low risk.")
    for index, clause in enumerate(audit.clauses, 1):
        paragraph(f"{index}. {clause.type} / {clause.risk.level.upper()} / {clause.risk.score}", heading)
        loc = clause.location
        paragraph(f"Source: page {loc.page or 'not paginated'}; section {loc.section_id}; characters {loc.start}-{loc.end}; chunk {loc.chunk_id}; OCR: {'yes' if loc.ocr else 'no'}")
        paragraph(f"Party: {clause.party} | Confidence: {clause.confidence:.2f} (uncalibrated)")
        paragraph(f"Quotation: {clause.quoted_text}")
        paragraph(f"Review reason: {clause.risk.why} | Rubric: {clause.risk.rubric_id}")
        if clause.redline:
            paragraph(f"Negotiation draft: {clause.redline.suggested}")
            paragraph(f"Rationale: {clause.redline.rationale}")
            paragraph(clause.redline.disclaimer)
    if audit.rule_checks:
        paragraph("Informational India checklist", heading)
        for check in audit.rule_checks:
            paragraph(f"{check.title}: {check.status.replace('_', ' ')}", heading)
            paragraph(check.detail)
            paragraph(f"Reference: {check.source_title}, {check.section}\n{check.source_url}")
            paragraph(check.disclaimer)
    paragraph("Coverage and limitations", heading)
    for warning in audit.warnings:
        paragraph(warning)
    paragraph("Checklist: " + ", ".join(audit.checklist))
    paragraph("This downloaded copy does not expire or update when a source or share link expires. Keep it private. Characters unsupported by the embedded font are shown as [U+XXXX] escapes; inspect the original source for exact typography.")
    story.append(Spacer(1, 10))
    paragraph(audit.disclaimer)

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(48, 30, "Informational only, not legal advice.")
        canvas.drawRightString(A4[0] - 48, 30, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
