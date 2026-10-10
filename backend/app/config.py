"""
config.py - Application configuration loaded from environment variables.
All secrets come from .env (never hardcoded).
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM Provider ─────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# When no API key is set we fall back to a deterministic rule-based planner.
LLM_ENABLED = bool(GEMINI_API_KEY)

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./proofloop.db")

# ── File workspace ────────────────────────────────────────────────────────────
# The agent is only allowed to read files from this directory.
WORKSPACE_DIR = os.path.abspath(
    os.getenv("WORKSPACE_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "sample_data"))
)

# ── Agent limits ──────────────────────────────────────────────────────────────
MAX_AGENT_STEPS   = int(os.getenv("MAX_AGENT_STEPS", "20"))
MAX_TOOL_RETRIES  = int(os.getenv("MAX_TOOL_RETRIES", "3"))

# ── Fault injection (dev/test only) ──────────────────────────────────────────
FAULT_INJECT = os.getenv("FAULT_INJECT", "")  # e.g. "timeout_after_write"

# ── CORS (allow the Vite dev server) ─────────────────────────────────────────
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
