"""
models.py — Pydantic request/response models
"""

from typing import Optional
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


# ─────────────────────────────────────────────
# Response: What the frontend receives
# ─────────────────────────────────────────────

class NarratedSegment(BaseModel):
    """One segment of the final recap: optional narration audio + video clip."""
    narration_text: str
    narration_audio_url: Optional[str]  # TTS audio URL for local playback
    narration_audio_id: Optional[str] = None # VideoDB Asset ID for the TTS audio
    narration_audio_length: float = 0.0
    clip: RetrievedClip


class RecapResponse(BaseModel):
    """The full personalised recap returned to the frontend."""
    user_state: UserState
    total_duration_seconds: float
    segments: list[NarratedSegment]
    compiled_stream_url: Optional[str]  # Set if Timeline compilation succeeds
    status: str  # "success" | "partial" (if some clips weren't found)
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
