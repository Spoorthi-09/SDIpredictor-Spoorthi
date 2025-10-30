# app/routers/ledger_router.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List, Optional
import pathlib, uuid
from app.services.ledger_review import review_inputs_and_format_output
from app.routers.extract import _read_pdf_text  

router = APIRouter(prefix="/ledger", tags=["Ledger Review"])

UPLOAD_DIR = pathlib.Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

@router.post("/review")
async def review_ledger_endpoint(
    files: List[UploadFile] = File(...),
    lease_start_date: Optional[str] = Form(None)
):
    """
    Validate tenant ledger and required docs.
    - Reads PDF text via pdfplumber (same as /extract-charges)
    - Calls the review_inputs_and_format_output service
    """

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    saved = []
    for uf in files:
        ext = pathlib.Path(uf.filename).suffix or ".pdf"
        target = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
        content = await uf.read()
        with target.open("wb") as out:
            out.write(content)
        saved.append({"orig": uf.filename, "path": target})

    # Extract text from each PDF
    docs = [{"filename": s["orig"], "text": _read_pdf_text(s["path"])} for s in saved]

    # Find tenant ledger text
    ledger_text = ""
    for d in docs:
        if "tenant_ledger" in d["filename"].lower():
            ledger_text = d["text"]
            break

    input_names = [d["filename"].rsplit(".", 1)[0].lower() for d in docs]

    # Run the ledger review
    approved, details, formatted = review_inputs_and_format_output(
        input_filenames=input_names,
        tenant_ledger_text=ledger_text,
        lease_start_date=lease_start_date,
    )

    return {
        "approved": approved,
        "details": details,
        "formatted": formatted,
    }
