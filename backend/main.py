"""
FastAPI backend — Medical Platform (triaje, ruteo, recomendación de clínicas).
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Always load from services/.env (user's location), then allow cwd/.env to override
_services_env = os.path.join(os.path.dirname(__file__), "services", ".env")
load_dotenv(_services_env)
load_dotenv(override=False)  # also pick up backend/.env if it exists

sys.path.insert(0, os.path.dirname(__file__))

from routers import patient, doctor, chat

app = FastAPI(
    title="MedConnect — Plataforma Médica Inteligente",
    description="Triaje con IA, ruteo a clínicas y mensajería doctor-paciente.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_csp_header(request, call_next):
    response = await call_next(request)
    csp = (
        "default-src * 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "script-src * 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "connect-src * 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "img-src * 'self' 'unsafe-inline' data: blob:; "
        "style-src * 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src * 'self' 'unsafe-inline' data: https://fonts.gstatic.com; "
        "worker-src * 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "frame-src * 'self' 'unsafe-inline' 'unsafe-eval' data: blob:;"
    )
    response.headers["Content-Security-Policy"] = csp
    return response


# Mount frontend
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/ui", StaticFiles(directory=frontend_path, html=True), name="frontend")

# Routers
app.include_router(patient.router)
app.include_router(doctor.router)
app.include_router(chat.router)


@app.get("/", tags=["health"])
async def health_check():
    return {
        "status": "ok",
        "service": "MedConnect",
        "version": "2.0.0",
    }


@app.get("/ui", include_in_schema=False)
@app.get("/ui/", include_in_schema=False)
async def ui_root():
    return RedirectResponse(url="/ui/login.html")
