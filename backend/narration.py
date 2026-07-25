"""
narration.py — Layer 4A: Narration Generation
===============================================
Uses Google Gemini (free) to write bridging narration scripts between clips.
TTS audio is optional — the UI shows narration text regardless.
"""

import json
import re
from openai import OpenAI
from models import UserState, RetrievedClip, NarratedSegment
from config import GROQ_API_KEY


def _build_narration_prompt(
    clips: list[RetrievedClip],
    user_state: UserState,
    series_name: str,
) -> str:
    clips_summary = "\n".join([
        f"{i+1}. [Episode {c.episode_number}: {c.episode_title}] {c.moment_description}"
        for i, c in enumerate(clips)
    ])

    focus_line = (
        f"The viewer is particularly focused on {user_state.focus_character}'s story."
        if user_state.focus_character
        else ""
    )

    n_bridges = len(clips) - 1

    return f"""You are writing voice-over narration for a personalised "Previously on {series_name}..." recap.

The recap will show these clips IN ORDER:
{clips_summary}

Context:
- The viewer watched episodes {sorted(user_state.watched_episodes)} and is now about to watch Episode {user_state.next_episode}
- They last watched {user_state.time_since_last_watch.replace('_', ' ')}
- {focus_line}

Write narration for this recap:
1. OPENING line (1 sentence): "Previously on {series_name}..." style
2. BRIDGE lines: {n_bridges} lines, one between each clip (1-2 sentences each)
3. CLOSING line: tease the next episode "And now, Episode {user_state.next_episode}..."

Rules:
- Present tense, active voice, TV narrator tone
- Each bridge connects the previous clip to the next one
- Total narration under 200 words

Return ONLY valid JSON — no markdown, no code fences:
{{"opening": "Previously on {series_name}...", "bridges": ["bridge 1", "bridge 2"], "closing": "And now, Episode {user_state.next_episode}..."}}

The bridges array must have exactly {n_bridges} items.
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
    Combine clips with narration text.
    Segment i = narration[i] + clip[i]
    The closing narration is appended to the last segment's narration_text.
    """
    narrations = (
        [scripts.get("opening", "Previously...")] +
        list(scripts.get("bridges", []))
    )
    closing = scripts.get("closing", "")

    segments = []
    for i, clip in enumerate(clips):
        narration_text = narrations[i] if i < len(narrations) else ""

        # Attach closing text to the last segment
        if i == len(clips) - 1 and closing:
            narration_text = narration_text + " " + closing if narration_text else closing

        segments.append(NarratedSegment(
            narration_text=narration_text.strip(),
            narration_audio_url=None,   # TTS not used — saves $, still looks great
            clip=clip,
        ))

    return segments
