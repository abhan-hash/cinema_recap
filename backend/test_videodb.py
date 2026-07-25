from config import get_videodb_conn, load_episode_index

try:
    conn = get_videodb_conn()
    coll = conn.get_collection()
    index = load_episode_index()
    video_id = list(index["episodes"].values())[0]["video_id"]
    video = coll.get_video(video_id)
    results = video.search(query="walter")
    shots = results.get_shots()
    print("Shots count:", len(shots))
except Exception as e:
    print("Error:", e)
