"""
agent.py — Layer 2: Recap Planning Agent
=========================================
Grounded approach: fetches the real transcript from VideoDB first,
then asks the LLM to pick moments FROM the actual content.
This eliminates hallucination — every beat the LLM picks is anchored
to something that was actually said in the episodes.
"""

import json
import re
from openai import OpenAI
from models import UserState, MomentBrief
from config import GROQ_API_KEY, get_collection

# How many beats per recap style
MOMENT_COUNTS = {
    "short":  4,
    "medium": 7,
    "long":   12,
}

# Base clip duration in seconds around each dialogue beat
CLIP_SECONDS = {
    "short":  6,
    "medium": 9,
    "long":   12,
}


def _fetch_episode_transcripts(
    watched_episode_numbers: list[int],
    episodes: dict,
    max_chars_per_ep: int = 8000,
) -> dict[int, str]:
    """
    Fetch the actual transcript text for each watched episode from VideoDB.
    Returns {episode_number: transcript_text}
    """
    coll = get_collection()
    transcripts = {}
    for ep_num in watched_episode_numbers:
        ep_key = str(ep_num)
        if ep_key not in episodes:
            continue
        vid_id = episodes[ep_key]["video_id"]
        title  = episodes[ep_key]["title"]
        try:
            video = coll.get_video(vid_id)
            text  = video.get_transcript_text() or ""
            # Truncate per episode to manage prompt size
            if len(text) > max_chars_per_ep:
                text = text[:max_chars_per_ep] + "\n[transcript continues...]"
            transcripts[ep_num] = text
            print(f"   📄 Loaded transcript Ep {ep_num} ({title}): {len(text)} chars")
        except Exception as e:
            print(f"   ⚠️  Could not load transcript for Ep {ep_num}: {e}")

    return transcripts


def _build_prompt(
    user_state: UserState,
    series_name: str,
    characters: list[str],
    episodes: dict,
    transcripts: dict[int, str],
) -> str:
    n_beats   = MOMENT_COUNTS.get(user_state.recap_length, 7)
    beat_secs = CLIP_SECONDS.get(user_state.recap_length, 9)

    focus_line = (
        f"Weight the beats toward {user_state.focus_character}'s arc."
        if user_state.focus_character
        else "Balance beats across the main story threads."
    )

    # Build the grounded transcript block
    transcript_block = ""
    for ep_num in sorted(transcripts.keys()):
        ep_title = episodes[str(ep_num)]["title"]
        transcript_block += f"\n\n--- EPISODE {ep_num}: {ep_title} TRANSCRIPT ---\n"
        transcript_block += transcripts[ep_num]

    return f"""You are an expert TV editor cutting a 'Previously on {series_name}...' cold-open.

IMPORTANT: You are working ONLY from the transcripts below. Do NOT invent scenes or dialogue from your training data.
Every moment you pick MUST be directly supported by text you can see in the transcripts.

{transcript_block}

---

TASK: The viewer watched Episodes {sorted(user_state.watched_episodes)} and is about to watch Episode {user_state.next_episode}.
{focus_line}
Known characters: {', '.join(characters)}

Pick EXACTLY {n_beats} beats for the recap. Think like a TRAILER EDITOR:
- Sequence beats to BUILD — setup → rising stakes → biggest shock/cliffhanger
- Prefer SHORT, emotionally punchy lines over long exposition
- Prefer moments that set up UNRESOLVED tension going into Episode {user_state.next_episode}

For EACH beat, provide:
- `moment_description`: What is happening visually (keep to 1 sentence)
- `exact_dialogue`: The EXACT line of dialogue from the transcript above that anchors this moment.
  This MUST be verbatim text you can see in the transcript. Do NOT paraphrase.
  If it's a pure action beat with no dialogue, set to null.
- `episode`: episode number (integer)
- `clip_duration_seconds`: seconds this beat needs ({beat_secs-2}–{beat_secs+4}s range).
  Short punchy action = {beat_secs-2}s. A key line that needs to land = {beat_secs+4}s.
- `mood`: one of: tense | dramatic | calm | action | sad
- `importance`: one of: critical | important | context

Return ONLY valid JSON — no markdown, no code fences:
{{"moments": [
  {{"moment_description": "...", "exact_dialogue": "...", "episode": 1, "clip_duration_seconds": {beat_secs}, "mood": "tense", "importance": "critical", "characters_involved": ["Walter White"]}}
]}}"""


def plan_recap(
    user_state: UserState,
    series_name: str,
    characters: list[str],
    episodes: dict,
) -> list[MomentBrief]:
    """
    Grounded recap planning:
    1. Load actual transcripts from VideoDB
    2. Feed them to Groq so it picks moments from REAL content
    3. Return MomentBriefs with exact dialogue anchors
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set — get one free at https://console.groq.com/keys")

    # Step 1: Load real transcripts
    print("📄 Loading episode transcripts from VideoDB...")
    transcripts = _fetch_episode_transcripts(
        watched_episode_numbers=user_state.watched_episodes,
        episodes=episodes,
    )
    if not transcripts:
        raise ValueError("Could not load any episode transcripts from VideoDB")

    # Step 2: Build grounded prompt and call Groq
    prompt = _build_prompt(user_state, series_name, characters, episodes, transcripts)
    print(f"🤖 Calling Groq (prompt: {len(prompt)} chars)...")

    client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",   # Use the bigger model for grounded selection
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=2000,
    )
    raw = response.choices[0].message.content.strip()
    print(f"   Groq response: {len(raw)} chars")

    # Strip markdown fences
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"Groq returned non-JSON: {raw[:300]}")

    # Step 3: Parse moments
    beat_secs = CLIP_SECONDS.get(user_state.recap_length, 9)
    moments = []
    for m in data.get("moments", []):
        importance = m.get("importance", "important")
        duration   = int(m.get("clip_duration_seconds", beat_secs))
        duration   = max(5, min(15, duration))

        brief = MomentBrief(
            moment_description=m["moment_description"],
            episode=int(m["episode"]),
            importance=importance,
            characters_involved=m.get("characters_involved", []),
            clip_duration_seconds=duration,
            mood=m.get("mood", "tense"),
            exact_dialogue=m.get("exact_dialogue") or None,
        )
        moments.append(brief)

    # Sort by episode then narrative position
    moments.sort(key=lambda m: m.episode)

    print(f"\n   ✅ {len(moments)} grounded beats selected:")
    for i, m in enumerate(moments):
        diag = f'  → "{m.exact_dialogue[:50]}"' if m.exact_dialogue else "  (action beat)"
        print(f"   {i+1}. [Ep {m.episode}] [{m.mood}] {m.moment_description[:55]}...")
        print(f"      {diag}")

    return moments
