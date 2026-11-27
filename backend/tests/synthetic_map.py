"""Synthetic Bengaluru-shaped road grid for tests and offline demos without OSM data."""
import json
import random


def make(path, step=0.006, seed=3):
    rng = random.Random(seed)
    s, w, n, e = 12.80, 77.45, 13.12, 77.80
    roads = []
    lat = s
    i = 0
    while lat <= n:
        c = 2 if i % 8 == 0 else 4
        roads.append({"c": c, "n": f"{i} Cross Rd", "g": [[round(lat, 5), round(lo, 5)] for lo in frange(w, e, step)]})
        lat += step; i += 1
    lo = w; j = 0
    while lo <= e:
        c = 2 if j % 8 == 0 else 4
        roads.append({"c": c, "n": f"{j} Main Rd", "g": [[round(la, 5), round(lo, 5)] for la in frange(s, n, step)]})
        lo += step; j += 1
    # a diagonal "outer ring road"
    roads.append({"c": 1, "n": "Outer Ring Rd", "g": [[round(12.92 + 0.11 * t / 40, 5), round(77.62 - 0.08 * t / 40, 5)] for t in range(41)]})
    water = [{"n": "Ulsoor Lake", "g": [[12.981, 77.618], [12.986, 77.621], [12.983, 77.627], [12.978, 77.623], [12.981, 77.618]]}]
    parks = [{"n": "Cubbon Park", "g": [[12.972, 77.590], [12.980, 77.592], [12.978, 77.601], [12.970, 77.598], [12.972, 77.590]]}]
    places = [{"n": "Koramangala", "p": [12.935, 77.624], "k": "suburb"}, {"n": "Malleshwaram", "p": [13.003, 77.570], "k": "suburb"}]
    json.dump({"name": "Synthetic grid", "bbox": [s, w, n, e], "fetched": "test", "full": False, "attribution": "synthetic",
               "roads": roads, "water": water, "parks": parks, "places": places}, open(path, "w"))


def frange(a, b, st):
    out = []
    x = a
    while x <= b + 1e-9:
        out.append(x); x += st
    return out
