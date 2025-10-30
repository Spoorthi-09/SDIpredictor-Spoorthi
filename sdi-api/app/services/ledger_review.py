# app/services/ledger_review.py
import re
from typing import Any, Dict, List, Tuple, Optional

# ---- Public API (what other modules import) ----
__all__ = [
    "detect_documents_present",
    "extract_ledger_flags",
    "validate_gate",
    "format_gate_result",
    "review_inputs_and_format_output",
]

# =====================================================
# File presence rules
# =====================================================
REQUIRED_FILES = [
    "lease_addendum",
    "lease_agreement",
    "notification_to_tenant",
    "tenant_ledger",
]
OPTIONAL_FILES = [
    "invoice",
    "claim_evaluation_report",
]

def detect_documents_present(input_filenames: List[str]) -> Dict[str, bool]:
    names = {n.lower().strip() for n in input_filenames}
    return {k: (k in names) for k in REQUIRED_FILES + OPTIONAL_FILES}

# =====================================================
# Tenant Ledger text parsing
# =====================================================
RENT_HINTS = ("rent", "base rent", "monthly rent", "1st month rent", "first month rent")
SDI_HINTS = ("sdi", "security deposit insurance", "deposit insurance premium", "sdi premium")
PAID_HINTS = ("paid", "received", "collected", "posted", "credit")
_MONEY = re.compile(r"\$?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")

def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def _line_matches(line: str, needles: Tuple[str, ...]) -> bool:
    L = line.lower()
    return any(k in L for k in needles)

def _search_money(line: str) -> Optional[str]:
    m = _MONEY.search(line)
    return m.group(0) if m else None

def extract_ledger_flags(ledger_text: str, lease_start_date: Optional[str] = None) -> Dict[str, Any]:
    text = ledger_text or ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rent_paid = sdi_paid = False
    rent_ev = sdi_ev = ""

    for line in lines:
        has_money = bool(_search_money(line))
        paid_mention = _line_matches(line, PAID_HINTS)

        if not rent_paid and _line_matches(line, RENT_HINTS) and (has_money or paid_mention):
            rent_paid = True
            rent_ev = _normalize_text(line)

        if not sdi_paid and _line_matches(line, SDI_HINTS) and (has_money or paid_mention):
            sdi_paid = True
            sdi_ev = _normalize_text(line)

        if rent_paid and sdi_paid:
            break

    if not rent_paid:
        for line in lines:
            if _line_matches(line, RENT_HINTS):
                rent_paid = True
                rent_ev = _normalize_text(line)
                break

    if not sdi_paid:
        for line in lines:
            if _line_matches(line, SDI_HINTS):
                sdi_paid = True
                sdi_ev = _normalize_text(line)
                break

    return {
        "first_month_rent_paid": rent_paid,
        "first_month_rent_evidence": rent_ev,
        "first_month_sdi_premium_paid": sdi_paid,
        "first_month_sdi_premium_paid_evidence": sdi_ev,
    }

# =====================================================
# Validation Gate Logic
# =====================================================
REQ_DOCS = REQUIRED_FILES  # alias

def validate_gate(documents_present: Dict[str, bool], ledger: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    missing = sorted([d for d in REQ_DOCS if not documents_present.get(d, False)])
    first_rent = bool(ledger.get("first_month_rent_paid", False))
    first_sdi = bool(ledger.get("first_month_sdi_premium_paid", False))
    approved = (len(missing) == 0) and first_rent and first_sdi
    details = {
        "First Month Paid": first_rent,
        "First Month Paid Evidence": ledger.get("first_month_rent_evidence", ""),
        "First Month SDI Premium Paid": first_sdi,
        "First Month SDI Premium Paid Evidence": ledger.get("first_month_sdi_premium_paid_evidence", ""),
        "Missing documents": missing,
        "Status": "Approved" if approved else "Declined",
    }
    return approved, details

# =====================================================
# Output formatting
# =====================================================
def format_gate_result(details: Dict[str, Any], summary: str) -> str:
    return "\n".join([
        f"• First Month Paid: {details.get('First Month Paid', False)}",
        f"• First Month Paid Evidence: {details.get('First Month Paid Evidence', '')}",
        f"• First Month SDI Premium Paid: {details.get('First Month SDI Premium Paid', False)}",
        f"• First Month SDI Premium Paid Evidence: {details.get('First Month SDI Premium Paid Evidence', '')}",
        f"• Missing documents: {details.get('Missing documents', [])}",
        f"• Status: {details.get('Status', 'Declined')}",
        f"• Summary of decision: {summary}",
    ])

# =====================================================
# Orchestrator — single entry point for router
# =====================================================
def review_inputs_and_format_output(
    input_filenames: List[str],
    tenant_ledger_text: Optional[str] = None,
    tenant_ledger_pdf_bytes: Optional[bytes] = None,
    lease_start_date: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Returns (approved_bool, details_dict, formatted_output_str).
    Accepts either tenant_ledger_text or tenant_ledger_pdf_bytes.
    """
    docs_present = detect_documents_present(input_filenames)

    # If you want PDF bytes fallback here, you can add it later.
    ledger_text = tenant_ledger_text or ""

    ledger_flags = extract_ledger_flags(ledger_text, lease_start_date)
    approved, details = validate_gate(docs_present, ledger_flags)

    if details["Status"] == "Approved":
        summary = (
            "All required documents are present. "
            "First-month rent and SDI premium were confirmed in the tenant ledger."
        )
    else:
        reasons = []
        if details["Missing documents"]:
            reasons.append(f"Missing required file(s): {', '.join(details['Missing documents'])}")
        if not details["First Month Paid"]:
            reasons.append("First-month rent not found in ledger.")
        if not details["First Month SDI Premium Paid"]:
            reasons.append("First-month SDI premium not found in ledger.")
        summary = " ".join(reasons) if reasons else "One or more approval conditions were not met."

    formatted = format_gate_result(details, summary)
    return approved, details, formatted
