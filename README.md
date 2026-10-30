# FlowSense — Beginner MVP (simulation mode)

A small, working first version of FlowSense for Kolkata. It runs with **no API keys and no database**.
**All data is simulated and labelled as such.** It does not detect real phones, Wi-Fi or network connections.

## Run it
```bash
pip install -r requirements.txt
cd backend
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000 (the backend also serves the frontend). API docs: http://127.0.0.1:8000/docs
The map needs internet for Leaflet and OpenStreetMap tiles.

## Test it
```bash
cd backend && python -m pytest tests/test_core.py -q
```

## What works
- Map of 5 demo zones (Jadavpur, Kalighat, Howrah Station, Howrah Bus Stand, Belur) coloured by activity level, with text labels.
- Scenario switch: Normal day, Peak crowd, Crowd clearing, Sudden surge, Low activity.
- Location panel: activity index and label, trend, wait band (for zones with a facility profile), confidence, source, updated time, 30-min chart.
- Journey planner: 3 demo route alternatives with duration, distance, delay minutes, delay score, crowd coverage and warnings; sort by fastest / least delay / shortest.

## Files
- `backend/app/logic.py` — simulator and all formulas (activity, trend, wait, confidence, delay score, demo routes).
- `backend/app/main.py` — FastAPI endpoints under `/api/v1`.
- `frontend/index.html` — whole UI (plain HTML + Leaflet).
- `backend/tests/test_core.py` — algorithm and API tests.

## Formulas (see spec section 8-9)
- Trend: mean(last 10 min) − mean(previous 10 min); > +5 rising, < −5 falling, else stable.
- Wait = people_ahead / service_rate, shown as a band (0.75x–1.35x). people_ahead = activity/100 × assumed queue capacity.
- Delay = max(0, current − baseline); Delay score = round(100 × clamp(delay / baseline, 0, 1)). It is relative severity, not a probability.
- Route crowd: 25 sample points per route; only points inside a zone (radius × 1.5) count; the rest are "unknown" and add no delay.

## Limitations (deliberate, for a first MVP)
- Simulated data only; facility capacities and speeds are made-up assumptions. Coordinates are approximate.
- Routes are straight-line shapes with a sideways bend, not real roads. No live traffic, no transit.
- No PostgreSQL, Alembic, auth, rate limiting, sensor ingestion or opt-in source yet; no minimum-sample suppression.
- No frontend tests or Playwright test yet.

## Next steps
1. Add PostgreSQL + Alembic and store aggregates. 2. Add a real routing adapter (OpenRouteService/OSRM) behind the same response shape.
3. Add the secured sensor-ingestion endpoint. 4. Rebuild the UI in React + TypeScript. 5. Add Playwright and the stretch features.
