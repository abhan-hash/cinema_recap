<<<<<<< HEAD

> "Previously on... but built for you specifically."

**VideoDB Global Media Intelligence Hackathon 2026**

---

## What it does

Every streaming platform gives every viewer the same "Previously on..." recap. RecapAI generates a personalised recap from the actual episode archive based on:

- **What you've watched** — which episodes, not a generic summary
- **How long ago** — watched last night vs 6 months ago → different depth
- **Which character you care about** — recap focused on that arc

An AI planning agent (Claude) decides which 5–8 moments are essential context for *your* specific next episode. VideoDB retrieves the exact clips from the archive using semantic search. AI-generated bridging narration ties the clips together.


## Architecture

```
User state (watched eps, time, character)
        ↓
Layer 2: Claude planning agent → recap brief (list of moments to find)
        ↓
Layer 3: VideoDB semantic search → exact timestamps + clips
        ↓
Layer 4: Claude narration scripts + OpenAI TTS audio
        ↓
Frontend: Sequenced player (narration → clip → narration → clip...)
```

### VideoDB usage
- `video.index_spoken_words()` — transcript + semantic search on dialogue
- `video.index_scenes(prompt=...)` — visual scene index with character-aware prompt
- `video.search(query, index_type=["scene", "spoken_word"])` — multi-index search
- `coll.search(query, filter=[{"episode": "3"}])` — collection-wide search scoped to watched episodes
- `video.generate_stream(timeline=[(start, end)])` — timestamped clip extraction

---

## Setup

### 1. Fill in API keys
```bash
cp .env.example .env
# Edit .env with your keys:
# VIDEODB_API_KEY=...
# ANTHROPIC_API_KEY=...
# OPENAI_API_KEY=...  (optional, for TTS narration audio)
```

### 2. Configure your series
Edit `backend/ingest.py`:
- Set `SERIES_NAME`
- Fill in the `EPISODES` list with your video URLs or file paths
- Set `CHARACTERS` list

### 3. Run ingestion (one-time)
```bash
cd backend
pip install -r requirements.txt
python3 ingest.py
```
This uploads every episode to VideoDB, indexes spoken words and scenes. Takes ~5-10 min per episode. Resumable — re-run safely.

### 4. Start the backend
```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 5. Start the frontend
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173

---

## Project structure

```
recapai/
├── backend/
│   ├── ingest.py        # Layer 0: one-time ingestion
│   ├── config.py        # VideoDB connection + episode index
│   ├── models.py        # Pydantic data models
│   ├── agent.py         # Layer 2: Claude planning agent
│   ├── retrieval.py     # Layer 3: VideoDB search + clip extraction
│   ├── narration.py     # Layer 4: narration scripts + TTS
│   └── main.py          # FastAPI app
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── WatchStateForm.jsx    # Screen 1: user state input
│       │   ├── GeneratingScreen.jsx  # Screen 2: progress indicator
│       │   └── RecapPlayer.jsx       # Screen 3: recap player + evidence
│       └── index.css
└── data/
    └── episode_index.json   # Created by ingest.py
```

---

## Tech stack

| Layer | Tech |
|-------|------|
| Video archive | VideoDB (spoken word + scene indexes) |
| Planning agent | Claude Sonnet (Anthropic) |
| Narration TTS | OpenAI TTS (voice: onyx) |
| Backend API | FastAPI (Python) |
| Frontend | React + Vite |
=======
# cinema_
=======
# cinema_recap
>>>>>>> 7254362ccc76b7eea93e33f8214824b6f373a7f4
