"""
main.py — FastAPI Backend
==========================
Endpoints:
  GET  /series         → Series info (episodes, characters)
  POST /generate-recap → Full recap generation pipeline
  GET  /clip-stream    → Get a streamable URL for a single clip
  GET  /tts/{filename} → Serve TTS audio files
  GET  /health         → Health check
"""

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from models import UserState, RecapResponse, SeriesInfo, EpisodeInfo
from config import load_episode_index, get_collection, get_videodb_conn
from agent import plan_recap
from retrieval import retrieve_clips, get_clip_stream_url
from narration import generate_narration_scripts, build_narrated_segments

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────

app = FastAPI(
    title="RecapAI Backend",
    description="Personalised TV recap generator powered by VideoDB + Claude",
    version="1.0.0",
)

# Allow requests from the frontend (dev + prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve TTS audio files
TTS_DIR = Path(__file__).parent.parent / "data" / "tts_cache"
TTS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "RecapAI"}


@app.get("/series", response_model=SeriesInfo)
def get_series_info():
    """
    Returns info about the ingested series — used to populate the frontend form.
    """
    try:
        index = load_episode_index()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    episodes = [
        EpisodeInfo(
            number=ep_data["number"],
            title=ep_data["title"],
            video_id=ep_data["video_id"],
        )
        for ep_key, ep_data in sorted(index["episodes"].items(), key=lambda x: int(x[0]))
    ]

    return SeriesInfo(
        series_name=index["series_name"],
        characters=index["characters"],
        episodes=episodes,
    )


@app.post("/generate-recap", response_model=RecapResponse)
async def generate_recap(user_state: UserState):
    """
    Main pipeline:
    1. Load episode index
    2. Planning agent (Claude) → recap brief
    3. VideoDB retrieval → clips
    4. Narration generation (Claude) → scripts
    5. TTS → audio files
    6. Return assembled recap
    """
    print(f"\n{'='*60}")
    print(f"🎬 Generating recap for: watched={user_state.watched_episodes}, next=Ep{user_state.next_episode}")
    print(f"   Time since last watch: {user_state.time_since_last_watch}")
    print(f"   Focus character: {user_state.focus_character or 'None'}")
    print(f"{'='*60}\n")

    # ── Load episode index ──
    try:
        episode_index = load_episode_index()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    series_name = episode_index["series_name"]
    characters = episode_index["characters"]
    episodes = episode_index["episodes"]

    # ── Validate watched episodes exist in index ──
    valid_watched = [
        ep for ep in user_state.watched_episodes
        if str(ep) in episodes
    ]
    if not valid_watched:
        raise HTTPException(
            status_code=400,
            detail="None of the watched episodes are in the index. Run ingest.py first."
        )

    # ── Layer 2: Planning agent ──
    try:
        moments = plan_recap(user_state, series_name, characters, episodes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planning agent failed: {e}")

    if not moments:
        raise HTTPException(status_code=500, detail="Planning agent returned no moments")

    # ── Layer 3: VideoDB retrieval ──
    try:
        clips = retrieve_clips(moments, valid_watched, episode_index)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clip retrieval failed: {e}")

    if not clips:
        raise HTTPException(status_code=500, detail="No clips could be retrieved from VideoDB")

    # ── Layer 4: Narration generation ──
    try:
        scripts = generate_narration_scripts(clips, user_state, series_name)
        segments = build_narrated_segments(clips, scripts)
    except Exception as e:
        print(f"⚠️  Narration failed: {e} — using minimal fallback")
        segments = build_narrated_segments(clips, {
            "opening": f"Previously on {series_name}...",
            "bridges": ["Meanwhile..." for _ in range(len(clips) - 1)],
            "closing": f"And now, Episode {user_state.next_episode}...",
        })

    # ── Calculate total duration ──
    total_duration = sum(
        (seg.clip.end - seg.clip.start) for seg in segments
    )

    # ── Determine status ──
    status = "success" if len(clips) >= len(moments) * 0.7 else "partial"
    message = (
        f"Generated {len(segments)}-clip recap ({total_duration:.0f}s) for Episode {user_state.next_episode}"
        if status == "success"
        else f"Retrieved {len(clips)}/{len(moments)} clips — some moments weren't found"
    )

    print(f"\n✅ Recap ready: {len(segments)} segments, {total_duration:.0f}s total")
    print(f"{'='*60}\n")

    return RecapResponse(
        user_state=user_state,
        total_duration_seconds=total_duration,
        segments=segments,
        compiled_stream_url=None,  # Timeline compilation in next step
        status=status,
        message=message,
    )


@app.get("/clip-stream")
def clip_stream(video_id: str, start: float, end: float):
    """
    Generate a streamable URL for a specific clip.
    Used by the frontend player for individual clip playback.
    """
    try:
        url = get_clip_stream_url(video_id, start, end)
        return {"stream_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tts/{filename}")
def serve_tts(filename: str):
    """Serve a cached TTS audio file."""
    file_path = TTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(file_path), media_type="audio/mpeg")
