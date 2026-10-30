from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import logic
from app.main import app

NOON = datetime(2026, 10, 30, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
LOC = {l["id"]: l for l in logic.LOCATIONS}
client = TestClient(app)


# ---- Algorithm tests (cases from the spec) ----
def test_wait_100_people_5_per_minute():
    assert logic.wait_minutes(100, 5) == 20


def test_delay_52_vs_35():
    d = logic.delay_minutes(52, 35)
    assert d == 17 and logic.delay_score(d, 35) == 49


def test_delay_never_negative():
    assert logic.delay_minutes(30, 35) == 0


def test_trend_falling_80_to_50():
    assert logic.trend_of([80.0] * 10 + [50.0] * 10)[0] == "falling"


def test_trend_unknown_without_data():
    assert logic.trend_of([])[0] == "unknown"  # no data is NOT zero crowd


def test_labels():
    assert logic.activity_label(10) == "Very low" and logic.activity_label(78) == "High"


# ---- Simulator ----
def test_simulator_is_deterministic():
    a = logic.location_activity(LOC["howrah-bus"], "normal", NOON)
    assert a == logic.location_activity(LOC["howrah-bus"], "normal", NOON)


def test_scenarios_change_trend():
    assert logic.location_activity(LOC["howrah-bus"], "surge", NOON)["trend"] == "rising"
    assert logic.location_activity(LOC["howrah-bus"], "clearing", NOON)["trend"] == "falling"
    assert logic.location_activity(LOC["howrah-bus"], "normal", NOON)["trend"] == "stable"


def test_wait_grows_with_crowd():
    low = logic.location_activity(LOC["howrah-bus"], "low", NOON)["wait_estimate_minutes"]
    peak = logic.location_activity(LOC["howrah-bus"], "peak", NOON)["wait_estimate_minutes"]
    assert peak["high"] > low["high"]


def test_no_facility_no_wait():
    assert logic.location_activity(LOC["kalighat"], "normal", NOON)["wait_estimate_minutes"] is None


def test_simulated_is_always_labelled():
    a = logic.location_activity(LOC["belur"], "normal", NOON)
    assert a["is_simulated"] and "SIMULATED" in a["source_label"] and a["estimated_people_range"] is None


# ---- API ----
def test_health():
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_locations_endpoint():
    data = client.get("/api/v1/locations?scenario=peak").json()
    assert len(data) == 5 and all(x["is_simulated"] for x in data)


def test_bad_scenario_rejected():
    assert client.get("/api/v1/locations?scenario=nope").status_code == 422


def test_unknown_location():
    assert client.get("/api/v1/locations/xyz/activity").status_code == 404


def _req(o, d, scenario="normal"):
    return {"origin": {"lat": LOC[o]["lat"], "lon": LOC[o]["lon"]},
            "destination": {"lat": LOC[d]["lat"], "lon": LOC[d]["lon"]}, "scenario": scenario}


def test_routes_alternatives():
    r = client.post("/api/v1/routes/alternatives", json=_req("jadavpur", "howrah-station", "peak")).json()
    assert r["is_simulated"] and len(r["routes"]) >= 2
    for rt in r["routes"]:
        assert rt["current_duration_s"] >= rt["baseline_duration_s"] and 0 <= rt["delay_score"] <= 100


def test_routes_validation():
    bad = {"origin": {"lat": 200, "lon": 0}, "destination": {"lat": 1, "lon": 1}}
    assert client.post("/api/v1/routes/alternatives", json=bad).status_code == 422
    same = client.post("/api/v1/routes/alternatives", json=_req("belur", "belur"))
    assert same.status_code == 400
