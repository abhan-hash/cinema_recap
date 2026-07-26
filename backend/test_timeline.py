from config import get_videodb_conn
from videodb.timeline import Timeline
from videodb.asset import VideoAsset

conn = get_videodb_conn()
timeline = Timeline(conn)
timeline.add_inline(VideoAsset(asset_id="m-z-019f9b16-fc09-7451-be0b-c9322c50838b", start=10, end=15))
stream = timeline.generate_stream()
print(stream)
