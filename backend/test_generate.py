import asyncio
from models import UserState
from main import generate_recap

async def main():
    state = UserState(
        watched_episodes=[1],
        next_episode=2,
        time_since_last_watch="one_week",
        focus_character="Walter White",
        recap_length="full"
    )
    try:
        res = await generate_recap(state)
        print("Success! Recap ready.")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
