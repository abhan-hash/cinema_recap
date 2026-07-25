"""
agent.py — Layer 2: Recap Planning Agent
=========================================
Uses Google Gemini (free tier) to produce a structured recap brief.
"""

import json
import re
from openai import OpenAI
from models import UserState, MomentBrief
from config import GROQ_API_KEY

# Clip durations by importance
CLIP_DURATIONS = {
    "critical": 40,
    "important": 25,
    "context": 15,
}

# Moment count targets by time-since-last-watch
MOMENT_COUNTS = {
    "last_night": 3,
    "last_week":  5,
    "last_month": 7,
    "6_months_ago": 8,
}

def _build_prompt(user_state: UserState, series_name: str, characters: list[str], episodes: dict) -> str:
    watched_info = []
    for ep_num in sorted(user_state.watched_episodes):
        ep_key = str(ep_num)
        if ep_key in episodes:
            watched_info.append(f"  - Episode {ep_num}: {episodes[ep_key]['title']}")

    moment_count = MOMENT_COUNTS.get(user_state.time_since_last_watch, 5)
    focus_line = (
        f"The viewer has specifically asked to focus on: {user_state.focus_character}."
        if user_state.focus_character
        else "No specific character focus — balance across the main story."
    )

    recap_length_guidance = {
        "short": "Keep it to 3-4 moments maximum. Only truly critical plot points.",
        "medium": "Use 5-7 moments. Cover main plot threads and key character beats.",
        "long": "Use 7-9 moments. Fuller context including subplots.",
    }.get(user_state.recap_length, "Use 5-7 moments.")

    return f"""You are a TV recap writer for the series "{series_name}".

The viewer has watched these episodes:
{chr(10).join(watched_info)}

They last watched {user_state.time_since_last_watch.replace('_', ' ')}.
They are about to watch Episode {user_state.next_episode}.
{focus_line}

Known characters in this series: {', '.join(characters)}

Your task: Identify exactly {moment_count} specific scenes/moments from the episodes they watched that are ESSENTIAL context for watching Episode {user_state.next_episode}.

{recap_length_guidance}

Prioritize:
1. Unresolved plot threads going into the next episode
2. Character relationships and their current state
3. The most recent dramatic turning point
4. Any cliffhangers or mysteries introduced
{"5. Moments specifically involving: " + user_state.focus_character if user_state.focus_character else ""}

For each moment, write a SPECIFIC, SEARCHABLE description that could find the exact scene in a video archive.
Good: "Walter poisons Brock with berries in the backyard"
Bad: "An important moment happens"

Return ONLY valid JSON — no markdown, no code fences, no explanation:
{{"moments": [{{"moment_description": "specific description", "episode": 1, "importance": "critical", "characters_involved": ["Name1"]}}]}}

importance must be one of: critical, important, context
"""


def plan_recap(user_state: UserState, series_name: str, characters: list[str], episodes: dict) -> list[MomentBrief]:
    """Call Groq to generate the recap brief."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set in .env — get one free at https://console.groq.com/keys")

    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )

    prompt = _build_prompt(user_state, series_name, characters, episodes)

    print("🤖 Calling Groq for recap planning...")
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    raw = response.choices[0].message.content.strip()
    print(f"   Groq response received ({len(raw)} chars)")

    # Strip markdown fences if Groq wrapped it anyway
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting JSON object
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"Groq returned non-JSON output: {raw[:300]}")

    moments = []
    for m in data.get("moments", []):
        importance = m.get("importance", "important")
        brief = MomentBrief(
            moment_description=m["moment_description"],
            episode=int(m["episode"]),
            importance=importance,
            characters_involved=m.get("characters_involved", []),
            clip_duration_seconds=CLIP_DURATIONS.get(importance, 25),
        )
        moments.append(brief)

    # Sort by episode for narrative order
    moments.sort(key=lambda m: m.episode)

    print(f"   ✅ Generated {len(moments)} moments to retrieve")
    for i, m in enumerate(moments):
        print(f"   {i+1}. [Ep {m.episode}] [{m.importance}] {m.moment_description[:70]}...")

    return moments
