from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List
import pathlib, uuid, re
import pdfplumber

from app.services.llm import extract_charges_with_claude  # keep your service

router = APIRouter()

UPLOAD_DIR = pathlib.Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# --- Deposit helpers ---
_DEPOSIT_PHRASES = (
    "security deposit", "sec dep", "sec. dep", "sec deposit", "sec. deposit",
    "deposit amount", "deposit:", "deposit -", "deposit due"
)

_ONE_MONTH_RENT_PHRASES = (
    "one month rent", "one month's rent", "1 month rent", "one (1) month rent"
)

# ex: "Deposit Applied: $500" or "Applied Deposit $500"
_DEPOSIT_APPLIED_RE = re.compile(
    r'(deposit\s+applied|applied\s+deposit)\s*[:\-]?\s*\$?\s*([\d,]+(?:\.\d{2})?)',
    re.IGNORECASE
)

def _is_deposit_line(text: str) -> bool:
    s = text.lower()
    return any(p in s for p in _DEPOSIT_PHRASES) or bool(_DEPOSIT_APPLIED_RE.search(text))

def _mentions_one_month_rent(text: str) -> bool:
    s = text.lower()
    return any(p in s for p in _ONE_MONTH_RENT_PHRASES)


# --- Money parsing: only treat as money if it has a $ OR a decimal cents part ---
_money_token = re.compile(r'\d{1,3}(?:,\d{3})*(?:\.\d{2})?')

def _iter_amounts_money_only(line: str):
    s = line
    for m in _money_token.finditer(s):
        token = m.group()
        has_decimal = '.' in token
        has_dollar = '$' in s[max(0, m.start()-2): m.start()+1]  # a couple chars before
        if not (has_decimal or has_dollar):
            continue
        try:
            val = float(token.replace(',', ''))
        except ValueError:
            continue
        if val <= 0:
            continue
        yield val

def _guess_category(line: str) -> str:
    s = line.lower()
    if any(k in s for k in ["rekey","lock","key"]): return "rekey"
    if any(k in s for k in ["carpet","clean","trash","wipe","deep clean"]): return "cleaning"
    if any(k in s for k in ["lawn","yard","mulch","sod","landscap"]): return "landscaping"
    if any(k in s for k in ["utility","water","electric","gas","power"]): return "utilities"
    if "rent" in s: return "unpaid_rent"
    if "lease break" in s or "relist" in s: return "lease_break"

    # Common fee lines → non_refundable_fee (policy excludes them anyway)
    if any(k in s for k in [
        "late fee", "convenience fee", "administrative fee", "admin fee",
        "coordination fee", "maintenance coordination fee"
    ]):
        return "non_refundable_fee"
    if "animal fee" in s or "pet fee" in s:
        return "non_refundable_fee"

    if "pet" in s: return "pet_damage"
    if "wear" in s and "normal" in s: return "normal_wear"
    return "unknown"

def _read_pdf_text(path: pathlib.Path) -> str:
    text = ""
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
    except Exception:
        # keep going; empty string means OCR/parse failed
        pass
    return text

@router.post("/extract-charges")
async def extract_charges(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded. Send one or more PDFs as 'files'.")

    # 1) Save uploads
    saved = []
    for uf in files:
        ext = pathlib.Path(uf.filename).suffix or ".pdf"
        target = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
        content = await uf.read()
        with target.open("wb") as out:
            out.write(content)
        saved.append({"orig": uf.filename, "path": target})

    # 2) Extract raw text from all PDFs
    docs = []
    for item in saved:
        text = _read_pdf_text(item["path"])
        docs.append({"filename": item["orig"], "text": text})

    # 3) Call LLM extractor (expects list[ {filename, text} ])
    llm_used = "claude"
    try:
        # NOTE: service is synchronous; do NOT await
        llm_out = extract_charges_with_claude(docs)  # returns dict with "charges"
    except Exception as e:
        llm_out = {"charges": [], "error": f"LLM extraction failed: {e.__class__.__name__}"}
        llm_used = None

   # 4) Naive fallback parse (with stricter money detection)
        fallback_charges = []
        fallback_meta = {"deposit_amount": None}

        for d in docs:
            for raw_line in d["text"].splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                lw = line.lower()

                # --- Detect 'Deposit' lines and store deposit amount instead of treating as charge ---
                if "deposit" in lw:
                    # explicit numeric amount (e.g., Security Deposit: $1,500)
                    amts = list(_iter_amounts_money_only(line))
                    if amts and fallback_meta["deposit_amount"] is None:
                        fallback_meta["deposit_amount"] = amts[0]
                    # or phrasing like "equal to one month rent"
                    elif "one month" in lw and "rent" in lw:
                        fallback_meta["deposit_amount"] = "ONE_MONTH_RENT"
                    # skip deposit lines from charge list
                    continue

                # --- normal charge extraction ---
                amts = list(_iter_amounts_money_only(line))
                if not amts:
                    continue
                cat = _guess_category(line)
                wear = "normal" if ("normal wear" in lw) else (
                    "beyond" if any(k in lw for k in ["stain", "hole", "broken", "damage"]) else None)

                for a in amts:
                    fallback_charges.append({
                        "category": cat,
                        "description": line[:140],
                        "amount": a,
                        "status": "unpaid",
                        "wear": wear,
                        "source": d["filename"]
                    })

        # 5) Prefer LLM charges; include fallback for transparency
        response = {
            "llm_used": llm_used or "none",
            "docs": [d["filename"] for d in docs],
            "charges": llm_out.get("charges") or [],
            "charges_fallback": fallback_charges[:200],
            "metadata": llm_out.get("metadata", {
                "deposit_amount": None,
                "move_out_date": None,
                "jurisdiction": None
            })
        }

        # --- If LLM didn’t find a deposit, fill from fallback ---
        if not response["metadata"].get("deposit_amount") and fallback_meta["deposit_amount"]:
            response["metadata"]["deposit_amount"] = fallback_meta["deposit_amount"]

        if "error" in llm_out:
            response["llm_error"] = llm_out["error"]

        return response

