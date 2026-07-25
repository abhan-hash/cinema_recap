"""
retrieval.py — Layer 3: VideoDB Retrieval
==========================================
For each moment in the recap brief, searches the VideoDB collection
and retrieves the best matching clip.
"""

from videodb import IndexType
from models import MomentBrief, RetrievedClip
from config import get_collection, get_videodb_conn


def retrieve_clips(
    moments: list[MomentBrief],
    watched_episode_numbers: list[int],
    episode_index: dict,
) -> list[RetrievedClip]:
    """
    For each moment brief, search VideoDB collection for the best clip.
    Only considers clips from episodes the user has actually watched.

    Args:
        moments: Recap brief from the planning agent
        watched_episode_numbers: e.g. [1, 2, 3]
        episode_index: The full episode_index.json dict

    Returns:
        List of RetrievedClip objects in narrative order
    """
    coll = get_collection()
    conn = get_videodb_conn()

    # Build a lookup: video_id → episode info
    episodes = episode_index.get("episodes", {})
    video_id_to_episode = {
        ep_data["video_id"]: {"number": ep_data["number"], "title": ep_data["title"]}
        for ep_key, ep_data in episodes.items()
    }

    # Build set of video_ids for watched episodes only
    watched_video_ids = {
        episodes[str(ep_num)]["video_id"]
        for ep_num in watched_episode_numbers
        if str(ep_num) in episodes
    }

    print(f"\n🔍 Retrieving {len(moments)} clips from VideoDB...")
    print(f"   Scoped to {len(watched_video_ids)} episode(s): {sorted(watched_episode_numbers)}\n")

    clips = []
    for i, moment in enumerate(moments):
        print(f"   [{i+1}/{len(moments)}] Searching: {moment.moment_description[:70]}...")

        best_shot = None
        best_score = -1.0

        try:
            # Strategy: search the specific episode's video directly when episode is specified,
            # otherwise search collection-wide and filter.
            ep_key = str(moment.episode)
            if ep_key in episodes and moment.episode in watched_episode_numbers:
                # Direct video search — more accurate when we know the episode
                video_id = episodes[ep_key]["video_id"]
                video = coll.get_video(video_id)

                shots = []
                try:
                    res1 = video.search(query=moment.moment_description, index_type=IndexType.scene)
                    shots.extend(res1.get_shots() if hasattr(res1, 'get_shots') else getattr(res1, 'shots', []))
                except Exception:
                    pass
                try:
                    res2 = video.search(query=moment.moment_description, index_type=IndexType.spoken_word)
                    shots.extend(res2.get_shots() if hasattr(res2, 'get_shots') else getattr(res2, 'shots', []))
                except Exception:
                    pass

                for shot in shots:
                    score = getattr(shot, 'search_score', 0.5)
                    if score > best_score:
                        best_score = score
                        best_shot = shot
                        best_shot._video_id = video_id  # stash for later

            else:
                shots = []
                try:
                    res1 = coll.search(query=moment.moment_description, index_type=IndexType.scene)
                    shots.extend(res1.get_shots() if hasattr(res1, 'get_shots') else getattr(res1, 'shots', []))
                except Exception:
                    pass
                try:
                    res2 = coll.search(query=moment.moment_description, index_type=IndexType.spoken_word)
                    shots.extend(res2.get_shots() if hasattr(res2, 'get_shots') else getattr(res2, 'shots', []))
                except Exception:
                    pass

                for shot in shots:
                    vid_id = getattr(shot, 'video_id', None)
                    if vid_id not in watched_video_ids:
                        continue  # skip episodes user hasn't watched
                    score = getattr(shot, 'search_score', 0.5)
                    if score > best_score:
                        best_score = score
                        best_shot = shot
                        best_shot._video_id = vid_id

        except Exception as e:
            print(f"   ⚠️  Search error for moment {i+1}: {e}")
            continue

        if best_shot is None:
            print(f"   ⚠️  No match found for: {moment.moment_description[:50]}")
            continue

        # Build clip boundaries with buffer
        buf_before = 3.0
        clip_start = max(0.0, best_shot.start - buf_before)
        clip_end = clip_start + moment.clip_duration_seconds

        # Get episode info
        actual_video_id = getattr(best_shot, '_video_id', None) or getattr(best_shot, 'video_id', '')
        ep_info = video_id_to_episode.get(actual_video_id, {"number": moment.episode, "title": "Unknown"})

        retrieved = RetrievedClip(
            video_id=actual_video_id,
            episode_number=ep_info["number"],
            episode_title=ep_info["title"],
            start=clip_start,
            end=clip_end,
            description=getattr(best_shot, 'text', moment.moment_description),
            search_score=best_score,
            moment_description=moment.moment_description,
        )
        clips.append(retrieved)
        print(f"   ✅ Found in Ep {ep_info['number']} at {clip_start:.1f}s–{clip_end:.1f}s (score: {best_score:.2f})")

    # Sort by episode number then start time for narrative order
    clips.sort(key=lambda c: (c.episode_number, c.start))

    print(f"\n   Retrieved {len(clips)}/{len(moments)} clips successfully\n")
    return clips


def get_clip_stream_url(video_id: str, start: float, end: float) -> str:
    """
    Generate a streamable URL for a specific clip segment.
    Used by the frontend to play individual clips.
    """
    conn = get_videodb_conn()
    coll = conn.get_collection()
    video = coll.get_video(video_id)
    stream = video.generate_stream(timeline=[(start, end)])
    return stream
