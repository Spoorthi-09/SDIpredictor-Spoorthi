from fastapi import APIRouter
from typing import List, Dict, Any, Optional

from app.schemas import AdjudicateRequest
from app.utils.rules import validate_gate, apply_policy_rules, finalize_payout

router = APIRouter()

# --- Minimal readiness check for final payout ---
REQUIRED_FOR_FINAL = ["deposit_amount", "move_out_date", "jurisdiction"]

def payout_readiness(payload: AdjudicateRequest) -> Dict[str, Any]:
    # Fallback: jurisdiction := payload.jurisdiction or payload.lease_state
    effective_jurisdiction = getattr(payload, "jurisdiction", None) or getattr(payload, "lease_state", None)
    deposit_amount = getattr(payload, "deposit_amount", None)
    move_out_date  = getattr(payload, "move_out_date", None)

    missing = []
    if not deposit_amount:  missing.append("deposit_amount")
    if not move_out_date:   missing.append("move_out_date")
    if not effective_jurisdiction: missing.append("jurisdiction")

    return {
        "ready": len(missing) == 0,
        "missing": missing,
        "effective_jurisdiction": effective_jurisdiction
    }

@router.post("/adjudicate")
def adjudicate(payload: AdjudicateRequest):
    ok, validation = validate_gate(
        payload.documents_present.dict() if hasattr(payload.documents_present, "dict") else dict(payload.documents_present),
        payload.ledger_checks.dict() if hasattr(payload.ledger_checks, "dict") else dict(payload.ledger_checks)
    )
    submitted_docs = [
        k for k, v in (
            payload.documents_present.dict() if hasattr(payload.documents_present, "dict") else dict(payload.documents_present)
        ).items() if v
    ]

    if not ok:
        return {
            "validation": validation,
            "final_payout_available": False,
            "missing_fields": [],
            "output_template": {
                "Tenant Name": getattr(payload, "tenant_name", ""),
                "Assessment Status": "Declined",
                "Property Address": getattr(payload, "property_address", ""),
                "Monthly Rent": getattr(payload, "monthly_rent", 0.0),
                "Submitted Documents": submitted_docs,
                "Approved Charges": [],
                "Excluded Charges": [],
                "Total Approved Charges": 0.0,
                "Final Payout Based on Coverage": 0.0
            },
            "summary_of_decision": "Required gate(s) failed. Declined per policy."
        }

    # Apply policy rules
    charges_list = [c.dict() if hasattr(c, "dict") else dict(c) for c in getattr(payload, "charges", [])]
    approved, excluded, total = apply_policy_rules(charges_list, getattr(payload, "monthly_rent", 0.0))

    readiness = payout_readiness(payload)

    if not readiness["ready"]:
        return {
            "validation": validation,
            "final_payout_available": False,
            "missing_fields": readiness["missing"],
            "output_template": {
                "Tenant Name": getattr(payload, "tenant_name", ""),
                "Assessment Status": "Approved",
                "Property Address": getattr(payload, "property_address", ""),
                "Monthly Rent": getattr(payload, "monthly_rent", 0.0),
                "Submitted Documents": submitted_docs,
                "Approved Charges": [{"item": a[0], "amount": a[1], "reason": a[2]} for a in approved],
                "Excluded Charges": [{"item": e[0], "amount": e[1], "reason": e[2]} for e in excluded],
                "Total Approved Charges": total,
                "Final Payout Based on Coverage": 0.0
            },
            "summary_of_decision": (
                "Final payout not available: missing required fields — "
                + ", ".join(readiness["missing"])
                + ". Only estimated payout may be shown."
            )
        }

    final_payout = finalize_payout(total, getattr(payload, "max_benefit", 0.0))

    return {
        "validation": validation,
        "final_payout_available": True,
        "missing_fields": [],
        "output_template": {
            "Tenant Name": getattr(payload, "tenant_name", ""),
            "Assessment Status": "Approved",
            "Property Address": getattr(payload, "property_address", ""),
            "Monthly Rent": getattr(payload, "monthly_rent", 0.0),
            "Submitted Documents": submitted_docs,
            "Approved Charges": [{"item": a[0], "amount": a[1], "reason": a[2]} for a in approved],
            "Excluded Charges": [{"item": e[0], "amount": e[1], "reason": e[2]} for e in excluded],
            "Total Approved Charges": total,
            "Final Payout Based on Coverage": final_payout
        },
        "jurisdiction_used": readiness["effective_jurisdiction"],
        "summary_of_decision": "Policy rules applied with caps; payout limited by Max Benefit."
    }
