from typing import Any, Dict, List, Tuple

# ====== Documents gate ======
REQ_DOCS = ["lease_addendum", "lease_agreement", "notification_to_tenant", "tenant_ledger"]

def validate_gate(documents_present: Dict[str, bool], ledger: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    missing = sorted([d for d in REQ_DOCS if not documents_present.get(d, False)])
    first_rent = bool(ledger.get("first_month_rent_paid", False))
    first_sdi  = bool(ledger.get("first_month_sdi_premium_paid", False))
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


# ====== Policy helpers ======
DAMAGE_HINTS = (
    "stain", "hole", "burn", "tear", "ripple", "gouge", "scratch", "soiled",
    "excessive", "ruin", "broken", "damage", "beyond wear", "heavy odor", "pet urine"
)

UTIL_SYNONYMS = ("utility", "utilities", "water", "sewer", "gas", "electric", "power")
REKEY_SYNONYMS = ("rekey", "locksmith", "lock change", "change locks")
LANDSCAPE_SYNONYMS = ("landscaping", "lawn", "yard", "grounds")

def _looks_beyond_wear(desc: str) -> bool:
    d = (desc or "").lower()
    return any(k in d for k in DAMAGE_HINTS)

def _is_util(cat: str, desc: str) -> bool:
    s = f"{cat} {desc}".lower()
    return any(u in s for u in UTIL_SYNONYMS)

def _is_rekey(cat: str, desc: str) -> bool:
    s = f"{cat} {desc}".lower()
    return any(k in s for k in REKEY_SYNONYMS)

def _is_landscape(cat: str, desc: str) -> bool:
    s = f"{cat} {desc}".lower()
    return any(k in s for k in LANDSCAPE_SYNONYMS)


# ====== Core policy ======
def apply_policy_rules(
    charges: List[Dict[str, Any]],
    monthly_rent: float
) -> Tuple[List[Tuple[str, float, str]], List[Tuple[str, float, str]], float]:
    """
    Returns:
      approved: [(label, amount, reason)]
      excluded: [(label, amount, reason)]
      total_approved: float
    Expected optional fields on each charge dict:
      - category: str
      - description: str
      - amount: float
      - status: "unpaid"/"overdue"/"paid" (only unpaid/overdue considered)
      - wear: "beyond"/"normal"/"" (if "", DAMAGE_HINTS can infer)
      - accelerated_moveout: bool (for lease_break exception)
      - linked_to_occupancy: bool (for prorated_rent)
    """
    approved: List[Tuple[str, float, str]] = []
    excluded: List[Tuple[str, float, str]] = []
    landscaping_used = 0.0
    rent_used = 0.0

    def include_only_unpaid(c: Dict[str, Any]) -> bool:
        return (c.get("status", "").lower() in ("unpaid", "overdue"))

    for c in charges:
        if not include_only_unpaid(c):
            amt = float(c.get("amount", 0) or 0)
            excluded.append((c.get("description", ""), amt, "Paid/Not overdue"))
            continue

        cat  = (c.get("category") or "").lower().strip()
        desc = c.get("description", "") or ""
        amt  = float(c.get("amount", 0) or 0)
        wear = (c.get("wear") or "").lower().strip()

        # ---- Hard exclusions (policy) ----
        if cat in ("non_refundable_fee", "benefit_program", "pet_damage", "lawn_vacant"):
            excluded.append((desc, amt, "Policy exclusion"))
            continue
        if (cat in ("cleaning", "normal_wear") and wear == "normal"):
            excluded.append((desc, amt, "Normal wear and tear"))
            continue

        # ---- Normalize categories by synonyms / description ----
        if _is_rekey(cat, desc):
            cat = "rekey"
        elif _is_landscape(cat, desc):
            cat = "landscaping"
        elif _is_util(cat, desc):
            cat = "unpaid_utilities"

        # ---- Inclusions & caps ----

        # Cleaning
        if cat == "cleaning":
            if wear == "beyond" or (not wear and _looks_beyond_wear(desc)):
                approved.append((f"Cleaning – {desc}", amt, "Beyond normal wear and tear"))
            else:
                excluded.append((desc, amt, "Unspecified/normal wear"))
            continue

        # Rekey
        if cat == "rekey":
            approved.append((f"Rekey – {desc}", amt, "Move-out rekey"))
            continue

        # Landscaping (max $500 total)
        if cat == "landscaping":
            cap = max(0.0, min(amt, 500.0 - landscaping_used))
            if cap > 0:
                approved.append((f"Landscaping – {desc}", cap, "Capped at $500"))
                if amt > cap:
                    excluded.append((desc, amt - cap, "Over $500 cap"))
                landscaping_used += cap
            else:
                excluded.append((desc, amt, "Over $500 cap"))
            continue

        # Utilities
        if cat in ("utilities", "unpaid_utilities"):
            approved.append((f"Unpaid Utilities – {desc}", amt, "Covered"))
            continue

        # Unpaid Rent (≤ 1 month total)
        if cat == "unpaid_rent":
            cap = max(0.0, min(amt, monthly_rent - rent_used))
            if cap > 0:
                approved.append((f"Unpaid Rent – {desc}", cap, "Capped at one month rent"))
                if amt > cap:
                    excluded.append((desc, amt - cap, "Over one month rent"))
                rent_used += cap
            else:
                excluded.append((desc, amt, "Over one month rent"))
            continue

        # Lease Break / Relisting (≤ 1 month unless accelerated move-out exception)
        if cat in ("lease_break", "relisting_fee", "lease_break_fee"):
            accelerated = bool(c.get("accelerated_moveout", False))
            if accelerated:
                approved.append((f"Lease Break Fee (Accelerated) – {desc}", amt, "Exception: accelerated move-out"))
            else:
                cap = min(amt, monthly_rent)
                approved.append((f"Lease Break Fee – {desc}", cap, "Capped at one month rent"))
                if amt > cap:
                    excluded.append((desc, amt - cap, "Over one month rent"))
            continue

        # Prorated Rent (only if clearly linked)
        if cat == "prorated_rent":
            linked = bool(c.get("linked_to_occupancy", False))
            if linked:
                approved.append((f"Prorated Rent – {desc}", amt, "Linked to occupancy/lease obligations"))
            else:
                excluded.append((desc, amt, "Exclude unless clearly linked"))
            continue

        # Unknown category
        excluded.append((desc, amt, "Unknown category (exclude)"))

    total_approved = round(sum(a[1] for a in approved), 2)
    return approved, excluded, total_approved


def finalize_payout(total_approved: float, max_benefit: float) -> float:
    """Final payout is the approved total clipped to the policy's Max Benefit."""
    return round(min(total_approved, float(max_benefit or 0)), 2)
