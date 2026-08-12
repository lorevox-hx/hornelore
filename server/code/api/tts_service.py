"""
LoreVox TTS microservice entrypoint (port 8001)

Run:
  uvicorn code.api.tts_service:app --host 0.0.0.0 --port 8001
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Your router file is here:
from code.api.routers import tts
from code.api.net_guard import allowed_origins as _allowed_origins

APP_VERSION = "tts-1.0"

app = FastAPI(title="LoreVox TTS", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    # SECURITY-REVIEW-2026-08-12: was allow_origins=["*"] with
    # allow_credentials=True -- a combination the CORS spec forbids and
    # browsers silently refuse.  Now the shared local allowlist
    # (net_guard.py), credentials off (nothing here uses cookies/auth).
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# mount router at /api/tts/*
app.include_router(tts.router)

# warm TTS once at startup (optional but recommended)
@app.on_event("startup")
def _warm_tts():
    try:
        tts.warm()
    except Exception as e:
        print(f"[TTS] warm skipped/failed: {e}")

@app.get("/api/health")
def health():
    return {"ok": True, "service": "tts", "version": APP_VERSION}
