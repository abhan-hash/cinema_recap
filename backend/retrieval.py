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
