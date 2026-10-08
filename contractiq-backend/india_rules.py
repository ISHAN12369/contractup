"""Informational India lease checklist. National references are not state-law determinations."""

import re

from audit_schemas import IndiaContext, Location, RuleCheck
from locations import locate
from schemas import Chunk

MTA = "https://mohua.gov.in/upload/uploadfiles/files/Model-Tenancy-Act-English-02_06_2021.pdf"
TPA = "https://www.indiacode.nic.in/bitstream/123456789/14037/1/transfer_of_property_act8_%281%29.pdf"
REGISTRATION = "https://www.indiacode.nic.in/bitstream/123456789/14646/1/ra1908-16.pdf"
STAMP = "https://www.indiacode.nic.in/bitstream/123456789/13205/1/the_indian_stamp_act%2C_1899.pdf"
CONTRACT = "https://www.indiacode.nic.in/handle/123456789/2187?col=123456789%2F1362"
ADOPTION = "https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=1779681&lang=2&reg=48"

RULES = {
    "applicability": ("Rent law applicability", r"rent control|tenancy act|governing law|jurisdiction", "MoHUA: Model Tenancy Act adoption", ADOPTION, "State/UT adoption", "Confirm the state/UT, premises, tenancy date, exclusions and enacted local law. The Model Tenancy Act is a model for state adoption, not a nationwide replacement for existing rent-control laws."),
    "deposit": ("Security deposit", r"security deposit|refundable deposit|advance rent", "Model Tenancy Act 2021", MTA, "Section 11 (model provision)", "The model reference uses two months' rent for residential and six for non-residential premises. Verify the enacted state law and applicability before using this benchmark."),
    "lock_in": ("Lock-in and exit payment", r"lock[- ]?in|early termination|liquidated damages|penalty", "Indian Contract Act 1872", CONTRACT, "Sections 73–74", "Review the lock-in duration, exit rights and any stipulated payment with counsel. A stated payment is not itself a determination of recoverable compensation."),
    "notice": ("Notice period", r"notice|terminat", "Transfer of Property Act 1882", TPA, "Sections 106–107", "Check contractual notice, purpose of the lease and applicable local law. Section 106 supplies defaults subject to contract, local law or usage; a single notice period is not universally applicable."),
    "stamp": ("Stamp duty", r"stamp duty|stamp paper|stamping|e-stamp", "Indian Stamp Act 1899", STAMP, "Sections 3, 35; Schedule I, Article 35; state amendments", "Confirm the relevant state's stamp legislation, instrument type, term and consideration. This check does not calculate duty or confirm payment."),
    "registration": ("Registration", r"register|registration|registrar", "Registration Act 1908", REGISTRATION, "Section 17(1)(d), subject to applicable amendments", "Review registration requirements for a lease from year to year, exceeding one year, or reserving yearly rent, and applicable exemptions/amendments. Mentioning registration does not prove it occurred."),
    "escalation": ("Rent escalation", r"escalat|rent increase|revision of rent|increase.{0,25}rent", "Model Tenancy Act 2021", MTA, "Section 9 (model provision)", "Check the agreed revision rate, dates and notice alongside applicable state law. The model provision refers to agreed terms; it does not establish a universal annual percentage cap."),
}


def check_rules(chunks: list[Chunk], context: IndiaContext) -> list[RuleCheck]:
    if not context.enabled:
        return []
    checks: list[RuleCheck] = []
    for key in dict.fromkeys(context.enabled_rules):
        if key not in RULES:
            raise ValueError("Unknown India checklist rule")
        title, pattern, source, url, section, guidance = RULES[key]
        evidence: list[Location] = []
        for chunk in chunks:
            match = re.search(pattern, chunk.text, re.I)
            if match:
                location = locate(chunk, match.group())
                if location:
                    evidence.append(location)
        status = "review" if evidence else "not_found"
        detail = guidance + (" Keyword evidence found; inspect the full provision." if evidence else " No checklist keyword was located; this does not prove absence.")
        if key == "applicability" or not context.state:
            status = "context_needed"
            detail += " State context: " + (context.state or "not supplied") + ". Applicability is not determined by this tool."
        if key == "deposit":
            if not context.model_act_applicable or context.premises == "unknown" or context.monthly_rent is None or context.deposit is None:
                status = "context_needed"
                detail += " Comparison needs rent, deposit, premises type and an explicit applicability assumption."
            else:
                months = 2 if context.premises == "residential" else 6
                exceeded = context.deposit > months * context.monthly_rent
                status = "attention" if exceeded else "within_reference"
                detail += f" User-entered figures {'exceed' if exceeded else 'are within'} the {months}-month model benchmark. Figures and applicability are unverified; this is not a legal compliance result."
        checks.append(RuleCheck(
            id=key, title=title, status=status, detail=detail,  # type: ignore[arg-type]
            source_title=source, source_url=url, section=section, evidence=evidence[:6],
        ))
    return checks
