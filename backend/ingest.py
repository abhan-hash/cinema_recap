"""
Layer 0: Ingestion Script
=========================
Run this ONCE before the demo to upload and index all episodes into VideoDB.

Usage:
    python ingest.py

What it does:
1. Uploads each episode video to VideoDB
2. Indexes spoken words (transcription + semantic search)
3. Indexes scenes with a character-aware prompt
4. Saves the episode → video_id mapping to data/episode_index.json

IMPORTANT: Fill in EPISODES list below with your actual episode URLs/file paths.
"""

import os
import json
import time
import subprocess
import urllib.request
import videodb
from videodb import SceneExtractionType
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# ─────────────────────────────────────────────
# CONFIGURE YOUR SERIES HERE
# ─────────────────────────────────────────────

SERIES_NAME = "Breaking Bad"  

# Each episode: number, title, and a URL or local file path.
EPISODES = [
    {
        "number": 1,
        "title": "Pilot",
        "url": "", # We'll rely on local ep1.mp4
    },
    {
        "number": 2,
        "title": "Cat's in the Bag...",
        "url": "", # We'll rely on local ep2.mp4
    },
    {
        "number": 3,
        "title": "And the Bag's in the River",
        "url": "", # We'll rely on local ep3.mp4
    }
]

# Character names in your series — used in the scene indexing prompt
CHARACTERS = [
    "Walter White",
    "Jesse Pinkman",
    "Skyler White",
    "Hank Schrader",
    "Marie Schrader",
    "Walter Jr."
]

# ─────────────────────────────────────────────
# INDEXING PROMPTS
# ─────────────────────────────────────────────

SCENE_INDEX_PROMPT = f"""
Analyze this scene from the series "{SERIES_NAME}".
Describe:
1. Which characters are present ({', '.join(CHARACTERS)})
2. What dramatic or plot-critical action is happening
3. The emotional tone (tense, funny, sad, shocking, romantic)
4. Any key objects or locations that matter to the story
Be specific and detailed — this will be used to find exact moments later.
"""

# ─────────────────────────────────────────────
# INGESTION LOGIC
# ─────────────────────────────────────────────

def main():
    print("🎬 RecapAI Ingestion Script")
    print(f"   Series: {SERIES_NAME}")
    print(f"   Episodes to ingest: {len(EPISODES)}\n")

    # Connect to VideoDB
    api_key = os.environ.get("VIDEODB_API_KEY")
    if not api_key:
        raise ValueError("VIDEODB_API_KEY not set in .env file")

    conn = videodb.connect(api_key=api_key)
    coll = conn.get_collection()
    print(f"✅ Connected to VideoDB — collection: {coll.id}\n")

    # Load existing index if partial ingestion already happened
    index_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'episode_index.json')
    if os.path.exists(index_path):
        with open(index_path) as f:
            episode_index = json.load(f)
        print(f"📂 Loaded existing episode index ({len(episode_index['episodes'])} episodes already done)\n")
    else:
        episode_index = {
            "series_name": SERIES_NAME,
            "collection_id": coll.id,
            "characters": CHARACTERS,
            "episodes": {}
        }

    # Process each episode
    for ep in EPISODES:
        ep_num = str(ep["number"])

        # Skip if already ingested
        if ep_num in episode_index["episodes"]:
            print(f"⏭️  Episode {ep_num} already ingested (video_id: {episode_index['episodes'][ep_num]['video_id']}), skipping.")
            continue

        print(f"📤 Episode {ep['number']}: {ep['title']}")

        try:
            # Step 1: Upload (Download locally first to bypass URL upload issues)
            local_path = os.path.join(os.path.dirname(__file__), '..', 'data', f"ep{ep['number']}.mp4")
            if not os.path.exists(local_path):
                print(f"   Downloading locally via yt-dlp from: {ep['url']} ...")
                subprocess.run(["python3", "-m", "yt_dlp", "-f", "best[ext=mp4]", "--output", local_path, ep["url"]], check=True)

            print(f"   Uploading local file to VideoDB: {local_path}")
            video = coll.upload(
                file_path=local_path,
                name=f"E{ep['number']:02d} - {ep['title']}"
            )
            print(f"   ✅ Uploaded — video_id: {video.id}")

            # Step 2: Index spoken words (transcription)
            print(f"   🎤 Indexing spoken words...")
            video.index_spoken_words()
            print(f"   ✅ Spoken word index complete")

            # Step 3: Index scenes with character-aware prompt + metadata
            print(f"   🎞️  Indexing scenes...")
            video.index_scenes(
                extraction_type=SceneExtractionType.time_based,
                extraction_config={"time": 60},  # analyze every 60 seconds
                prompt=SCENE_INDEX_PROMPT,
                metadata={
                    "episode": ep_num,
                    "series": SERIES_NAME[:20],  # max 20 chars
                }
            )
            print(f"   ✅ Scene index complete")

            # Save to index
            episode_index["episodes"][ep_num] = {
                "video_id": video.id,
                "title": ep["title"],
                "number": ep["number"],
            }

            # Persist after every episode (safe against crashes)
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w") as f:
                json.dump(episode_index, f, indent=2)
            print(f"   💾 Saved to episode_index.json\n")

            # Small pause between episodes to avoid rate limits
            time.sleep(2)

        except Exception as e:
            print(f"   ❌ Error on episode {ep_num}: {e}")
            print(f"   Continuing to next episode...\n")
            continue

    print("─" * 50)
    print(f"✅ Ingestion complete!")
    print(f"   Episodes indexed: {len(episode_index['episodes'])}")
    print(f"   Index saved to: {index_path}")
    print(f"\n   You can now run the backend: uvicorn main:app --reload")


if __name__ == "__main__":
    main()
