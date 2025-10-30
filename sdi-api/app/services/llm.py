import os, json, re
from typing import List, Dict, Any, Optional
from anthropic import Anthropic
ANTHROPIC_API_KEY = ""
claude = Anthropic(api_key=ANTHROPIC_API_KEY)

ALLOWED_CATEGORIES = [
    "cleaning","rekey","landscaping","utilities","unpaid_rent","lease_break",
    "prorated_rent","non_refundable_fee","pet_damage","normal_wear","unknown"
]

SYSTEM_MSG = (
    "You are a strict SDI move-out document parser. "
    "Extract only what the text states. Return VALID JSON. "
    "Do NOT invent values. No commentary. No totals."
)

BASE_PROMPT = """You will receive one or more documents' text. Do two things:

1) Extract line-item charges per file (UNCHANGED from earlier).
2) Extract top-level metadata if present anywhere across the documents:
   - deposit_amount: number | null
   - move_out_date: 'YYYY-MM-DD' | null
   - jurisdiction: US state/territory string (e.g., 'SC', 'South Carolina') | null

Rules for metadata:
- deposit_amount: 
  - If you see an explicit security deposit amount (e.g., “Security Deposit: $1,500”), use that amount (numbers only).
  - If the text explicitly says the deposit equals one month’s rent (e.g., “equal to one month rent”), set deposit_amount to the literal phrase "ONE_MONTH_RENT" (do not compute the value).
  - If you only see SDI premiums (e.g., $38 monthly), DO NOT infer the deposit → return null.
  - Any line that references a Security Deposit (e.g., “Security Deposit: $2,550”, “Sec Dep $1,200”, “SD $900” where SD clearly means Security Deposit) must be excluded from files[].charges and used only for metadata.deposit_amount.
  - If you only see 'Deposit Applied: $X' (applied to charges) but no explicit deposit amount, return that $X as deposit_amount.

- move_out_date:
  - Use the explicit move-out/move out/move-out date if present. Return in YYYY-MM-DD format if unambiguous; else null.

- jurisdiction:
  - Prefer explicit jurisdiction in the docs (e.g., 'Governing Law: South Carolina', 'Jurisdiction: SC'). 
  - If multiple are mentioned, choose the one tied to the lease or governing law.

Return EXACTLY this JSON shape:

{{
  "files": [
    {{
      "filename": string,
      "charges": [
        {{
          "description": string,
          "category": one_of({allowed}),
          "amount": number,
          "status": "unpaid",
          "wear": "beyond" | "normal" | null
        }},
        ...
      ]
    }},
    ...
  ],
  "metadata": {{
    "deposit_amount": number | "ONE_MONTH_RENT" | null,
    "move_out_date": string | null,
    "jurisdiction": string | null
  }}
}}

Charge extraction rules (unchanged):
- Parse line-items only. If multiple amounts exist in one line, split into multiple items.
- Set status="unpaid" always.
- Categorization:
  - rekey/lock/key → rekey
  - clean/trash/carpet clean/deep clean → cleaning
  - lawn/yard/mulch/sod → landscaping
  - water/electric/gas/utility → utilities
  - rent arrears → unpaid_rent
  - lease break/relist → lease_break
  - non-refundable/admin fee → non_refundable_fee
  - pet → pet_damage
  - 'normal wear' → wear="normal"
  - stain/hole/broken/damage → wear="beyond"

DOCUMENTS:
"""

def _safe_json_block(s: str) -> Any:
    s = s.strip()
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1 or j <= i:
        raise ValueError("No JSON object found.")
    return json.loads(s[i:j+1])

def extract_charges_with_claude(docs: List[Dict[str, str]]) -> Dict[str, Any]:
    if not claude:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    if not docs:
        return {"charges": [], "metadata": {"deposit_amount": None, "move_out_date": None, "jurisdiction": None}}

    # Concatenate docs for the prompt
    doc_blob = "\n\n".join(
        f"--- {d['filename']} ---\n{(d.get('text') or '').strip()[:7000]}"
        for d in docs
    )
    prompt = BASE_PROMPT.format(allowed=ALLOWED_CATEGORIES) + doc_blob

    resp = claude.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
        max_tokens=5000,
        temperature=0.1,
        system=SYSTEM_MSG,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = resp.content[0].text if resp.content else "{}"
    data = _safe_json_block(raw)

    # Normalize
    files = data.get("files", [])
    metadata = data.get("metadata", {}) or {}

    normalized_charges: List[Dict[str, Any]] = []
    for f in files:
        fname = str(f.get("filename", "unknown.pdf"))
        for item in f.get("charges", []):
            cat = (item.get("category") or "unknown").lower()
            wear = item.get("wear")
            normalized_charges.append({
                "description": str(item.get("description", ""))[:256],
                "category": cat if cat in ALLOWED_CATEGORIES else "unknown",
                "amount": float(item.get("amount") or 0),
                "status": "unpaid",
                "wear": wear if wear in ("normal", "beyond") else None,
                "source": fname
            })

    # metadata normalization
    dep_amt = metadata.get("deposit_amount", None)
    if isinstance(dep_amt, str) and dep_amt != "ONE_MONTH_RENT":
        # try to coerce plain numeric strings
        try:
            dep_amt = float(re.sub(r"[^\d.]", "", dep_amt))
        except Exception:
            dep_amt = None
    elif isinstance(dep_amt, (int, float)):
        dep_amt = float(dep_amt)
    elif dep_amt not in (None, "ONE_MONTH_RENT"):
        dep_amt = None

    move_out = metadata.get("move_out_date") or None
    jur = metadata.get("jurisdiction") or None

    return {
        "llm_used": "claude",
        "charges": normalized_charges,
        "metadata": {
            "deposit_amount": dep_amt,                  
            "move_out_date": move_out,                  
            "jurisdiction": jur                         
        }
    }
