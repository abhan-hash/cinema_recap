"""
retrieval.py — Layer 3: VideoDB Retrieval
==========================================
Uses transcript-level word timestamps for frame-accurate clip retrieval.
Falls back to semantic search only when transcript matching fails.
"""

import re
from difflib import SequenceMatcher
from videodb import IndexType
from models import MomentBrief, RetrievedClip
from config import get_collection, get_videodb_conn


def _build_sentences(transcript: list[dict]) -> list[dict]:
    """
    Group word-level transcript tokens into dialogue sentences with timestamps.
    Returns: [{'start': float, 'end': float, 'text': str}, ...]
    """
    sentences = []
    current = []

    for t in transcript:
        word = t.get('text', '').strip()
        if not word or word == '-':
            if current:
                start = current[0]['start']
                end   = current[-1]['end']
                text  = ' '.join(c['text'] for c in current).strip()
                if text:
                    sentences.append({'start': start, 'end': end, 'text': text})
                current = []
        else:
            current.append(t)

    if current:
        start = current[0]['start']
        end   = current[-1]['end']
        text  = ' '.join(c['text'] for c in current).strip()
        if text:
            sentences.append({'start': start, 'end': end, 'text': text})

    return sentences


def _fuzzy_score(a: str, b: str) -> float:
    """Fuzzy similarity ratio between two strings (0-1)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _search_transcript(sentences: list[dict], query: str, top_n: int = 5) -> list[dict]:
    """
    Fuzzy search the transcript sentences for the best match to query.
    Returns top_n results with a 'score' field.
    """
    scored = []
    q_lower = query.lower()
    q_words = set(re.findall(r'\w+', q_lower))

    for s in sentences:
        text_lower = s['text'].lower()
        t_words = set(re.findall(r'\w+', text_lower))

        # Combine word overlap with fuzzy string ratio
        overlap = len(q_words & t_words) / max(len(q_words), 1)
        ratio   = _fuzzy_score(q_lower, text_lower)
        score   = 0.6 * ratio + 0.4 * overlap

        scored.append({**s, 'score': score})

    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:top_n]


def _get_video_transcript_sentences(video_id: str) -> list[dict]:
    """Fetch and parse transcript for a video, cached in memory per call."""
    coll = get_collection()
    video = coll.get_video(video_id)
    try:
        transcript = video.get_transcript()
        return _build_sentences(transcript)
    except Exception as e:
        print(f"   ⚠️  Transcript unavailable for {video_id}: {e}")
        return []


def retrieve_clips(
    moments: list[MomentBrief],
    watched_episode_numbers: list[int],
    episode_index: dict,
) -> list[RetrievedClip]:
    """
    For each moment brief, find the best matching clip using transcript search.
    Primary: exact/fuzzy dialogue matching against word-level timestamps.
    Fallback: VideoDB semantic search (for action-only beats with no dialogue).
    """
    coll = get_collection()

    # Build lookups
    episodes = episode_index.get("episodes", {})
    video_id_to_episode = {
        ep_data["video_id"]: {"number": ep_data["number"], "title": ep_data["title"]}
        for ep_key, ep_data in episodes.items()
    }
    watched_video_ids = {
        episodes[str(ep_num)]["video_id"]
        for ep_num in watched_episode_numbers
        if str(ep_num) in episodes
    }

    print(f"\n🔍 Retrieving {len(moments)} clips using transcript-precision search...")
    print(f"   Episodes in scope: {sorted(watched_episode_numbers)}\n")

    # Pre-load transcripts for watched episodes
    transcript_map: dict[str, list[dict]] = {}
    for ep_num in watched_episode_numbers:
        ep_key = str(ep_num)
        if ep_key in episodes:
            vid_id = episodes[ep_key]["video_id"]
            print(f"   Loading transcript for Ep {ep_num}...")
            transcript_map[vid_id] = _get_video_transcript_sentences(vid_id)
            print(f"   ✅ {len(transcript_map[vid_id])} dialogue lines indexed")

    clips = []
    for i, moment in enumerate(moments):
        print(f"\n   [{i+1}/{len(moments)}] Beat: {moment.moment_description[:70]}...")
        if moment.exact_dialogue:
            print(f"   🎯 Exact dialogue: '{moment.exact_dialogue[:60]}'")

        best_match = None
        best_score = -1.0
        best_video_id = None

        # Determine which videos to search
        ep_key = str(moment.episode)
        if ep_key in episodes and moment.episode in watched_episode_numbers:
            target_vids = [episodes[ep_key]["video_id"]]
        else:
            target_vids = list(watched_video_ids)

        # ── STRATEGY 1: Transcript fuzzy search ──
        for vid_id in target_vids:
            sentences = transcript_map.get(vid_id, [])
            if not sentences:
                continue

            # If we have exact dialogue, search that first and give it priority
            if moment.exact_dialogue:
                results = _search_transcript(sentences, moment.exact_dialogue)
                for r in results[:3]:
                    score = r['score'] * 2.0  # Heavy boost for dialogue hit
                    if score > best_score:
                        best_score = score
                        best_match = r
                        best_video_id = vid_id

            # Also search by the descriptive moment text
            results = _search_transcript(sentences, moment.moment_description)
            for r in results[:3]:
                if r['score'] > best_score:
                    best_score = r['score']
                    best_match = r
                    best_video_id = vid_id

        # ── STRATEGY 2: Semantic fallback (for pure action beats) ──
        if best_match is None or best_score < 0.15:
            print(f"   🔁 Low transcript score ({best_score:.2f}), trying semantic fallback...")
            try:
                for vid_id in target_vids:
                    video = coll.get_video(vid_id)
                    query = moment.exact_dialogue or moment.moment_description
                    try:
                        res = video.search(query=query, index_type=IndexType.spoken_word)
                        shots = res.get_shots() if hasattr(res, 'get_shots') else getattr(res, 'shots', [])
                        for shot in shots:
                            score = float(getattr(shot, 'search_score', 0.3))
                            if score > best_score:
                                best_score = score
                                best_video_id = vid_id
                                # Map shot to match format
                                best_match = {
                                    'start': float(shot.start),
                                    'end': float(shot.end),
                                    'text': str(getattr(shot, 'text', '')),
                                    'score': score,
                                    '_is_semantic': True,
                                }
                    except Exception:
                        pass
            except Exception as e:
                print(f"   ⚠️  Semantic fallback error: {e}")

        if best_match is None:
            print(f"   ⚠️  No match found for beat {i+1}")
            continue

        # ── Build clip window centred on the match ──
        match_start = float(best_match['start'])
        match_end   = float(best_match['end'])
        match_mid   = (match_start + match_end) / 2.0
        half        = moment.clip_duration_seconds / 2.0

        clip_start = max(0.0, match_mid - half)
        clip_end   = match_mid + half

        ep_info = video_id_to_episode.get(best_video_id, {
            "number": moment.episode, "title": "Unknown"
        })

        strategy = "semantic" if best_match.get('_is_semantic') else "transcript"
        print(f"   ✅ [{strategy}] Ep {ep_info['number']} "
              f"{clip_start:.1f}s–{clip_end:.1f}s  "
              f"score={best_score:.3f}  "
              f"text='{best_match['text'][:60]}'")

        clips.append(RetrievedClip(
            video_id=best_video_id,
            episode_number=ep_info["number"],
            episode_title=ep_info["title"],
            start=clip_start,
            end=clip_end,
            description=best_match['text'],
            search_score=min(best_score, 1.0),
            moment_description=moment.moment_description,
            mood=moment.mood,
        ))

    # Sort by episode then timestamp for narrative order
    clips.sort(key=lambda c: (c.episode_number, c.start))

    print(f"\n   Retrieved {len(clips)}/{len(moments)} clips\n")
    return clips


def get_clip_stream_url(video_id: str, start: float, end: float) -> str:
    """Generate a streamable URL for a specific clip segment."""
    coll = get_videodb_conn().get_collection()
    video = coll.get_video(video_id)
    return video.generate_stream(timeline=[(start, end)])


# ─────────────────────────────────────────────
# Senior Director QA Pass
# ─────────────────────────────────────────────

def _snap_to_sentence_boundaries(
    start: float,
    end: float,
    sentences: list[dict],
    snap_window: float = 4.0,
) -> tuple[float, float]:
    """
    Expand clip boundaries so we never start or end mid-dialogue.
    - If clip_start lands inside a sentence, pull it back to that sentence's start.
    - If clip_end   lands inside a sentence, push it forward to that sentence's end.
    Only snaps if the adjustment is within `snap_window` seconds.
    """
    new_start = start
    new_end   = end

    for sent in sentences:
        s, e = sent['start'], sent['end']

        # Start snapping: clip starts mid-sentence?
        if s < start and e > start and (start - s) <= snap_window:
            new_start = min(new_start, s)

        # End snapping: clip ends mid-sentence?
        if s < end and e > end and (e - end) <= snap_window:
            new_end = max(new_end, e)

    return new_start, new_end


def qa_and_refine_clips(
    clips: list[RetrievedClip],
    episode_index: dict,
    groq_api_key: str | None = None,
) -> list[RetrievedClip]:
    """
    Senior Director QA pass — two stages:

    Stage 1 (automatic): Fix transcript boundary issues.
      - Never cut a line of dialogue mid-sentence.
      - Ensure minimum 5s and maximum 16s per clip.

    Stage 2 (LLM): Holistic sequence review.
      - LLM gets the full transcript excerpt for every clip.
      - Flags: too short, too long, dialogue cut, wrong scene.
      - Outputs adjustments (extend/trim/drop) per clip index.
    """
    coll = get_collection()
    episodes = episode_index.get("episodes", {})

    # Build transcript map for each unique video
    video_transcript_map: dict[str, list[dict]] = {}
    unique_video_ids = {c.video_id for c in clips}
    for vid_id in unique_video_ids:
        sentences = _get_video_transcript_sentences(vid_id)
        video_transcript_map[vid_id] = sentences

    # ── Stage 1: Auto boundary fix ──
    print("\n🎬 Director QA — Stage 1: Fixing dialogue boundaries...")
    stage1_clips: list[RetrievedClip] = []
    for i, clip in enumerate(clips):
        sentences = video_transcript_map.get(clip.video_id, [])
        raw_start, raw_end = clip.start, clip.end

        snapped_start, snapped_end = _snap_to_sentence_boundaries(
            raw_start, raw_end, sentences, snap_window=5.0
        )

        # Enforce min/max duration
        duration = snapped_end - snapped_start
        if duration < 5.0:
            # Extend symmetrically to at least 5s
            pad = (5.0 - duration) / 2
            snapped_start = max(0.0, snapped_start - pad)
            snapped_end   = snapped_start + 5.0
        elif duration > 16.0:
            # Trim: keep the centre of the clip
            mid = (snapped_start + snapped_end) / 2
            snapped_start = mid - 8.0
            snapped_end   = mid + 8.0

        if snapped_start != raw_start or snapped_end != raw_end:
            print(f"   [{i+1}] Adjusted {raw_start:.1f}–{raw_end:.1f}s → {snapped_start:.1f}–{snapped_end:.1f}s")

        stage1_clips.append(clip.model_copy(update={
            'start': max(0.0, snapped_start),
            'end':   snapped_end,
        }))

    if not groq_api_key:
        print("   ⚠️  Skipping Stage 2 (no GROQ_API_KEY)")
        return stage1_clips

    # ── Stage 2: LLM holistic review ──
    print("\n🎬 Director QA — Stage 2: LLM sequence review...")

    # Build a rich context for the LLM: for each clip, show the actual dialogue it covers
    clip_summaries = []
    for i, clip in enumerate(stage1_clips):
        sentences = video_transcript_map.get(clip.video_id, [])
        # Grab sentences that fall within this clip's window
        in_clip = [
            s['text'] for s in sentences
            if s['end'] >= clip.start and s['start'] <= clip.end
        ]
        dialogue_excerpt = " ".join(in_clip)[:300] or "(no dialogue — action beat)"
        clip_summaries.append(
            f"[{i+1}] Ep{clip.episode_number} {clip.start:.1f}s–{clip.end:.1f}s "
            f"({clip.end - clip.start:.1f}s) mood={clip.mood}\n"
            f"    Dialogue: \"{dialogue_excerpt}\"\n"
            f"    Intent: {clip.moment_description}"
        )

    prompt = """You are a senior TV editor doing a final QA pass on a recap sequence.
Review these NUM_CLIPS clips and flag any that need adjustment.

CLIP_SUMMARIES

For each clip that has a problem, output an adjustment. Problems to look for:
- Dialogue appears cut mid-sentence at the start or end (the dialogue excerpt starts/ends abruptly mid-thought)
- Clip is under 5s or over 14s (check the duration shown)
- The clip's dialogue doesn't match its stated intent at all (wrong scene)
- Duplicate scene (same dialogue/scene as another clip in the list)

If a clip needs adjustment output it. If a clip is fine, do NOT include it.
Only output clips that genuinely need fixing. If everything looks good, you MUST STILL return valid JSON with an empty array: {"adjustments": []}.

Return ONLY valid JSON:
{"adjustments": [
  {"index": 0, "action": "extend_start", "seconds": 2.5, "reason": "dialogue cut at beginning"},
  {"index": 2, "action": "extend_end",   "seconds": 1.5, "reason": "line incomplete at end"},
  {"index": 4, "action": "drop",         "reason": "duplicates clip 3"},
  {"index": 5, "action": "trim",         "new_start": 1200.0, "new_end": 1210.0, "reason": "wrong scene entirely"}
]}

Actions available: extend_start, extend_end, drop, trim"""
    prompt = prompt.replace("NUM_CLIPS", str(len(stage1_clips)))
    prompt = prompt.replace("CLIP_SUMMARIES", chr(10).join(clip_summaries))

    try:
        import json, re
        from openai import OpenAI
        client = OpenAI(api_key=groq_api_key, base_url="https://api.groq.com/openai/v1")
        models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
        raw = None
        last_err = None
        for model in models:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=400,
                )
                raw = response.choices[0].message.content.strip()
                break
            except Exception as e:
                last_err = e
                if "rate_limit" in str(e).lower() or "429" in str(e):
                    continue
                raise e
        
        if raw is None:
            raise RuntimeError(f"All QA models failed or rate limited. Last error: {last_err}")
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
        adjustments = data.get("adjustments", [])
        print(f"   LLM flagged {len(adjustments)} issues")
    except Exception as e:
        print(f"   ⚠️  LLM review failed: {e} — keeping Stage 1 results")
        return stage1_clips

    # Apply adjustments
    drop_indices = set()
    final_clips = list(stage1_clips)

    for adj in adjustments:
        idx = adj.get("index")
        if idx is None or idx >= len(final_clips):
            continue
        action = adj.get("action", "")
        clip   = final_clips[idx]
        reason = adj.get("reason", "")

        if action == "drop":
            drop_indices.add(idx)
            print(f"   [{idx+1}] DROP — {reason}")

        elif action == "extend_start":
            secs = float(adj.get("seconds", 2.0))
            new_start = max(0.0, clip.start - secs)
            final_clips[idx] = clip.model_copy(update={'start': new_start})
            print(f"   [{idx+1}] EXTEND_START by {secs}s → {new_start:.1f}s — {reason}")

        elif action == "extend_end":
            secs = float(adj.get("seconds", 2.0))
            new_end = clip.end + secs
            final_clips[idx] = clip.model_copy(update={'end': new_end})
            print(f"   [{idx+1}] EXTEND_END by {secs}s → {new_end:.1f}s — {reason}")

        elif action == "trim":
            new_start = float(adj.get("new_start", clip.start))
            new_end   = float(adj.get("new_end",   clip.end))
            final_clips[idx] = clip.model_copy(update={'start': new_start, 'end': new_end})
            print(f"   [{idx+1}] TRIM → {new_start:.1f}–{new_end:.1f}s — {reason}")

    result = [c for i, c in enumerate(final_clips) if i not in drop_indices]
    print(f"   ✅ QA complete: {len(result)} clips after review (dropped {len(drop_indices)})\n")
    return result

