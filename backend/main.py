"""STAT — Speech Triage And Tag: FastAPI backend."""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from stt import transcribe
from triage import triage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="STAT API", version="0.1.0")

# CORS — allow all origins for POC
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory case counter (resets on deploy/restart)
_case_counter = 0

TW_TZ = timezone(timedelta(hours=8))

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.post("/transcribe-and-triage")
async def transcribe_and_triage(audio_file: UploadFile = File(...)):
    """Receive audio, transcribe, run START triage, return result."""
    global _case_counter

    # Read audio bytes
    audio_bytes = await audio_file.read()

    # Validate minimum size (rough proxy for <2s audio)
    if len(audio_bytes) < 5000:
        raise HTTPException(status_code=400, detail={
            "error": "audio_too_short",
            "message": "口述時間不足，請錄製至少 2 秒",
        })

    # Step 1: Speech-to-Text
    try:
        transcript = transcribe(audio_bytes)
    except RuntimeError as e:
        logger.error("STT failed: %s", e)
        raise HTTPException(status_code=502, detail={
            "error": "stt_failed",
            "message": f"語音辨識失敗：{e}",
        })

    # Step 2: Claude triage
    try:
        result = triage(transcript)
    except RuntimeError as e:
        logger.error("Triage failed: %s", e)
        raise HTTPException(status_code=502, detail={
            "error": "triage_failed",
            "message": f"AI 判讀失敗：{e}",
            "transcript": transcript,
        })

    # Step 3: Build response
    _case_counter += 1
    now = datetime.now(TW_TZ)

    return JSONResponse(content={
        "transcript": transcript,
        "triage_level": result["triage_level"],
        "triage_label": result["triage_label"],
        "summary": result["summary"],
        "actions": result["actions"],
        "timestamp": now.isoformat(),
        "case_id": f"{_case_counter:03d}",
    })


# Serve frontend
@app.get("/")
async def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse(content={"message": "STAT API is running"})


# Mount frontend static files (if any assets exist later)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
