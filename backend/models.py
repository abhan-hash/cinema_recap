"""
models.py — Pydantic request/response models
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Request: What the user submits from the frontend
# ─────────────────────────────────────────────

class UserState(BaseModel):
    """The viewer's watch state — drives all personalisation."""
    watched_episodes: list[int] = Field(
        ...,
        description="Episode numbers the user has watched, e.g. [1, 2, 3]"
    )
    next_episode: int = Field(
        ...,
        description="The episode they're about to watch"
    )
    time_since_last_watch: str = Field(
        ...,
        description="How long ago they last watched: 'last_night', 'last_week', 'last_month', '6_months_ago'"
    )
    focus_character: Optional[str] = Field(
        None,
        description="Optional character they want the recap focused on, e.g. 'the Tramp'"
    )
    recap_length: str = Field(
        "medium",
        description="Desired recap length: 'short' (30s), 'medium' (90s), 'long' (3min)"
    )


# ─────────────────────────────────────────────
# Internal: Recap planning agent output
# ─────────────────────────────────────────────

class MomentBrief(BaseModel):
    """A single moment the LLM agent wants to retrieve from the archive."""
    moment_description: str
    episode: int
    importance: str  # "critical" | "important" | "context"
    characters_involved: list[str]
    clip_duration_seconds: int  # tight window around the key moment
    mood: str = "tense"  # "tense" | "dramatic" | "calm" | "action" | "sad"
    exact_dialogue: Optional[str] = None  # Exact dialogue quote to help VideoDB search find the exact scene


# ─────────────────────────────────────────────
# Internal: A retrieved clip from VideoDB
# ─────────────────────────────────────────────

class RetrievedClip(BaseModel):
    """A clip returned by VideoDB search, ready for assembly."""
    video_id: str
    episode_number: int
    episode_title: str
    start: float
    end: float
    description: str       # shot.text from VideoDB
    search_score: float
    moment_description: str
    mood: str = "tense"   # carries mood through to the frontend
    dialogue_text: Optional[str] = None  # Verbatim spoken dialogue subtitle


# ─────────────────────────────────────────────
# Response: What the frontend receives
# ─────────────────────────────────────────────

class NarratedSegment(BaseModel):
    """One recap segment: a contextual caption + the video clip."""
    narration_text: str          # Short caption shown as hover overlay
    narration_audio_url: Optional[str] = None  # Always None now — no per-clip audio
    clip: RetrievedClip


class RecapResponse(BaseModel):
    """The full personalised recap returned to the frontend."""
    user_state: UserState
    total_duration_seconds: float
    segments: list[NarratedSegment]
    compiled_stream_url: Optional[str]  # Set if Timeline compilation succeeds
    previously_on_audio_url: Optional[str] = None  # Character-voiced "Previously on..." intro
    status: str  # "success" | "partial"
    message: str


# ─────────────────────────────────────────────
# Response: Series info (for the frontend's series selector)
# ─────────────────────────────────────────────

class EpisodeInfo(BaseModel):
    number: int
    title: str
    video_id: str

class SeriesInfo(BaseModel):
    series_name: str
    characters: list[str]
    episodes: list[EpisodeInfo]


# ─────────────────────────────────────────────
# Chatbot: Scene-aware, spoiler-safe Q&A
# ─────────────────────────────────────────────

class ChatMessage(BaseModel):
    """A single message in a chat conversation."""
    role: str    # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    """Chat request sent from the frontend."""
    message: str
    history: list[ChatMessage] = []
    current_clip: Optional[dict[str, Any]] = None   # RetrievedClip fields as dict
    user_state: UserState

class RelevantSceneNav(BaseModel):
    """Navigational link to a relevant scene in the show."""
    label: str
    direction: str          # "previous" | "next"
    reason: str
    episode_number: int
    episode_title: str
    video_id: str
    start: float
    end: float

class ChatResponse(BaseModel):
    reply: str
    prev_scene: Optional[RelevantSceneNav] = None
    next_scene: Optional[RelevantSceneNav] = None
