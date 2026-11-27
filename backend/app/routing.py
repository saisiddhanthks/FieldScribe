"""
Road routing for ambulances.

Online: OSRM road routes (cached). Offline: on-device shortest drive time over the
downloaded OpenStreetMap road graph (backend/maps/bengaluru.json, see fetch_map.py),
then any cached OSRM route, then a labelled straight-line estimate.

Online: OSRM (OpenStreetMap routing, free public server, no key) gives the real
road geometry, distance and drive time. Every route is cached in SQLite, so a
route fetched once keeps working in a dead zone. Offline / unreachable: a
straight-line estimate (great-circle distance x 1.35 road factor at 28 km/h
urban ambulance speed), clearly labelled as an estimate.
"""
from __future__ import annotations

import heapq
import json
import math
import os
import threading
import time
from pathlib import Path
from datetime import datetime, timezone

import httpx

from . import db

OSRM = os.environ.get("FIELDSCRIBE_OSRM_URL", "https://router.project-osrm.org")
ROAD_FACTOR, URBAN_KMH = 1.35, 28.0
_last_fail: dict[str, float] = {}



def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _key(a, b) -> str:
    return f"{a[0]:.4f},{a[1]:.4f}>{b[0]:.4f},{b[1]:.4f}"


def estimate(a, b) -> dict:
    d = haversine_m(a, b) * ROAD_FACTOR
    return {"source": "estimate", "coords": [list(a), list(b)], "distance_m": round(d), "duration_s": round(d / (URBAN_KMH / 3.6))}


# ----------------------------------------------------------------------------- offline road graph

MAP_FILE = Path(os.environ.get("FIELDSCRIBE_MAP", Path(__file__).resolve().parent.parent / "maps" / "bengaluru.json"))
SPEED_KMH = {1: 50, 2: 34, 3: 30, 4: 26, 5: 22, 6: 18}  # ambulance urban speeds by road class
_G: dict = {}
_G_LOCK = threading.Lock()


def map_status() -> dict:
    ok = MAP_FILE.exists()
    out = {"available": ok, "path": str(MAP_FILE)}
    if ok:
        out["size_mb"] = round(MAP_FILE.stat().st_size / 1e6, 1)
        g = _graph()
        out.update({k: g.get(k) for k in ("name", "fetched", "roads", "nodes", "edges", "build_s", "full")})
    return out


def _graph() -> dict:
    """Build (once) an undirected road graph from the offline map. Ambulances may use
    either direction under emergency exemption, so one-way tags are not enforced."""
    if _G or not MAP_FILE.exists():
        return _G
    with _G_LOCK:
        if _G:
            return _G
        t0 = time.time()
        data = json.loads(MAP_FILE.read_text(encoding="utf-8"))
        ids: dict[tuple, int] = {}
        pts: list[tuple[float, float]] = []
        adj: list[list[tuple[int, float, float]]] = []

        def nid(p):
            k = (p[0], p[1])
            i = ids.get(k)
            if i is None:
                i = ids[k] = len(pts)
                pts.append(k)
                adj.append([])
            return i
        edges = 0
        for r in data["roads"]:
            sp = SPEED_KMH.get(r.get("c", 5), 22) / 3.6
            g = r["g"]
            prev = nid(g[0])
            for p in g[1:]:
                cur = nid(p)
                if cur != prev:
                    d = haversine_m(pts[prev], pts[cur])
                    adj[prev].append((cur, d, d / sp))
                    adj[cur].append((prev, d, d / sp))
                    edges += 1
                prev = cur
        # keep snapping to the largest connected component so every route is solvable
        comp = [-1] * len(pts)
        best, best_size = 0, 0
        for s0 in range(len(pts)):
            if comp[s0] != -1:
                continue
            stack, size = [s0], 0
            comp[s0] = s0
            while stack:
                u = stack.pop()
                size += 1
                for v, _, _ in adj[u]:
                    if comp[v] == -1:
                        comp[v] = s0
                        stack.append(v)
            if size > best_size:
                best, best_size = s0, size
        grid: dict[tuple[int, int], list[int]] = {}
        for i, p in enumerate(pts):
            if comp[i] == best:
                grid.setdefault((int(p[0] / 0.004), int(p[1] / 0.004)), []).append(i)
        _G.update({"pts": pts, "adj": adj, "grid": grid, "name": data.get("name"), "fetched": data.get("fetched"),
                   "roads": len(data["roads"]), "nodes": len(pts), "edges": edges, "full": data.get("full"),
                   "build_s": round(time.time() - t0, 2)})
    return _G


def _snap(g: dict, p: tuple[float, float]) -> int | None:
    cx, cy = int(p[0] / 0.004), int(p[1] / 0.004)
    for r in range(0, 12):
        best, bd = None, 1e18
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                for i in g["grid"].get((cx + dx, cy + dy), ()):
                    d = haversine_m(p, g["pts"][i])
                    if d < bd:
                        best, bd = i, d
        if best is not None:
            return best
    return None


_mem: dict[str, dict] = {}


def offline_route(a, b) -> dict | None:
    g = _graph()
    if not g:
        return None
    k = _key(a, b)
    if k in _mem:
        return dict(_mem[k], cached=True)
    s, t = _snap(g, a), _snap(g, b)
    if s is None or t is None:
        return None
    dist = {s: 0.0}
    meters = {s: 0.0}
    prev: dict[int, int] = {}
    pq = [(0.0, s)]
    adj = g["adj"]
    while pq:
        du, u = heapq.heappop(pq)
        if u == t:
            break
        if du > dist.get(u, 1e18):
            continue
        for v, m, w in adj[u]:
            nd = du + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                meters[v] = meters[u] + m
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if t not in dist:
        return None
    path = [t]
    while path[-1] != s:
        path.append(prev[path[-1]])
    path.reverse()
    coords = [list(a)] + [list(g["pts"][i]) for i in path] + [list(b)]
    lead = haversine_m(a, g["pts"][s]) + haversine_m(g["pts"][t], b)  # walk/drive to the snapped road
    r = {"source": "offline-roads", "coords": coords, "distance_m": round(meters[t] + lead),
         "duration_s": round(dist[t] + lead / (15 / 3.6))}
    _mem[k] = r
    return dict(r, cached=False)


def _cached(k: str) -> dict | None:
    c = db.q1("SELECT payload FROM route_cache WHERE key=?", (k,))
    return dict(json.loads(c["payload"]), cached=True) if c else None


def _osrm(a, b, k) -> dict | None:
    if time.time() - _last_fail.get("osrm", 0) < 60:  # server/internet just failed: go straight to offline routing
        return None
    try:
        url = f"{OSRM}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}?overview=full&geometries=geojson"
        resp = httpx.get(url, timeout=3, headers={"User-Agent": "FieldScribe-hackathon-demo"})
        if resp.status_code == 200 and resp.json().get("routes"):
            rt = resp.json()["routes"][0]
            r = {"source": "osrm", "coords": [[c[1], c[0]] for c in rt["geometry"]["coordinates"]],
                 "distance_m": round(rt["distance"]), "duration_s": round(rt["duration"])}
            with db.tx() as c:
                c.execute("INSERT OR REPLACE INTO route_cache(key,payload,fetched_at) VALUES(?,?,?)",
                          (k, json.dumps(r), datetime.now(timezone.utc).isoformat(timespec="seconds")))
            return dict(r, cached=False)
    except Exception:
        pass
    _last_fail["osrm"] = time.time()
    return None


def route(a: tuple[float, float], b: tuple[float, float], online: bool) -> dict:
    """Online: live OSRM road route (cached). Offline: on-device route over the downloaded
    road graph; then a previously cached OSRM route; then a labelled straight-line estimate."""
    k = _key(a, b)
    if online:
        r = _cached(k) or _osrm(a, b, k)
        if r:
            return r
    return offline_route(a, b) or _cached(k) or dict(estimate(a, b), cached=False)


def along(coords: list[list[float]], frac: float) -> list[float]:
    """Point at fraction `frac` of the polyline length."""
    if len(coords) < 2:
        return coords[0]
    segs = [haversine_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]
    target = sum(segs) * max(0.0, min(1.0, frac))
    for i, s in enumerate(segs):
        if target <= s and s > 0:
            t = target / s
            return [coords[i][0] + (coords[i + 1][0] - coords[i][0]) * t, coords[i][1] + (coords[i + 1][1] - coords[i][1]) * t]
        target -= s
    return coords[-1]
