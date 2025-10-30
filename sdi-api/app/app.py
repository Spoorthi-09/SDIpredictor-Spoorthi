# app/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os

from app.routers.predict import router as predict_router
from app.routers.adjudicate import router as adjudicate_router
from app.routers.extract import router as extract_router
from app.routers import ledger_router


app = FastAPI(title="SDI Claim API", version="1.0.0")

# --- CORS ---
allow_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "*")
allow_origins = [o.strip() for o in allow_origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(predict_router, prefix="")
app.include_router(adjudicate_router, prefix="")
app.include_router(extract_router, prefix="")
app.include_router(ledger_router.router)

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Serve all assets (css/js/images) from /static
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- Root page ---
@app.get("/", response_class=HTMLResponse)
def home():
    index_path = TEMPLATES / "index.html"
    return index_path.read_text(encoding="utf-8")
