"""
Application entry point.

Run with:
    uvicorn app.main:app --reload

Interactive API docs are auto-generated at:
    http://127.0.0.1:8000/docs
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routers import alerts, auth, beacons, commands, devices

# Absolute path to the folder holding the dashboard's index.html, so it works
# no matter which directory the server is started from.
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables on startup (safe to run every time).
    init_db()
    yield


app = FastAPI(
    title="Sentinel Anti-Theft API",
    version="0.1.0",
    description="Consent-based, multi-tenant anti-theft platform.",
    lifespan=lifespan,
)

# Allow the web dashboard (a browser app) to call this API. In production set
# CORS_ORIGINS to your real dashboard URL(s) instead of "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(beacons.router)
app.include_router(alerts.router)
app.include_router(commands.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


# Serve the owner dashboard (a static web app) at /dashboard/.
# `html=True` makes it serve index.html for the directory root.
app.mount("/dashboard", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
