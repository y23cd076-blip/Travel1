# SmartTrip AI — Intelligent Travel Itinerary Planner

An AI travel agent that generates day-by-day itineraries, budget breakdowns, and
travel tips — built around **constraint-based optimization** and **grounded
LLM generation**, rather than asking an LLM to freely hallucinate a plan.

## Why this isn't "just an LLM wrapper"

Most AI travel planner demos ask an LLM one prompt and print the response.
That approach reliably produces itineraries that ignore the stated budget,
invent places that don't exist, schedule things geographically far apart on
the same day, and repeat attractions across days. This project fixes that
with a two-stage pipeline:

1. **Optimizer (`backend/optimizer.py`)** — a 0/1 knapsack algorithm treats
   each day's available hours as capacity and each attraction's
   interest-match score as value, selecting the best feasible subset per day
   from a curated, real dataset (`backend/data/destinations.json`). Hotels
   and restaurants are then chosen greedily to fit whatever budget remains.
   This stage is 100% deterministic and explainable — no hallucination is
   possible because the LLM hasn't been involved yet.

2. **LLM narrative layer (`backend/llm_service.py`)** — only after the
   schedule is fixed does an LLM get involved, and only to write prose
   (day summaries, tips, packing lists) *about* the already-decided
   schedule. It is explicitly instructed not to introduce new places, and a
   template-based fallback keeps the app fully functional even with no API
   key configured.

This split is the core academic contribution to document in your report:
**Design & Analysis of Algorithms** (the knapsack formulation) combined with
**hallucination mitigation via retrieval/grounding** (the curated dataset).

## Architecture

```
Streamlit Frontend (frontend/app.py)
        │  HTTP (requests)
        ▼
FastAPI Backend (backend/main.py)
        │
        ├── optimizer.py      → knapsack-based day/attraction/hotel/restaurant selection
        ├── llm_service.py    → grounded narrative generation (Gemini API, optional)
        ├── database.py       → Firestore if configured, else local JSON fallback
        └── data/destinations.json → curated dataset (5 pilot cities)
```

## Project structure

```
AI-Travel-Agent/
├── backend/
│   ├── main.py              # FastAPI app, /plan-trip endpoint
│   ├── models.py             # Pydantic request/response schemas
│   ├── optimizer.py          # Core knapsack optimization algorithm
│   ├── llm_service.py        # LLM narrative generation + fallback (Gemini)
│   ├── database.py           # Storage abstraction (Firestore / local JSON)
│   ├── data/
│   │   ├── destinations.json # Curated dataset: 5 pilot destinations
│   │   └── trips_db.json     # Auto-created local storage (if no Firestore)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app.py                 # Streamlit UI
│   └── requirements.txt
├── render.yaml
└── README.md
```

## Setup & running locally

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Optionally fill in GEMINI_API_KEY and/or FIREBASE_CREDENTIALS_JSON in .env
# The app works fully without either — see "Zero-config mode" below.

uvicorn main:app --reload
```

Backend runs at `http://localhost:8000`. Interactive API docs at
`http://localhost:8000/docs`.

### 2. Frontend

In a second terminal:

```bash
cd frontend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`.

### Zero-config mode

You can run this entire project with **no API keys and no database setup**:
- No `GEMINI_API_KEY` → narrative text uses a deterministic template.
- No `FIREBASE_CREDENTIALS_JSON` / `GOOGLE_APPLICATION_CREDENTIALS` → trips
  are saved to `backend/data/trips_db.json`.

This is intentional: it lets your whole team develop and demo without
waiting on shared credentials, and lets you swap in real credentials only
when you're ready.

### Getting a Gemini API key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey) and create a
   free API key.
2. Put it in `backend/.env` as `GEMINI_API_KEY=...`.
3. (Optional) Set `GEMINI_MODEL` to override the default (`gemini-2.5-flash`).

### Getting Firestore credentials

1. In the [Firebase console](https://console.firebase.google.com/), create a
   project (or use an existing one) and enable **Firestore Database**
   (Native mode).
2. Go to **Project Settings → Service Accounts → Generate new private key**.
   This downloads a JSON file.
3. Paste the *entire contents* of that JSON file as a single-line env var:
   `FIREBASE_CREDENTIALS_JSON='{"type": "service_account", ...}'`
   This is the simplest option for host platforms (Render, Railway, etc.)
   that only let you set env vars, not upload files.
   - Alternatively, set `GOOGLE_APPLICATION_CREDENTIALS` to a path pointing
     at the JSON file on disk (standard Google Cloud convention) instead.
4. Trips will be saved to a `trips` collection in Firestore, one document
   per trip.

## Pilot destinations (current dataset)

Goa, Manali, Jaipur, Kerala (Kochi & Munnar), Hyderabad — each with curated
attractions, restaurants, and hotels with realistic costs, durations, and
interest tags. Expanding this dataset (more cities, more entries per city)
is a natural, low-risk way to grow the project.

## API

**`GET /destinations`** — list available pilot destinations.

**`POST /plan-trip`**
```json
{
  "source": "Hyderabad",
  "destination": "goa",
  "start_date": "2026-08-10",
  "end_date": "2026-08-13",
  "budget": 35000,
  "interests": ["beaches", "nightlife", "food"]
}
```
Returns a full itinerary: day-by-day plan, hotel, budget breakdown, tips.

**`GET /trips`** — list previously saved trips.

## Deploying

`render.yaml` is set up to deploy the backend to [Render](https://render.com)
as a free web service. Set `GEMINI_API_KEY` and `FIREBASE_CREDENTIALS_JSON`
as secret env vars in the Render dashboard after connecting the repo (they're
marked `sync: false` so Render will prompt you for them rather than storing
them in the yaml file). Deploy the Streamlit frontend separately (e.g.
Streamlit Community Cloud), pointing its `BACKEND_URL` secret at your
Render backend URL.

## Known limitations (good material for your "Future Scope" chapter)

- Dataset is small and manually curated per city (future: scale via Maps
  Places API or scraping, or grow to more cities).
- Restaurant pool can run out for longer trips in smaller cities (e.g. Goa
  has 5 restaurants; a 4-day trip wanting 2/day needs 8) — a good place to
  add either a "repeat allowed after N days" rule or a bigger dataset.
- No live weather/Maps integration yet (planned Phase 2 — see your project
  roadmap doc).
- No user authentication yet — trips are stored but not tied to a user
  account (Firestore security rules currently allow the service account
  full access; add Firebase Auth + per-user rules for a real deployment).
- Budget estimates are only as good as the curated dataset's prices, which
  will drift from real-world prices over time.

## Suggested next build steps (for your team of 3)

1. Add Google Maps API — real distances between attractions, and a check
   that daily schedules aren't geographically absurd.
2. Add OpenWeatherMap — surface forecast + weather-based tip generation.
3. Add Firebase Auth + "my trips" page tied to a user ID (Firestore already
   makes this natural — store trips keyed by `user_id`).
4. PDF export of the generated itinerary.
5. Expand `destinations.json` to 10+ cities with a larger dataset per city.
6. Run the evaluation study (10-15 test users) and write up the results —
   this is a required section of your report, not optional polish.
