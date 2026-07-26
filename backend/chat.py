"""
chat.py — Scene-aware, spoiler-safe chatbot
=============================================
Answers viewer questions about the current recap scene using the actual
episode transcripts as ground truth. Enforces a strict spoiler guardrail
so it NEVER reveals anything from episodes the user hasn't watched yet.
"""

from openai import OpenAI
from models import ChatRequest
from config import GEMINI_API_KEY, GROQ_API_KEY, get_collection


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
                # Sample beginning + end so LLM sees full arc
                half = max_chars_per_ep // 2
                text = text[:half] + "\n...[middle omitted]...\n" + text[-half:]
            block += f"\n\n=== EPISODE {ep_num}: {title} ===\n{text}"
        except Exception as e:
            print(f"  ⚠️  Chat: Could not load transcript Ep {ep_num}: {e}")
    return block


def answer_question(request: ChatRequest, episode_index: dict) -> str:
    """
    Core chatbot logic:
    1. Build a spoiler-guarded system prompt with real transcript context
    2. Send the full conversation history to the LLM
    3. Return the reply
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
    system_prompt = f"""You are an expert TV companion for "{series_name}". Your role is to help the viewer \
understand and enjoy what they've already watched — clearly, engagingly, and without spoilers.

━━━ SPOILER RULES — STRICTLY ENFORCE THESE ━━━
• The viewer has ONLY watched Episodes: {watched}
• They are about to watch Episode {next_ep} for the FIRST TIME
• You MUST NOT reveal, hint at, or allude to ANYTHING from Episode {next_ep} onwards
• Do NOT say things like "in a later episode", "eventually", "by the end of the series" — these imply spoilers
• If asked about something from a future episode, respond ONLY with:
  "That's ahead — no spoilers! Ask me about what you've already seen 😊"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{scene_ctx}
WHAT YOU KNOW — TRANSCRIPTS OF WATCHED EPISODES:
{transcript_block}

Answer in 2-5 sentences. Be warm, insightful, and grounded in the transcripts above. \
If something isn't clear from the transcripts, say so honestly rather than guessing."""

    # ── Build message list ──
    messages = [{"role": "system", "content": system_prompt}]

    # Include conversation history (last 12 turns to stay within context)
    for msg in request.history[-12:]:
        messages.append({"role": msg.role, "content": msg.content})

    # Add the new user message
    messages.append({"role": "user", "content": request.message})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.6,
        max_tokens=600,
    )

    return response.choices[0].message.content.strip()
