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
from config import GROQ_API_KEY, GEMINI_API_KEY, get_collection

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


# Total character budget across all episodes to stay within token limits.
# Gemini Flash: 1M token context — very generous. Groq fallback: ~10k tokens.
# At ~4 chars/token: 200k chars ≈ 50k tokens — well within Gemini's free tier.
TOTAL_TRANSCRIPT_BUDGET = 200_000
GROQ_TRANSCRIPT_BUDGET  = 10_000  # chars total when falling back to Groq


def _fetch_episode_transcripts(
    watched_episode_numbers: list[int],
    episodes: dict,
    max_chars_per_ep: int = 25000,
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

    # Determine character focus and custom directives
    active_chars = []
    if user_state.focus_characters:
        active_chars = user_state.focus_characters
    elif user_state.focus_character:
        active_chars = [c.strip() for c in user_state.focus_character.split(',') if c.strip()]

    custom_directive = ""
    if user_state.custom_prompt:
        custom_directive = (
            f"🎯 HIGH-PRIORITY CUSTOM DIRECTIVE: The user explicitly requested: \"{user_state.custom_prompt}\".\n"
            f"Every single moment in your recap plan MUST directly serve, illustrate, or feature this specific topic/theme.\n\n"
        )

    if active_chars:
        chars_str = " & ".join(active_chars)
        focus_line = (
            f"{custom_directive}"
            f"CRITICAL INSTRUCTION: The user specifically wants a recap merging the storylines of {chars_str}.\n"
            f"You MUST make {chars_str} the absolute priority. Focus on their shared interactions, key individual turning points, "
            f"and the intersection of their character arcs. Do not include unrelated B-rolls or other plotlines."
        )
        showrunner_rules = f"""- NARRATIVE FOCUS: {chars_str}'s combined storylines are the absolute priority. Do not include unrelated beats.
- SEQUENCE: Chronologically build {chars_str}'s journey — setup → rising stakes → shared conflicts / cliffhangers.
- PACING: Do not waste beats on generic B-roll unless relevant to {chars_str}.
- TENSION: Prefer moments for {chars_str} that set up UNRESOLVED tension going into Episode {user_state.next_episode}."""
    elif user_state.custom_prompt:
        focus_line = (
            f"{custom_directive}"
            f"CRITICAL INSTRUCTION: Focus 100% of the recap beats on the user's topic: \"{user_state.custom_prompt}\"."
        )
        showrunner_rules = f"""- NARRATIVE FOCUS: Every beat MUST directly illustrate "{user_state.custom_prompt}".
- SEQUENCE: Chronologically sequence beats to tell a coherent story around this theme.
- TENSION: Prefer moments that set up UNRESOLVED tension going into Episode {user_state.next_episode}."""
    else:
        focus_line = "Balance beats across the main story threads."
        showrunner_rules = f"""- NARRATIVE FOCUS: Identify the "A-Plot" and "B-Plot" from the transcripts and weave them chronologically.
- PACING & RHYTHM (B-ROLL): Inject at least 1-2 "B-roll" action shots (e.g. scenic transitions, silent reactions, driving) between heavy dialogue scenes to let the recap breathe. For these, `exact_dialogue` MUST be null.
- Sequence beats to BUILD — setup → rising stakes → biggest shock/cliffhanger.
- Prefer moments that set up UNRESOLVED tension going into Episode {user_state.next_episode}."""

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

Pick EXACTLY {n_beats} beats for the recap. Think like a MASTER SHOWRUNNER:
{showrunner_rules}

For EACH beat, provide:
- `moment_description`: What is happening visually (keep to 1 sentence)
- `exact_dialogue`: The EXACT line of dialogue from the transcript above that anchors this moment. MUST be verbatim. If it's a B-Roll/action beat, set to null.
- `episode`: episode number (integer)
- `clip_duration_seconds`: seconds this beat needs ({beat_secs-2}–{beat_secs+4}s range).
- `mood`: one of: tense | dramatic | calm | action | sad
- `importance`: one of: critical | important | context | b-roll

Return ONLY valid JSON — no markdown, no code fences. VERY IMPORTANT: You must properly escape any double quotes inside string values (e.g., use \\" for inner quotes):
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

    # Build provider list — Gemini first (1M token context, generous free tier),
    # fall back to Groq if Gemini key not set or fails.
    providers = []
    if GEMINI_API_KEY:
        gemini_client = OpenAI(
            api_key=GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        for gm in ["gemini-3.1-flash-lite", "gemini-2.0-flash"]:
            providers.append({
                "name": gm,
                "client": gemini_client,
                "model": gm,
                "max_tokens": 2048,
            })
    if GROQ_API_KEY:
        for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
            providers.append({
                "name": m,
                "client": OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1"),
                "model": m,
                "max_tokens": 800,
            })

    if not providers:
        raise ValueError("No API keys set — add GEMINI_API_KEY or GROQ_API_KEY to .env")

    raw = None
    last_err = None
    for p in providers:
        try:
            print(f"   🤖 Trying {p['name']}...")
            # Shrink transcript budget when falling back to Groq
            if "llama" in p["name"] and len(prompt) > GROQ_TRANSCRIPT_BUDGET:
                print(f"   ⚠️  Prompt too large for {p['name']} ({len(prompt)} chars) — skipping")
                continue
            response = p["client"].chat.completions.create(
                model=p["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=p["max_tokens"],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content.strip()
            print(f"   ✅ Response: {len(raw)} chars (via {p['name']})")
            break
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if any(code in err_str for code in ["rate_limit", "429", "413", "quota"]):
                print(f"   ⚠️  {p['name']} rate limited — trying next provider")
                continue
            raise e

    if raw is None:
        raise RuntimeError(f"All providers failed. Last error: {last_err}")

    # Strip markdown fences
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE).strip()

    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group(), strict=False)
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
