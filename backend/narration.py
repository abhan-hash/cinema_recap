"""
narration.py — Layer 4A: Narration Generation
===============================================
Uses Google Gemini (free) to write bridging narration scripts between clips.
TTS audio is optional — the UI shows narration text regardless.
"""

import json
import re
import os
import subprocess
import hashlib
from pathlib import Path
from openai import OpenAI
from models import UserState, RetrievedClip, NarratedSegment
from config import GROQ_API_KEY, get_videodb_conn

TTS_DIR = Path(__file__).parent.parent / "data" / "tts_cache"
TTS_DIR.mkdir(parents=True, exist_ok=True)


def _build_narration_prompt(
    clips: list[RetrievedClip],
    user_state: UserState,
    series_name: str,
) -> str:
    beats = "\n".join([
        f"{i+1}. [Ep {c.episode_number} · {c.mood.upper()}] {c.moment_description}"
        for i, c in enumerate(clips)
    ])

    focus_line = (
        f"The viewer is tracking {user_state.focus_character}'s arc specifically."
        if user_state.focus_character else ""
    )

    n_bridges = len(clips) - 1

    return f"""You are the VOICE OF GOD narrator for "{series_name}" — gravelly, urgent, cinematic.
You are writing the narration for a 'Previously on...' cold open that plays OVER rapid-fire video cuts.

The cuts play in this order:
{beats}

{focus_line}
Viewer is about to watch Episode {user_state.next_episode}.

Write narration that makes the viewer FEEL the weight of what happened:
- OPENING: One punchy line. Start with "Previously on {series_name}..." then land a gut-punch sentence.
- BRIDGES ({n_bridges} total, one per cut transition): 1 SHORT sentence max. 
  These play AS the clip cuts happen — they must be urgent, cliffhanger-y, never bland.
  Use fragments. Use dramatic pauses. e.g. "And then—" / "But Walter had other plans." / "One lie. That's all it took."
- CLOSING: Tease the next episode with dread. e.g. "Now the walls are closing in."

Rules:
- Present tense. Active. Punchy. No filler words.
- Match the MOOD of each beat (tense/dramatic/calm/action/sad)
- The whole narration read aloud should feel like a 30-second movie trailer

Return ONLY valid JSON — no markdown, no code fences:
{{"opening": "Previously on {series_name}... [one punchy sentence]", "bridges": ["bridge 1", "bridge 2"], "closing": "And now..."}}

The bridges array must have EXACTLY {n_bridges} items.
"""


def generate_narration_scripts(
    clips: list[RetrievedClip],
    user_state: UserState,
    series_name: str,
) -> dict:
    """Ask Groq to write narration. Returns dict with opening, bridges, closing."""
    fallback = {
        "opening": f"Previously on {series_name}...",
        "bridges": ["Meanwhile, the story continued..." for _ in range(max(0, len(clips) - 1))],
        "closing": f"And now, Episode {user_state.next_episode}...",
    }

    if not clips or not GROQ_API_KEY:
        return fallback

    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )

    prompt = _build_narration_prompt(clips, user_state, series_name)

    print("🎙️  Generating narration scripts with Groq...")
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE).strip()

        scripts = json.loads(raw)
    except Exception as e:
        print(f"   ⚠️  Narration generation failed: {e} — using fallback")
        return fallback

    # Ensure bridges list has correct length
    expected = len(clips) - 1
    bridges = scripts.get("bridges", [])
    while len(bridges) < expected:
        bridges.append("Meanwhile...")
    scripts["bridges"] = bridges[:expected]

    print(f"   ✅ Narration scripts generated")
    return scripts


def build_narrated_segments(
    clips: list[RetrievedClip],
    scripts: dict,
) -> list[NarratedSegment]:
    """
    Combine clips with narration text, generate TTS, and upload to VideoDB.
    """
    narrations = (
        [scripts.get("opening", "Previously...")] +
        list(scripts.get("bridges", []))
    )
    closing = scripts.get("closing", "")

    conn = get_videodb_conn()
    coll = conn.get_collection()

    segments = []
    for i, clip in enumerate(clips):
        narration_text = narrations[i] if i < len(narrations) else ""

        # Attach closing text to the last segment
        if i == len(clips) - 1 and closing:
            narration_text = narration_text + " " + closing if narration_text else closing
            
        narration_text = narration_text.strip()
        
        audio_url = None
        audio_id = None
        audio_length = 0.0
        if narration_text:
            text_hash = hashlib.md5(narration_text.encode('utf-8')).hexdigest()
            filename = f"tts_{text_hash}.mp3"
            filepath = TTS_DIR / filename
            
            if not filepath.exists():
                print(f"🎙️ Generating TTS for segment {i+1}...")
                subprocess.run([
                    "edge-tts", 
                    "--voice", "en-US-ChristopherNeural", 
                    "--text", narration_text, 
                    "--write-media", str(filepath)
                ], check=True)
            
            audio_url = f"/tts/{filename}"
            print(f"☁️ Uploading TTS audio to VideoDB...")
            audio_asset = coll.upload(file_path=str(filepath))
            audio_id = audio_asset.id
            audio_length = float(getattr(audio_asset, 'length', 0.0))

        segments.append(NarratedSegment(
            narration_text=narration_text,
            narration_audio_url=audio_url,
            narration_audio_id=audio_id,
            narration_audio_length=audio_length,
            clip=clip,
        ))

    return segments
