"""
config.py — Shared configuration and VideoDB connection singleton
"""

import os
import json
import videodb
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# ─────────────────────────────────────────────
# API Keys
# ─────────────────────────────────────────────
VIDEODB_API_KEY = os.environ.get("VIDEODB_API_KEY", "")
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY", "")

# ─────────────────────────────────────────────
# Episode Index (built by ingest.py)
# ─────────────────────────────────────────────
EPISODE_INDEX_PATH = Path(__file__).parent.parent / "data" / "episode_index.json"

def load_episode_index() -> dict:
    """Load the episode index saved by ingest.py."""
    if not EPISODE_INDEX_PATH.exists():
        raise FileNotFoundError(
            f"Episode index not found at {EPISODE_INDEX_PATH}. "
            "Run ingest.py first."
        )
    with open(EPISODE_INDEX_PATH) as f:
        return json.load(f)

# ─────────────────────────────────────────────
# VideoDB Connection (lazy singleton)
# ─────────────────────────────────────────────
_conn = None
_coll = None

def get_videodb_conn():
    global _conn
    if _conn is None:
        if not VIDEODB_API_KEY:
            raise ValueError("VIDEODB_API_KEY not set in .env")
        _conn = videodb.connect(api_key=VIDEODB_API_KEY)
    return _conn

def get_collection():
    global _coll
    if _coll is None:
        conn = get_videodb_conn()
        _coll = conn.get_collection()
    return _coll
