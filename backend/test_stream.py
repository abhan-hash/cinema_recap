from config import get_videodb_conn, load_episode_index
try:
    conn = get_videodb_conn()
    coll = conn.get_collection()
    index = load_episode_index()
    video_id = list(index["episodes"].values())[0]["video_id"]
    video = coll.get_video(video_id)
    stream = video.generate_stream(timeline=[(0, 10)])
    print("Stream:", type(stream), stream)
except Exception as e:
    print("Error:", e)
