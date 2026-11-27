"""
Download an offline street map of Bengaluru from OpenStreetMap (one time, needs internet).

    python fetch_map.py              # main roads + lakes + parks + area names  (~10-25 MB, 2-8 min)
    python fetch_map.py --full       # also residential streets                 (much larger, slower)
    python fetch_map.py --bbox 12.80,77.45,13.12,77.80   # south,west,north,east

The city is fetched in small tiles so busy public servers accept the requests. Each tile is
saved as it arrives, so if anything fails just run the command again and it resumes.
Saves backend/maps/bengaluru.json. Data (c) OpenStreetMap contributors, ODbL.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "maps" / "bengaluru.json"
TILE_DIR = HERE / "maps" / ".tiles"
MIRRORS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.private.coffee/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter"]
MAIN = "motorway|trunk|primary|secondary|tertiary|unclassified|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link"
CLASS = {"motorway": 1, "trunk": 1, "motorway_link": 1, "trunk_link": 1, "primary": 2, "primary_link": 2,
         "secondary": 3, "secondary_link": 3, "tertiary": 4, "tertiary_link": 4, "unclassified": 5, "residential": 6,
         "living_street": 6}


def overpass(q: str, label: str) -> dict:
    waits = [0, 10, 25, 45, 60]
    last = None
    for attempt, w in enumerate(waits):
        if w:
            print(f"      servers busy, waiting {w}s before retry {attempt}/{len(waits) - 1} ...", flush=True)
            time.sleep(w)
        for url in MIRRORS:
            try:
                r = httpx.post(url, data={"data": q}, timeout=120, headers={"User-Agent": "FieldScribe-offline-map/1.1"})
                if r.status_code == 200:
                    return r.json()
                last = f"{url.split('/')[2]}: HTTP {r.status_code}"
            except Exception as e:
                last = f"{url.split('/')[2]}: {type(e).__name__}"
    raise RuntimeError(f"{label}: all servers failed ({last})")


def tiles(bb: list[float], n: int):
    s, w, nn, e = bb
    dl, dw = (nn - s) / n, (e - w) / n
    for i in range(n):
        for j in range(n):
            yield i * n + j, (round(s + i * dl, 5), round(w + j * dw, 5), round(s + (i + 1) * dl, 5), round(w + (j + 1) * dw, 5))


def cached(name: str, q: str, label: str) -> dict:
    f = TILE_DIR / f"{name}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    data = overpass(q, label)
    TILE_DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data), encoding="utf-8")
    return data


def rnd(g):
    return [[round(p["lat"], 5), round(p["lon"], 5)] for p in g]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", default="12.80,77.45,13.12,77.80")
    ap.add_argument("--full", action="store_true", help="include residential streets (large)")
    ap.add_argument("--grid", type=int, default=4, help="split the area into GRID x GRID tiles")
    a = ap.parse_args()
    bb = [float(x) for x in a.bbox.split(",")]
    hw = MAIN + ("|residential|living_street" if a.full else "")
    tag = "full" if a.full else "main"
    t0 = time.time()
    roads, seen = [], set()
    print(f"1/3 roads ({a.grid * a.grid} tiles)")
    for k, (s, w, n, e) in tiles(bb, a.grid):
        q = f'[out:json][timeout:90];way["highway"~"^({hw})$"]({s},{w},{n},{e});out tags geom;'
        data = cached(f"roads_{tag}_{a.grid}_{k}", q, f"roads tile {k + 1}")
        added = 0
        for el in data.get("elements", []):
            if el.get("type") != "way" or "geometry" not in el or el["id"] in seen:
                continue
            seen.add(el["id"])
            t = el.get("tags", {})
            roads.append({"c": CLASS.get(t.get("highway"), 5), "n": t.get("name:en") or t.get("name") or t.get("ref") or "",
                          "g": rnd(el["geometry"])})
            added += 1
        print(f"   tile {k + 1:2d}/{a.grid * a.grid}: +{added} roads (total {len(roads)})", flush=True)
    print("2/3 lakes and parks")
    water, parks, seen_a = [], [], set()
    for k, (s, w, n, e) in tiles(bb, 2):
        q = (f'[out:json][timeout:90];(way["natural"="water"]({s},{w},{n},{e});way["water"="lake"]({s},{w},{n},{e});'
             f'way["leisure"="park"]({s},{w},{n},{e}););out tags geom;')
        data = cached(f"areas_{k}", q, f"areas tile {k + 1}")
        for el in data.get("elements", []):
            if "geometry" not in el or len(el["geometry"]) < 4 or el["id"] in seen_a:
                continue
            seen_a.add(el["id"])
            t = el.get("tags", {})
            item = {"n": t.get("name:en") or t.get("name") or "", "g": rnd(el["geometry"])}
            (water if t.get("natural") == "water" or t.get("water") else parks).append(item)
        print(f"   tile {k + 1}/4: {len(water)} water, {len(parks)} parks", flush=True)
    print("3/3 area names")
    data = cached("places_v2", f'[out:json][timeout:60];node["place"~"^(suburb|neighbourhood|quarter|town)$"]({bb[0]},{bb[1]},{bb[2]},{bb[3]});out body;',
                  "places")
    places = [{"n": el["tags"].get("name:en") or el["tags"].get("name"), "p": [round(el["lat"], 5), round(el["lon"], 5)],
               "k": el["tags"].get("place")} for el in data.get("elements", [])
              if el.get("tags", {}).get("name") and "lat" in el and "lon" in el]
    print(f"   {len(places)} places")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = {"name": "Bengaluru", "bbox": bb, "fetched": time.strftime("%Y-%m-%d"), "full": a.full,
           "attribution": "© OpenStreetMap contributors (ODbL)", "roads": roads, "water": water, "parks": parks, "places": places}
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"\nSaved {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB) in {time.time() - t0:.0f}s")
    print("Restart FieldScribe: the map and road routes now also work fully offline.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"\nStopped: {e}.\nThe public map servers are busy. Tiles downloaded so far are saved -"
              f" wait 2-3 minutes and run the same command again; it continues where it stopped.")
        sys.exit(1)
