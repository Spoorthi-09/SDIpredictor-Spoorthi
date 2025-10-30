from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import date

# ===== PREDICT =====
class PredictRequest(BaseModel):
    rows: List[Dict[str, Any]] = Field(..., description="List of claim records")
    clip_to_max_benefit: bool = True

class PredictResponse(BaseModel):
    predictions: List[float]
    n_rows: int
    clipped: bool

# ===== ADJUDICATE =====
class DocumentsPresent(BaseModel):
    lease_addendum: bool
    lease_agreement: bool
    notification_to_tenant: bool
    tenant_ledger: bool
    invoice: Optional[bool] = False
    claim_evaluation_report: Optional[bool] = False

class LedgerChecks(BaseModel):
    first_month_rent_paid: bool
    first_month_rent_evidence: Optional[str] = ""
    first_month_sdi_premium_paid: bool
    first_month_sdi_premium_paid_evidence: Optional[str] = ""

class ChargeItem(BaseModel):
    # Example categories: cleaning | rekey | landscaping | utilities | unpaid_rent | lease_break | ...
    category: str
    description: Optional[str] = ""
    amount: float
    status: str                   # unpaid | overdue | paid
    wear: Optional[str] = None    # beyond | normal | None
    source: Optional[str] = None  # filename or doc id (optional provenance)

    class Config:
        extra = "allow"  # tolerate extra keys from extractors

class AdjudicateRequest(BaseModel):
    # Case metadata
    tenant_name: Optional[str] = ""
    property_address: Optional[str] = ""

    # Financial inputs
    monthly_rent: float
    max_benefit: float

    # Final-payout readiness fields (optional; if missing, final payout is unavailable)
    deposit_amount: Optional[float] = None
    jurisdiction: Optional[str] = None           # parsed from PDFs/LLM if available
    lease_state: Optional[str] = None            # <-- fallback to use if jurisdiction missing
    move_out_date: Optional[date] = None
    deposit_received_date: Optional[date] = None # for future interest calcs
    payout_issue_date: Optional[date] = None     # for deadline/penalty logic

    # Documents & ledger checks
    documents_present: "DocumentsPresent"
    ledger_checks: "LedgerChecks"

    # Extracted charges (LLM +/or fallback)
    charges: List["ChargeItem"]

    class Config:
        extra = "allow"  # future-proofing; UI/LLM may add harmless fields
