"""STAT — Speech Triage And Tag: FastAPI backend."""

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Request, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from stt import transcribe
from triage import triage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="STAT API", version="0.2.0")

# Secret path for access control
APP_SECRET_PATH = os.environ.get("APP_SECRET_PATH", "")
if not APP_SECRET_PATH:
    logger.warning("APP_SECRET_PATH is not set — all routes will be inaccessible")

# Google Sheet webhook URL (Apps Script Web App)
GOOGLE_SHEET_WEBHOOK_URL = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL", "")

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


@app.post(f"/s/{APP_SECRET_PATH}/transcribe-and-triage")
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

    # Step 2: Gemini triage
    try:
        results = triage(transcript)
    except RuntimeError as e:
        logger.error("Triage failed: %s", e)
        raise HTTPException(status_code=502, detail={
            "error": "triage_failed",
            "message": f"AI 判讀失敗：{e}",
            "transcript": transcript,
        })

    # Step 3: Build response — assign case_id to each casualty
    now = datetime.now(TW_TZ)
    casualties = []
    for result in results:
        _case_counter += 1
        casualties.append({
            "transcript": transcript,
            "triage_level": result["triage_level"],
            "triage_label": result["triage_label"],
            "summary": result["summary"],
            "actions": result["actions"],
            "march": result.get("march"),
            "vitals": result.get("vitals"),
            "trauma_codes": result.get("trauma_codes", []),
            "mechanism_codes": result.get("mechanism_codes", []),
            "special_population": result.get("special_population", []),
            "mist": result.get("mist"),
            "timestamp": now.isoformat(),
            "case_id": f"{_case_counter:03d}",
        })

    return JSONResponse(content={"casualties": casualties})


@app.post(f"/s/{APP_SECRET_PATH}/log-casualties")
async def log_casualties(request: Request):
    """Forward confirmed casualty records to Google Sheet via Apps Script webhook."""
    if not GOOGLE_SHEET_WEBHOOK_URL:
        return JSONResponse(content={"status": "skipped", "reason": "no webhook URL configured"})

    body = await request.json()
    casualties = body.get("casualties", [])
    if not casualties:
        return JSONResponse(content={"status": "skipped", "reason": "no casualties"})

    rows = []
    for c in casualties:
        vitals = c.get("vitals") or {}
        march = c.get("march") or {}
        mist = c.get("mist") or {}
        airway = march.get("a_airway") or {}
        rows.append({
            "case_id": c.get("case_id", ""),
            "timestamp": c.get("timestamp", ""),
            "triage_level": c.get("triage_level", ""),
            "triage_label": c.get("triage_label", ""),
            "summary": c.get("summary", ""),
            "actions": " / ".join(c.get("actions") or []),
            "consciousness": vitals.get("consciousness", ""),
            "hr": vitals.get("hr", ""),
            "bp": vitals.get("bp", ""),
            "spo2": vitals.get("spo2", ""),
            "temp": vitals.get("temp", ""),
            "rr": vitals.get("rr", ""),
            "gcs": vitals.get("gcs", ""),
            "march_m": march.get("m_hemorrhage", ""),
            "march_a": airway.get("description", "") if isinstance(airway, dict) else str(airway),
            "march_r": march.get("r_respiration", ""),
            "march_c": march.get("c_circulation", ""),
            "march_h": march.get("h_hypothermia", ""),
            "mist_m": mist.get("m_mechanism", ""),
            "mist_i": mist.get("i_injuries", ""),
            "mist_s": mist.get("s_signs", ""),
            "mist_t": mist.get("t_treatment", ""),
            "trauma_codes": ", ".join(str(x) for x in (c.get("trauma_codes") or [])),
            "mechanism_codes": ", ".join(str(x) for x in (c.get("mechanism_codes") or [])),
            "special_population": ", ".join(c.get("special_population") or []),
            "transcript": c.get("transcript", ""),
        })

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            resp = await client.post(GOOGLE_SHEET_WEBHOOK_URL, json={"rows": rows})
            resp.raise_for_status()
        logger.info("Logged %d casualties to Google Sheet", len(rows))
        return JSONResponse(content={"status": "ok", "count": len(rows)})
    except Exception as e:
        logger.error("Failed to log to Google Sheet: %s", e)
        return JSONResponse(status_code=502, content={"status": "error", "message": str(e)})


# Serve frontend at secret path
@app.get(f"/s/{APP_SECRET_PATH}/")
async def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse(content={"message": "STAT API is running"})


@app.get(f"/s/{APP_SECRET_PATH}/ble-test")
async def serve_ble_test():
    ble_path = FRONTEND_DIR / "ble-test.html"
    if ble_path.exists():
        return FileResponse(ble_path)
    return JSONResponse(status_code=404, content={"message": "Not found"})


# Mount frontend static files under secret path
if FRONTEND_DIR.exists():
    app.mount(
        f"/s/{APP_SECRET_PATH}/static",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="static",
    )
