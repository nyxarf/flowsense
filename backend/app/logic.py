"""FlowSense MVP core: demo simulator + explainable estimates.
Pure Python (no web code) so every formula is easy to read and test."""
import math
import statistics
import zlib
from datetime import datetime

SCENARIOS = {
    "normal": "Normal day",
    "peak": "Peak crowd",
    "clearing": "Crowd clearing",
    "surge": "Sudden surge",
    "low": "Low activity",
}

# Demo zones. Coordinates are approximate: verify before any real use.
# "facility" = demo assumptions for the waiting-time model (not measured values).
LOCATIONS = [
    {"id": "jadavpur", "name": "Jadavpur", "category": "railway_station", "lat": 22.4991, "lon": 88.3710,
     "radius_m": 600, "scale": 0.9, "facility": {"service_points": 4, "avg_service_minutes": 1.2, "queue_capacity": 80}},
    {"id": "kalighat", "name": "Kalighat", "category": "other", "lat": 22.5206, "lon": 88.3427,
     "radius_m": 600, "scale": 1.0, "facility": None},
    {"id": "howrah-station", "name": "Howrah Station", "category": "railway_station", "lat": 22.5839, "lon": 88.3425,
     "radius_m": 900, "scale": 1.1, "facility": {"service_points": 10, "avg_service_minutes": 1.5, "queue_capacity": 250}},
    {"id": "howrah-bus", "name": "Howrah Bus Stand", "category": "bus_terminal", "lat": 22.5851, "lon": 88.3447,
     "radius_m": 700, "scale": 1.1, "facility": {"service_points": 6, "avg_service_minutes": 2.0, "queue_capacity": 110}},
    {"id": "belur", "name": "Belur", "category": "other", "lat": 22.6322, "lon": 88.3555,
     "radius_m": 600, "scale": 0.8, "facility": None},
]


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ---------- Simulator (deterministic: same inputs -> same numbers) ----------
def _gauss(h, mu, sigma):
    return math.exp(-((h - mu) ** 2) / (2 * sigma ** 2))


def daily_curve(minute_of_day):
    """Base activity 0..~1 with a morning (9h) and evening (18h) peak."""
    h = minute_of_day / 60
    return 0.25 + 0.45 * _gauss(h, 9, 1.5) + 0.55 * _gauss(h, 18, 1.8)


def scenario_factor(scenario, minutes_ago):
    if scenario == "peak":
        return 1.6
    if scenario == "low":
        return 0.4
    if scenario == "clearing":  # 1.8x thirty minutes ago -> 0.7x now
        return 0.7 + 1.1 * clamp(minutes_ago / 30, 0, 1)
    if scenario == "surge":  # flat 0.8x, then ramps to 2.2x over the last 10 min
        return 0.8 if minutes_ago > 10 else 0.8 + 1.4 * (10 - minutes_ago) / 10
    return 1.0


def _noise(seed, loc_id, minute):
    return (zlib.crc32(f"{seed}:{loc_id}:{minute}".encode()) % 7001) / 1000 - 3.5  # +-3.5


def simulate_series(loc, scenario, now_minute, seed=42, points=30):
    """Activity index (0-100) for each of the last `points` minutes, oldest first."""
    out = []
    for ago in range(points - 1, -1, -1):
        m = now_minute - ago
        raw = 100 * daily_curve(m % 1440) * loc["scale"] * scenario_factor(scenario, ago) + _noise(seed, loc["id"], m)
        out.append(round(clamp(raw, 0, 100), 1))
    return out


# ---------- Estimates ----------
def activity_label(index):
    for limit, name in [(20, "Very low"), (40, "Low"), (60, "Moderate"), (80, "High")]:
        if index <= limit:
            return name
    return "Very high"


def trend_of(series):
    """Mean of last 10 points minus mean of the 10 before. >+5 rising, <-5 falling."""
    if len(series) < 20:
        return "unknown", None
    delta = statistics.mean(series[-10:]) - statistics.mean(series[-20:-10])
    return ("rising" if delta > 5 else "falling" if delta < -5 else "stable"), round(delta, 1)


def confidence_score(sample_size, series):
    """Simplified spec formula. Simulated data has no real history, so source/history are low
    and the result is capped below 'high'."""
    freshness, source, history = 1.0, 0.4, 0.0
    sample = min(sample_size / 100, 1)
    stability = clamp(1 - statistics.pstdev(series[-10:]) / 20, 0, 1)
    score = 0.30 * freshness + 0.25 * sample + 0.20 * source + 0.15 * history + 0.10 * stability
    return min(score, 0.69)


def confidence_label(score):
    return "low" if score < 0.4 else "medium" if score < 0.7 else "high"


def wait_minutes(people_ahead, served_per_minute, eps=1e-6):
    """Spec formula: people ahead / service rate."""
    return people_ahead / max(served_per_minute, eps)


def wait_estimate(activity_index, facility):
    """Returns a wait band (minutes) or None when no facility profile exists."""
    if not facility:
        return None
    people_ahead = activity_index / 100 * facility["queue_capacity"]
    rate = facility["service_points"] / facility["avg_service_minutes"]
    mid = wait_minutes(people_ahead, rate)
    return {"low": round(mid * 0.75), "high": round(mid * 1.35),
            "basis": "demo facility throughput model (assumed capacity and service time)"}


def delay_minutes(current_min, baseline_min):
    return max(0.0, current_min - baseline_min)


def delay_score(delay_min, baseline_min):
    """Relative delay severity 0-100 (NOT a probability of being late)."""
    return round(100 * clamp(delay_min / max(baseline_min, 1), 0, 1))


def location_activity(loc, scenario, now: datetime, seed=42):
    series = simulate_series(loc, scenario, now.hour * 60 + now.minute, seed)
    idx = series[-1]
    sample = round(idx * 1.5)  # simulated "observation count"
    trend, delta = trend_of(series)
    conf = confidence_score(sample, series)
    return {
        "location_id": loc["id"], "name": loc["name"], "category": loc["category"],
        "lat": loc["lat"], "lon": loc["lon"], "radius_m": loc["radius_m"],
        "activity_index": idx, "activity_label": activity_label(idx),
        "trend": trend, "trend_delta": delta,
        "source_type": "simulated", "source_label": "SIMULATED — demo data", "is_simulated": True,
        "observed_at": now.isoformat(timespec="seconds"), "sample_size": sample,
        "estimated_people_range": None,  # needs a site-validated calibration factor
        "wait_estimate_minutes": wait_estimate(idx, loc["facility"]),
        "confidence": confidence_label(conf), "history": series,
        "limitations": [
            "Synthetic observations; not live phone, Wi-Fi or network counts",
            "Wait estimate depends on assumed service capacity" if loc["facility"]
            else "No facility profile, so no wait estimate",
        ],
    }


# ---------- Demo routing ----------
def haversine_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _path(a, b, bend, n=24):
    """Straight line from a to b with a sideways bulge of `bend` degrees (fake road alternative)."""
    dy, dx = b[0] - a[0], b[1] - a[1]
    norm = math.hypot(dx, dy) or 1
    pts = []
    for i in range(n + 1):
        t = i / n
        k = bend * math.sin(math.pi * t)
        pts.append((a[0] + dy * t + (dx / norm) * k, a[1] + dx * t - (dy / norm) * k))
    return pts


ROUTE_TEMPLATES = [  # label, bend (deg), speed km/h
    ("Direct route", 0.0, 22),
    ("Alternative via east", 0.014, 27),
    ("Alternative via west", -0.014, 26),
]


def build_routes(origin, dest, zone_activity, locations):
    """origin/dest = (lat, lon). zone_activity = {location_id: activity_index}.
    Only points inside a zone (radius x1.5) count as covered; the rest stay 'unknown'."""
    routes = []
    for label, bend, speed in ROUTE_TEMPLATES:
        pts = _path(origin, dest, bend)
        dist = sum(haversine_m(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) * 1.25  # road circuity
        baseline_s = dist / (speed / 3.6)
        acts = []
        for p in pts:
            near = [(haversine_m(p, (z["lat"], z["lon"])), z) for z in locations]
            near = [(d, z) for d, z in near if d <= z["radius_m"] * 1.5]
            acts.append(zone_activity[min(near, key=lambda t: t[0])[1]["id"]] if near else None)
        covered = [a for a in acts if a is not None]
        coverage = len(covered) / len(acts)
        # unknown points add no delay (we do not invent congestion)
        factor = sum(0.6 * a / 100 for a in covered) / len(acts)
        current_s = baseline_s * (1 + factor)
        d_min = delay_minutes(current_s / 60, baseline_s / 60)
        mean_act = round(statistics.mean(covered), 1) if covered else None
        warnings = []
        if coverage < 1:
            warnings.append(f"Crowd data unavailable along {round((1 - coverage) * 100)}% of this route")
        if not covered:
            warnings.append("No crowd data on this route; delay shown equals baseline")
        routes.append({
            "label": label, "geometry": [[round(a, 5), round(b, 5)] for a, b in pts],
            "distance_m": round(dist), "baseline_duration_s": round(baseline_s),
            "current_duration_s": round(current_s),
            "duration_source": "demo model: baseline speed + simulated zone activity (no live traffic)",
            "delay_minutes": round(d_min, 1), "delay_score": delay_score(d_min, baseline_s / 60),
            "crowd": {"coverage_pct": round(coverage * 100), "mean_activity": mean_act,
                      "label": activity_label(mean_act) if mean_act is not None else "Unknown"},
            "confidence": "low" if coverage < 0.5 else "medium", "warnings": warnings,
        })
    return sorted(routes, key=lambda r: r["current_duration_s"])
