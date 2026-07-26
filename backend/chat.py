"""
chat.py — Scene-aware, spoiler-safe chatbot & Interactive Scene Navigator
========================================================================
Answers viewer questions about the current recap scene using watched episode
transcripts. Identifies previous relevant setup scenes and next related follow-up
scenes within watched episodes, returning clickable scene navigation links.
"""

import json
from openai import OpenAI
from models import ChatRequest, ChatResponse, RelevantSceneNav
from config import GEMINI_API_KEY, GROQ_API_KEY, get_collection
from retrieval import search_archive


def _get_llm_client():
    """Return (client, model_name) — Gemini preferred, Groq fallback."""
    if GEMINI_API_KEY:
        return OpenAI(
            api_key=GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ), "gemini-3.1-flash-lite"
    elif GROQ_API_KEY:
        return OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        ), "llama-3.3-70b-versatile"
    else:
        raise ValueError("No LLM API key set — add GEMINI_API_KEY or GROQ_API_KEY to .env")


def _load_watched_transcripts(
    watched_episodes: list[int],
    episodes: dict,
    max_chars_per_ep: int = 20000,
) -> str:
    """
    Load transcript text for watched episodes only.
    Returns a single formatted string block for use in the system prompt.
    """
    coll = get_collection()
    block = ""
    for ep_num in sorted(watched_episodes):
        ep_key = str(ep_num)
        if ep_key not in episodes:
            continue
        vid_id = episodes[ep_key]["video_id"]
        title  = episodes[ep_key]["title"]
        try:
            video = coll.get_video(vid_id)
            text  = video.get_transcript_text() or ""
            if len(text) > max_chars_per_ep:
                half = max_chars_per_ep // 2
                text = text[:half] + "\n...[middle omitted]...\n" + text[-half:]
            block += f"\n\n=== EPISODE {ep_num}: {title} ===\n{text}"
        except Exception as e:
            print(f"  ⚠️  Chat: Could not load transcript Ep {ep_num}: {e}")
    return block


def answer_question(request: ChatRequest, episode_index: dict) -> ChatResponse:
    """
    Core chatbot logic & scene navigator:
    1. Answers viewer question grounded in watched transcripts.
    2. Identifies previous relevant setup scene and next related scene within watched episodes.
    3. Resolves timestamps via search_archive and returns ChatResponse with nav links.
    """
    client, model = _get_llm_client()

    series_name = episode_index.get("series_name", "the show")
    episodes    = episode_index.get("episodes", {})
    watched     = sorted(request.user_state.watched_episodes)
    next_ep     = request.user_state.next_episode

    # ── Current scene context ──
    scene_ctx = ""
    if request.current_clip:
        c = request.current_clip
        scene_ctx = f"""
CURRENT SCENE CONTEXT (the clip the user just paused):
  Episode:   {c.get('episode_number', '?')} — "{c.get('episode_title', '')}"
  Timestamp: {c.get('start', 0):.0f}s – {c.get('end', 0):.0f}s
  What happens: {c.get('moment_description', '')}
"""

    # ── Load transcripts ──
    transcript_block = _load_watched_transcripts(watched, episodes)

    # ── System prompt ──
    system_prompt = f"""You are an expert TV companion and Scene Navigator for "{series_name}".
Your role is to help the viewer understand and enjoy what they've already watched — clearly, engagingly, and without spoilers.

━━━ SPOILER RULES — STRICTLY ENFORCE THESE ━━━
• The viewer has ONLY watched Episodes: {watched}
• They are about to watch Episode {next_ep} for the FIRST TIME
• You MUST NOT reveal, hint at, or allude to ANYTHING from Episode {next_ep} onwards
• Do NOT say things like "in a later episode", "eventually", "by the end of the series" — these imply spoilers
• If asked about something from a future episode, set reply to: "That's ahead — no spoilers! Ask me about what you've already seen 😊" and leave prev_scene/next_scene null.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{scene_ctx}
WHAT YOU KNOW — TRANSCRIPTS OF WATCHED EPISODES:
{transcript_block}

YOU MUST RESPOND ONLY WITH A VALID JSON OBJECT matching this exact structure:
{{
  "reply": "Your 2-4 sentence explanation answering the user's question.",
  "prev_scene_query": "A short 3-6 word search quote/phrase to locate the earlier setup/cause scene in watched episodes (or null if none)",
  "prev_scene_reason": "Short 1-line explanation of why this earlier scene is relevant",
  "prev_scene_episode": 1,
  "next_scene_query": "A short 3-6 word search quote/phrase to locate the follow-up/effect scene in watched episodes (or null if none)",
  "next_scene_reason": "Short 1-line explanation of why this follow-up scene is relevant",
  "next_scene_episode": 2
}}

CRITICAL: Both prev_scene_episode and next_scene_episode MUST be from watched episodes {watched}. Do NOT suggest scenes from Episode {next_ep} or later."""

    # ── Build message list ──
    messages = [{"role": "system", "content": system_prompt}]

    for msg in request.history[-12:]:
        messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": request.message})

    raw_reply = ""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.4,
            max_tokens=800,
            response_format={"type": "json_object"} if "gemini" in model.lower() else None,
        )
        raw_reply = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Chat completion error: {e}")
        return ChatResponse(reply="Sorry, I ran into an error processing your question.")

    # Parse JSON output from LLM
    try:
        cleaned = raw_reply
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        data = json.loads(cleaned, strict=False)
    except Exception:
        return ChatResponse(reply=raw_reply)

    reply_text = data.get("reply", raw_reply)

    # ── Resolve prev_scene navigation clip ──
    prev_nav = None
    p_query = data.get("prev_scene_query")
    p_reason = data.get("prev_scene_reason")
    p_ep = data.get("prev_scene_episode")
    if p_query and p_query != "null":
        hits = search_archive(query=p_query, index_type="all", episode_index=episode_index, episode_number=p_ep)
        if hits:
            h = hits[0]
            prev_nav = RelevantSceneNav(
                label=f"Ep {h['episode_number']}: {h['episode_title']}",
                direction="previous",
                reason=p_reason or "Earlier setup scene",
                episode_number=h['episode_number'],
                episode_title=h['episode_title'],
                video_id=h['video_id'],
                start=h['start'],
                end=h['end'],
            )

    # ── Resolve next_scene navigation clip ──
    next_nav = None
    n_query = data.get("next_scene_query")
    n_reason = data.get("next_scene_reason")
    n_ep = data.get("next_scene_episode")
    if n_query and n_query != "null" and n_ep in watched:
        hits = search_archive(query=n_query, index_type="all", episode_index=episode_index, episode_number=n_ep)
        if hits:
            h = hits[0]
            next_nav = RelevantSceneNav(
                label=f"Ep {h['episode_number']}: {h['episode_title']}",
                direction="next",
                reason=n_reason or "Follow-up scene",
                episode_number=h['episode_number'],
                episode_title=h['episode_title'],
                video_id=h['video_id'],
                start=h['start'],
                end=h['end'],
            )

    return ChatResponse(reply=reply_text, prev_scene=prev_nav, next_scene=next_nav)
