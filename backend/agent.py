"""
agent.py — Layer 2: Multi-Agent Recap Planning
=========================================
We split planning into three distinct AI Agents to prevent context collapse:
1. The Researcher: Maps out the actual plot threads from the transcript.
2. The Showrunner: Designs the narrative arc (A-Plot/B-Plot) based on user prefs.
3. The Editor: Finds the exact verbatim dialogue anchors in the transcript.
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
            if len(text) > max_chars_per_ep:
                text = text[:max_chars_per_ep] + "\n[transcript continues...]"
            transcripts[ep_num] = text
            print(f"   📄 Loaded transcript Ep {ep_num} ({title}): {len(text)} chars")
        except Exception as e:
            print(f"   ⚠️  Could not load transcript for Ep {ep_num}: {e}")

    return transcripts


def _call_llm(prompt: str, client: OpenAI) -> str:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=2000,
    )
    return response.choices[0].message.content.strip()


def _run_researcher_agent(transcripts: dict[int, str], series_name: str, client: OpenAI) -> str:
    print("🤖 [Agent 1] Researcher is analyzing transcripts...")
    transcript_block = ""
    for ep_num in sorted(transcripts.keys()):
        transcript_block += f"\n\n--- EPISODE {ep_num} TRANSCRIPT ---\n{transcripts[ep_num]}"

    prompt = f"""You are the Lead Researcher for a TV recap of {series_name}.
Read the following transcripts and extract a structured "Plot Map".
Ignore formatting and timestamps. Focus entirely on WHAT HAPPENED.

{transcript_block}

---
TASK:
Output a clean, concise summary of:
1. The A-Plot (The main driving storyline)
2. The B-Plot (The secondary character storylines)
3. Unresolved Tensions (What is left hanging?)
"""
    return _call_llm(prompt, client)


def _run_showrunner_agent(plot_map: str, user_state: UserState, characters: list[str], client: OpenAI) -> str:
    print("🤖 [Agent 2] Showrunner is designing the narrative arc...")
    n_beats = MOMENT_COUNTS.get(user_state.recap_length, 7)
    focus = f"Focus heavily on {user_state.focus_character}." if user_state.focus_character else "Balance the A-Plot and B-Plot."

    prompt = f"""You are the Showrunner editing a 'Previously on...' recap.
Here is the Plot Map of what the viewer has seen so far:
{plot_map}

TASK:
The viewer watched Episodes {sorted(user_state.watched_episodes)} and is about to watch Episode {user_state.next_episode}.
{focus}

Design a "Recap Blueprint" of EXACTLY {n_beats} story beats. 
- Sequence them chronologically to build tension (Setup -> Rising Action -> Cliffhanger).
- Inject 1-2 "B-Roll" (silent visual action shots) to help the pacing breathe.

Output a numbered list of the {n_beats} beats. For each beat, describe WHAT HAPPENS and WHY it matters.
Do NOT worry about exact dialogue or JSON formatting yet. Just write the creative blueprint.
"""
    return _call_llm(prompt, client)


def _run_editor_agent(blueprint: str, transcripts: dict[int, str], beat_secs: int, client: OpenAI) -> str:
    print("🤖 [Agent 3] Editor is finding exact transcript anchors...")
    transcript_block = ""
    for ep_num in sorted(transcripts.keys()):
        transcript_block += f"\n\n--- EPISODE {ep_num} TRANSCRIPT ---\n{transcripts[ep_num]}"

    prompt = f"""You are the Video Editor. You must execute this Recap Blueprint by finding EXACT dialogue anchors in the transcripts.

BLUEPRINT:
{blueprint}

TRANSCRIPTS:
{transcript_block}

TASK:
For EACH beat in the blueprint, find the PERFECT exact, verbatim line of dialogue from the transcripts to anchor it.
If it is a B-Roll action beat, set exact_dialogue to null.

Return ONLY valid JSON:
{{"moments": [
  {{"moment_description": "...", "exact_dialogue": "exact verbatim text from transcript", "episode": 1, "clip_duration_seconds": {beat_secs}, "mood": "tense", "importance": "critical", "characters_involved": ["Walt"]}}
]}}
"""
    raw = _call_llm(prompt, client)
    # Strip markdown
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE).strip()
    return raw


def plan_recap(
    user_state: UserState,
    series_name: str,
    characters: list[str],
    episodes: dict,
) -> list[MomentBrief]:
    """
    Multi-Agent grounded recap planning:
    1. Researcher -> Plot Map
    2. Showrunner -> Blueprint
    3. Editor -> Exact JSON Matches
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")

    print("📄 Loading episode transcripts from VideoDB...")
    transcripts = _fetch_episode_transcripts(user_state.watched_episodes, episodes)
    if not transcripts:
        raise ValueError("Could not load any episode transcripts from VideoDB")

    client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

    # The Multi-Agent Pipeline
    plot_map = _run_researcher_agent(transcripts, series_name, client)
    blueprint = _run_showrunner_agent(plot_map, user_state, characters, client)
    beat_secs = CLIP_SECONDS.get(user_state.recap_length, 9)
    editor_json = _run_editor_agent(blueprint, transcripts, beat_secs, client)

    try:
        data = json.loads(editor_json)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', editor_json, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"Editor Agent returned non-JSON: {editor_json[:300]}")

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

    moments.sort(key=lambda m: m.episode)

    print(f"\n   ✅ {len(moments)} Multi-Agent beats selected:")
    for i, m in enumerate(moments):
        diag = f'  → "{m.exact_dialogue[:50]}"' if m.exact_dialogue else "  (action beat)"
        print(f"   {i+1}. [Ep {m.episode}] [{m.mood}] {m.moment_description[:55]}...")
        print(f"      {diag}")

    return moments
