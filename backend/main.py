"""
main.py — FastAPI Backend
==========================
Endpoints:
  GET  /series              → Series info (episodes, characters)
  POST /generate-recap      → Full recap generation pipeline
  GET  /clip-stream         → Get a streamable URL for a single clip
  GET  /audio/{filename}    → Serve generated audio files (previously-on intro)
  GET  /health              → Health check
"""

import os
import hashlib
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models import UserState, RecapResponse, SeriesInfo, EpisodeInfo
from config import load_episode_index, get_collection, get_videodb_conn, GROQ_API_KEY
from agent import plan_recap
from retrieval import retrieve_clips, get_clip_stream_url, qa_and_refine_clips
from narration import get_voice_for_character

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from videodb.editor import Timeline, VideoAsset, Track, Clip

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────

app = FastAPI(
    title="RecapAI Backend",
    description="Personalised TV recap generator powered by VideoDB + Groq",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIO_DIR = Path(__file__).parent.parent / "data" / "audio_cache"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# Helper: Generate "Previously on..." intro audio
# ─────────────────────────────────────────────

def _generate_previously_on_audio(series_name: str, focus_character: str | None) -> str | None:
    """
    Generate a short 'Previously on <Series>...' audio clip using edge-tts.
    Returns the relative URL path to serve it, or None if generation fails.
    """
    voice = get_voice_for_character(focus_character)
    text = f"Previously on {series_name}..."

    text_hash = hashlib.md5(f"{text}_{voice}".encode()).hexdigest()
    filename = f"previously_on_{text_hash}.mp3"
    filepath = AUDIO_DIR / filename

    if not filepath.exists():
        print(f"🎙️  Generating 'Previously on' audio (voice: {voice})...")
        try:
            subprocess.run(
                ["edge-tts", "--voice", voice, "--text", text, "--write-media", str(filepath)],
                check=True, capture_output=True
            )
            print(f"   ✅ Audio saved: {filename}")
        except Exception as e:
            print(f"   ⚠️  edge-tts failed: {e}")
            return None

    return f"/audio/{filename}"


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "RecapAI"}


@app.get("/series", response_model=SeriesInfo)
def get_series_info():
    """Returns info about the ingested series — used to populate the frontend form."""
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
    2. Planning agent (Groq/Llama) reads transcripts → recap brief
    3. VideoDB retrieval → frame-accurate clips
    4. Caption generation → short contextual overlays
    5. "Previously on..." audio generation (character-voiced)
    6. Seamless timeline compilation (video only)
    7. Return assembled recap
    """
    print(f"\n{'='*60}")
    print(f"🎬 Generating recap: watched={user_state.watched_episodes}, next=Ep{user_state.next_episode}")
    print(f"   Time since last watch: {user_state.time_since_last_watch}")
    print(f"   Focus character: {user_state.focus_character or 'None'}")
    print(f"{'='*60}\n")

    # ── Load episode index ──
    try:
        episode_index = load_episode_index()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    series_name = episode_index["series_name"]
    characters  = episode_index["characters"]
    episodes    = episode_index["episodes"]

    # ── Validate watched episodes ──
    valid_watched = [ep for ep in user_state.watched_episodes if str(ep) in episodes]
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

    # ── Layer 4: Senior Director QA pass ──
    print("\n🎬 Running Director QA pass...")
    try:
        clips = qa_and_refine_clips(clips, episode_index, groq_api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"⚠️  QA pass failed: {e} — using raw clips")

    if not clips:
        raise HTTPException(status_code=500, detail="All clips were dropped by QA pass")

    # ── Build segments (no captions — just clips with empty narration_text) ──
    segments = []
    from models import NarratedSegment
    for clip in clips:
        segments.append(NarratedSegment(narration_text="", clip=clip))

    # ── Total duration ──
    total_duration = sum(seg.clip.end - seg.clip.start for seg in segments)

    # ── Layer 5: "Previously on..." intro audio ──
    previously_on_url = _generate_previously_on_audio(series_name, user_state.focus_character)

    # ── Layer 6: Compile Seamless Stream (video only) ──
    compiled_stream_url = None
    try:
        print("🎬 Compiling seamless video timeline...")
        timeline = Timeline(get_videodb_conn())
        video_track = Track()

        current_time = 0.0
        for seg in segments:
            video_asset = VideoAsset(id=seg.clip.video_id, start=seg.clip.start)
            duration = seg.clip.end - seg.clip.start
            video_clip = Clip(asset=video_asset, duration=duration)
            video_track.add_clip(start=current_time, clip=video_clip)
            current_time += duration

        timeline.add_track(video_track)
        compiled_stream_url = timeline.generate_stream()
        print(f"🎬 Seamless stream ready: {compiled_stream_url}")
    except Exception as e:
        print(f"⚠️  Timeline compilation failed: {e}")

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
        compiled_stream_url=compiled_stream_url,
        previously_on_audio_url=previously_on_url,
        status=status,
        message=message,
    )


@app.get("/clip-stream")
def clip_stream(video_id: str, start: float, end: float):
    """Generate a streamable URL for a specific clip."""
    try:
        url = get_clip_stream_url(video_id, start, end)
        return {"stream_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audio/{filename}")
def serve_audio(filename: str):
    """Serve a generated audio file (e.g. previously-on intro)."""
    file_path = AUDIO_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(file_path), media_type="audio/mpeg")
