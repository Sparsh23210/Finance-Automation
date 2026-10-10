"""
main.py - FastAPI application entry point.
Registers routers, creates DB tables on startup, and configures CORS.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.database import engine
from app.models import Base
from app.api.finance import router as finance_router
from app.api.tasks import router as tasks_router

# Create all tables on startup (idempotent — won't drop existing tables).
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ProofLoop API",
    description="Autonomous AI Task Worker — Evidence-Driven Finance Automation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(finance_router)
app.include_router(tasks_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "ProofLoop"}
