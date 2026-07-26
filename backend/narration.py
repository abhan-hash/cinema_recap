"""
narration.py — Layer 4: Narration Script Generation
=====================================================
Generates contextual narration text for each clip.
No TTS audio — narration is displayed as a text overlay in the frontend.
"""

import json
import re
from openai import OpenAI
from models import UserState, RetrievedClip, NarratedSegment
from config import GROQ_API_KEY


# Map focus characters to appropriate edge-tts voice names
# Used by the "Previously on..." intro audio
CHARACTER_VOICES = {
    "walter white":    "en-US-ChristopherNeural",
    "jesse pinkman":   "en-US-GuyNeural",
    "skyler white":    "en-US-JennyNeural",
    "hank schrader":   "en-US-EricNeural",
    "marie schrader":  "en-US-AriaNeural",
    "default":         "en-US-ChristopherNeural",  # Walter White
}


def get_voice_for_character(character: str | None) -> str:
    """Return the edge-tts voice closest to the chosen character."""
    if not character:
        return CHARACTER_VOICES["default"]
    return CHARACTER_VOICES.get(character.lower().strip(), CHARACTER_VOICES["default"])


def _build_narration_prompt(
    clips: list[RetrievedClip],
    user_state: UserState,
    series_name: str,
) -> str:
    clip_lines = []
    for i, clip in enumerate(clips):
        clip_lines.append(
            f"  [{i+1}] Ep{clip.episode_number} – {clip.moment_description} "
            f"(mood: {clip.mood})"
        )
    clips_str = "\n".join(clip_lines)

    focus = f"Focus character: {user_state.focus_character}." if user_state.focus_character else ""
    return f"""You are writing contextual text OVERLAYS for a '{series_name}' recap.
Each overlay appears on screen while a specific clip plays.
The viewer last watched {user_state.time_since_last_watch.replace('_', ' ')} ago and is about to watch Episode {user_state.next_episode}.
{focus}

Here are the clips in order:
{clips_str}

Write a SHORT, punchy overlay caption for each clip.
Rules:
- Max 12 words per caption — it's a caption, not a paragraph
- Use present tense — "Walter discovers..." not "Walter discovered..."
- Contextual to THAT specific clip's moment
- No generic phrases like "Meanwhile..." or "The tension builds..."
- Match the clip's mood: tense=urgent, dramatic=weight, calm=quiet, action=sharp, sad=heavy
- Don't repeat yourself across clips

Return ONLY valid JSON (no markdown):
{{"captions": ["caption for clip 1", "caption for clip 2", ...]}}"""


def generate_narration_scripts(
    clips: list[RetrievedClip],
    user_state: UserState,
    series_name: str,
) -> list[str]:
    """
    Generate a short contextual caption for each clip.
    Returns a list of caption strings in clip order.
    """
    if not GROQ_API_KEY or not clips:
        return [clip.moment_description[:60] for clip in clips]

    try:
        client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
        prompt = _build_narration_prompt(clips, user_state, series_name)

        print("✍️  Generating clip captions...")
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE).strip()

        data = json.loads(raw)
        captions = data.get("captions", [])

        # Ensure we have one per clip (fallback to description if short)
        result = []
        for i, clip in enumerate(clips):
            if i < len(captions) and captions[i]:
                result.append(str(captions[i]).strip())
            else:
                result.append(clip.moment_description[:80])

        print(f"   ✅ {len(result)} captions generated")
        return result

    except Exception as e:
        print(f"   ⚠️  Caption generation failed: {e} — using descriptions")
        return [clip.moment_description[:80] for clip in clips]


def build_narrated_segments(
    clips: list[RetrievedClip],
    captions: list[str],
) -> list[NarratedSegment]:
    """
    Pair each clip with its caption. No audio generation.
    """
    segments = []
    for i, clip in enumerate(clips):
        caption = captions[i] if i < len(captions) else ""
        segments.append(NarratedSegment(
            narration_text=caption,
            narration_audio_url=None,
            clip=clip,
        ))
    return segments
