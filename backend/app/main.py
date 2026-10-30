"""FlowSense MVP API. Run: uvicorn app.main:app --reload  (from the backend folder)"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import logic

SEED = int(os.getenv("SIMULATION_SEED", "42"))
IST = timezone(timedelta(hours=5, minutes=30))
Scenario = Literal["normal", "peak", "clearing", "surge", "low"]

app = FastAPI(title="FlowSense MVP", description="Simulated crowd & route insights for Kolkata")


def _now():
    return datetime.now(IST)


def _find(location_id):
    for loc in logic.LOCATIONS:
        if loc["id"] == location_id:
            return loc
    raise HTTPException(404, "Unknown location")


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "data_mode": "simulation"}


@app.get("/api/v1/scenarios")
def scenarios():
    return [{"id": k, "label": v} for k, v in logic.SCENARIOS.items()]


@app.get("/api/v1/locations")
def locations(scenario: Scenario = "normal"):
    now = _now()
    return [logic.location_activity(l, scenario, now, SEED) for l in logic.LOCATIONS]


@app.get("/api/v1/locations/{location_id}/activity")
def activity(location_id: str, scenario: Scenario = "normal"):
    return logic.location_activity(_find(location_id), scenario, _now(), SEED)


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str | None = Field(default=None, max_length=80)


class RouteRequest(BaseModel):
    origin: Point
    destination: Point
    scenario: Scenario = "normal"


@app.post("/api/v1/routes/alternatives")
def route_alternatives(req: RouteRequest):
    o, d = (req.origin.lat, req.origin.lon), (req.destination.lat, req.destination.lon)
    if logic.haversine_m(o, d) < 300:
        raise HTTPException(400, "Origin and destination are too close together")
    now = _now()
    zones = {l["id"]: logic.location_activity(l, req.scenario, now, SEED)["activity_index"] for l in logic.LOCATIONS}
    return {
        "provider": "demo-route-provider", "is_simulated": True,
        "source_label": "SIMULATED — demo routes, not live traffic",
        "fetched_at": now.isoformat(timespec="seconds"),
        "routes": logic.build_routes(o, d, zones, logic.LOCATIONS),
    }


# Serve the frontend from the same server (must be registered last).
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
