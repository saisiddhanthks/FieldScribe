"""
Synthetic gold-standard benchmark for the clinical NER.

Generates deterministic EMT dictations with known ground truth across slices:
  clean, brand (Indian brand names), hinglish (code-mixed), asr_noise (mis-spelt
  drug names as an ASR would produce), negation, spoken_numbers, multi_drug.
Metrics: entity P/R/F1 (drug+dose+unit+route must all match), per-field
accuracy, per-slice F1, negation accuracy, *silent critical error* rate
(a wrong drug or dose that the engine did NOT flag for review), and latency.
No real patient data is used.
"""
from __future__ import annotations

import random
import re
import statistics
import time

from .nlp import lexicon as L
from .nlp.ner import extract

ROUTE_SAY = {"PO": ["oral", "orally", "by mouth"], "IV": ["iv", "intravenous"], "IM": ["im", "intramuscular"],
             "SL": ["sublingual", "under the tongue"], "NEB": ["nebulised", "nebulized"], "IN": ["intranasal"]}
UNIT_SAY = {"mg": ["mg", "milligram"], "mcg": ["mcg", "micrograms"], "g": ["g", "gram"], "mL": ["ml", "millilitres"]}
DRUG_CASES = [
    ("Aspirin", [300, 325, 150], "mg", "PO", ["ecosprin", "disprin"]),
    ("Paracetamol", [500, 650, 1000], "mg", "PO", ["dolo", "crocin", "pcm"]),
    ("Ondansetron", [4, 8], "mg", "IV", ["emeset", "ondem"]),
    ("Pheniramine", [22.75, 45.5], "mg", "IM", ["avil"]),
    ("Salbutamol", [2.5, 5], "mg", "NEB", ["asthalin"]),
    ("Adrenaline", [0.5, 0.3], "mg", "IM", ["epinephrine"]),
    ("Nitroglycerin", [0.4], "mg", "SL", ["ntg", "gtn"]),
    ("Isosorbide dinitrate", [5, 10], "mg", "SL", ["sorbitrate", "isordil"]),
    ("Normal saline", [500, 250, 1000], "mL", "IV", ["saline"]),
    ("Ringer lactate", [500, 1000], "mL", "IV", ["rl"]),
    ("Tranexamic acid", [1], "g", "IV", ["txa"]),
    ("Diclofenac", [75, 50], "mg", "IM", ["voveran"]),
    ("Hydrocortisone", [100, 200], "mg", "IV", ["efcorlin"]),
    ("Midazolam", [2, 5], "mg", "IV", ["mezolam"]),
    ("Morphine", [2, 5], "mg", "IV", ["morphine"]),
    ("Dextrose", [50, 100], "mL", "IV", ["d25"]),
    ("Diazepam", [5, 10], "mg", "IV", ["calmpose"]),
    ("Fentanyl", [50, 100], "mcg", "IV", ["fentanyl"]),
]
NUM_SAY = {300: "three hundred", 500: "five hundred", 4: "four", 8: "eight", 100: "one hundred", 2: "two", 5: "five",
           650: "six hundred fifty", 1000: "one thousand", 75: "seventy five", 50: "fifty", 250: "two hundred fifty",
           150: "one hundred fifty", 325: "three hundred twenty five", 200: "two hundred", 10: "ten", 1: "one"}
NOISE = {"Aspirin": ["asprin", "aspirn"], "Ondansetron": ["ondansatron", "ondansetrone"], "Paracetamol": ["paracitamol", "paracetmol"],
         "Adrenaline": ["adrenalne", "adrenlin"], "Salbutamol": ["salbutmol", "salbutamal"], "Hydrocortisone": ["hydrocortizone"],
         "Diclofenac": ["diclofinac", "diclophenac"], "Midazolam": ["midazolem", "midazalam"], "Tranexamic acid": ["tranexamic"],
         "Nitroglycerin": ["nitroglycerine"], "Isosorbide dinitrate": ["isosorbid dinitrate"], "Morphine": ["morphin"], "Dextrose": ["dextros"], "Diazepam": ["diazepem"],
         "Pheniramine": ["phenyramine"], "Fentanyl": ["fentanil"], "Normal saline": ["normal salene"], "Ringer lactate": ["ringer lactat"]}
OPENERS = ["", "patient ", "gave ", "administered ", "we gave ", "", "started "]
HING = ["{drug} {dose} {unit} {route} diya", "patient ko {drug} {dose} {unit} {route} de diya", "{drug} {dose} {unit} {route} lagaya",
        "{drug} {dose} {unit} {route} diya at {time}"]


def _time(rng):
    return f"{rng.randint(6, 22):02d}:{rng.randint(0, 59):02d}"


def build(n_per_slice: int = 30, seed: int = 108) -> list[dict]:
    rng = random.Random(seed)
    cases: list[dict] = []

    def gold(drug, dose, unit, route, time=None, negated=False):
        return {"drug": drug, "dose": dose, "unit": unit, "route": route, "time": time, "negated": negated}

    for slice_name in ["clean", "brand", "hinglish", "asr_noise", "negation", "spoken_numbers", "multi_drug", "narrative"]:
        for _ in range(n_per_slice):
            drug, doses, unit, route, brands = rng.choice(DRUG_CASES)
            dose = rng.choice(doses)
            t = _time(rng)
            rs = rng.choice(ROUTE_SAY[route])
            us = rng.choice(UNIT_SAY[unit])
            ds = f"{dose:g}"
            name = drug.lower()
            if slice_name == "clean":
                text = f"{rng.choice(OPENERS)}{name} {ds} {us} {rs} at {t}"
                g = [gold(drug, dose, unit, route, t)]
            elif slice_name == "brand":
                text = f"{rng.choice(OPENERS)}{rng.choice(brands)} {ds} {us} {rs} at {t}"
                g = [gold(drug, dose, unit, route, t)]
            elif slice_name == "hinglish":
                text = rng.choice(HING).format(drug=rng.choice([name] + brands), dose=ds, unit=us, route=rs, time=t)
                g = [gold(drug, dose, unit, route, t if "{time}" in text or t in text else None)]
            elif slice_name == "asr_noise":
                text = f"{rng.choice(OPENERS)}{rng.choice(NOISE.get(drug, [name]))} {ds} {us} {rs} at {t}"
                g = [gold(drug, dose, unit, route, t)]
            elif slice_name == "negation":
                text = rng.choice([f"no {name} given", f"{name} not given due to allergy", f"withheld {name}", f"patient refused {name}"])
                g = [gold(drug, None, unit, None, None, True)]
            elif slice_name == "spoken_numbers":
                if dose in NUM_SAY:
                    ds = NUM_SAY[dose]
                text = f"{rng.choice(OPENERS)}{name} {ds} {us} {rs} at {t}"
                g = [gold(drug, dose, unit, route, t)]
            elif slice_name == "narrative":
                bp = f"bp {rng.randint(90, 170)}/{rng.randint(55, 100)}, pulse {rng.randint(60, 130)}"
                tpl = rng.choice([
                    "{v}. at {t} {ds} {us} {name} given {rs}. spo2 {s} after",
                    "{v}, spo2 {s}. {name} given, dose {ds} {us}, route {rs}, time {t}",
                    "on arrival {v}. {brand} {ds} {us} {rs} at {t} and reassessed, gcs 15",
                    "{v}. administered {ds} {us} of {name} {rs} at {t}. patient stable",
                ])
                text = tpl.format(v=bp, t=t, ds=ds, us=us, name=name, rs=rs, s=rng.randint(88, 99), brand=rng.choice(brands))
                g = [gold(drug, dose, unit, route, t)]
            else:
                d2, doses2, unit2, route2, _b = rng.choice([c for c in DRUG_CASES if c[0] != drug])
                dose2 = rng.choice(doses2)
                t2 = _time(rng)
                text = (f"gave {name} {ds} {us} {rs} at {t}, then {d2.lower()} {dose2:g} {rng.choice(UNIT_SAY[unit2])} "
                        f"{rng.choice(ROUTE_SAY[route2])} at {t2}")
                g = [gold(drug, dose, unit, route, t), gold(d2, dose2, unit2, route2, t2)]
            cases.append({"id": f"{slice_name}-{len(cases):03d}", "slice": slice_name, "text": text, "gold": g})
    return cases


def _match(pred: dict, g: dict) -> bool:
    if pred["drug"] != g["drug"] or pred["negated"] != g["negated"]:
        return False
    if g["negated"]:
        return True
    return pred["dose"] is not None and abs(float(pred["dose"]) - float(g["dose"])) < 1e-6 \
        and pred["unit"] == g["unit"] and pred["route"] == g["route"]


def run(n_per_slice: int = 30) -> dict:
    cases = build(n_per_slice)
    tp = fp = fn = 0
    field_hits = {k: [0, 0] for k in ("drug", "dose", "unit", "route", "time")}
    slices: dict[str, list[int]] = {}
    neg_ok = neg_tot = 0
    silent_critical = flagged_errors = 0
    lat = []
    errors = []
    for c in cases:
        t0 = time.perf_counter()
        r = extract(c["text"])
        lat.append((time.perf_counter() - t0) * 1000)
        preds = []
        for e in r["entities"]:
            if e["kind"] != "medication":
                continue
            f = e["fields"]
            preds.append({"drug": f["drug"]["value"], "dose": f["dose"]["value"], "unit": f["unit"]["value"],
                          "route": f["route"]["value"], "time": f["time"]["value"], "negated": e["negated"],
                          "flagged": any(x["level"] in ("critical", "warning") for x in e["flags"]) or e["confidence"] < 0.75})
        s = slices.setdefault(c["slice"], [0, 0, 0])
        used = set()
        for g in c["gold"]:
            hit = next((i for i, p in enumerate(preds) if i not in used and _match(p, g)), None)
            same_drug = next((i for i, p in enumerate(preds) if i not in used and p["drug"] == g["drug"]), None)
            if g["negated"]:
                neg_tot += 1
                if same_drug is not None and preds[same_drug]["negated"]:
                    neg_ok += 1
            cand = hit if hit is not None else same_drug
            if cand is not None:
                p = preds[cand]
                for k in field_hits:
                    if g["negated"] and k in ("dose", "unit", "route", "time"):
                        continue
                    if k == "time" and g["time"] is None:
                        continue
                    field_hits[k][1] += 1
                    pv, gv = p[k], g[k]
                    ok = (pv is not None and gv is not None and abs(float(pv) - float(gv)) < 1e-6) if k == "dose" else pv == gv
                    field_hits[k][0] += ok
            else:
                for k in ("drug",):
                    field_hits[k][1] += 1
            if hit is not None:
                tp += 1
                s[0] += 1
                used.add(hit)
            else:
                fn += 1
                s[2] += 1
                if cand is not None:
                    used.add(cand)
                    if preds[cand]["flagged"]:
                        flagged_errors += 1
                    else:
                        silent_critical += 1
                errors.append({"id": c["id"], "slice": c["slice"], "text": c["text"], "gold": g,
                               "pred": preds[cand] if cand is not None else None})
        extra = [p for i, p in enumerate(preds) if i not in used]
        fp += len(extra)
        s[1] += len(extra)
        for p in extra:
            if not p["flagged"]:
                silent_critical += 1
    prf = lambda t, f_p, f_n: (t / (t + f_p) if t + f_p else 0, t / (t + f_n) if t + f_n else 0)
    P, R = prf(tp, fp, fn)
    F1 = 2 * P * R / (P + R) if P + R else 0
    per_slice = {}
    for k, (t, f_p, f_n) in slices.items():
        p_, r_ = prf(t, f_p, f_n)
        per_slice[k] = {"precision": round(p_, 4), "recall": round(r_, 4), "f1": round(2 * p_ * r_ / (p_ + r_), 4) if p_ + r_ else 0,
                        "tp": t, "fp": f_p, "fn": f_n}
    total_gold = sum(len(c["gold"]) for c in cases)
    return {
        "cases": len(cases), "gold_entities": total_gold,
        "entity": {"precision": round(P, 4), "recall": round(R, 4), "f1": round(F1, 4), "tp": tp, "fp": fp, "fn": fn},
        "fields": {k: round(a / b, 4) if b else None for k, (a, b) in field_hits.items()},
        "slices": per_slice,
        "negation_accuracy": round(neg_ok / neg_tot, 4) if neg_tot else None,
        "silent_critical_error_rate": round(silent_critical / total_gold, 4),
        "flagged_error_rate": round(flagged_errors / total_gold, 4),
        "latency_ms": {"mean": round(statistics.mean(lat), 2), "p95": round(sorted(lat)[int(0.95 * len(lat)) - 1], 2), "max": round(max(lat), 2)},
        "errors": errors[:25],
        "note": "Synthetic, de-identified benchmark generated from templates; real-world pilot WER/F1 must be measured on recorded EMT audio.",
    }


def _perturb(word: str, rate: float, rng: random.Random) -> str:
    chars = list(word)
    out = []
    for ch in chars:
        r = rng.random()
        if ch == " " or r > rate:
            out.append(ch)
            continue
        op = rng.choice(["sub", "del", "dup", "swap"])
        if op == "sub":
            out.append(rng.choice("aeioumnrlst"))
        elif op == "dup":
            out.append(ch + ch)
        elif op == "swap" and out:
            out[-1], ch = ch, out[-1]
            out.append(ch)
        # del -> drop
    return "".join(out)


def stress(levels=(0.0, 0.05, 0.1, 0.15, 0.2, 0.3), n: int = 120, seed: int = 7) -> list[dict]:
    """Randomly corrupt drug names at a given character error rate (simulated ASR
    degradation) and measure drug-level recall and how many misses were flagged."""
    out = []
    for lvl in levels:
        rng = random.Random(seed)
        hit = flagged = silent = 0
        for _ in range(n):
            drug, doses, unit, route, brands = rng.choice(DRUG_CASES)
            name = rng.choice([drug.lower()] + brands)
            noisy = _perturb(name, lvl, rng)
            dose = rng.choice(doses)
            r = extract(f"gave {noisy} {dose:g} {unit.lower()} {rng.choice(ROUTE_SAY[route])} at 10:30")
            meds = [e for e in r["entities"] if e["kind"] == "medication"]
            if any(e["fields"]["drug"]["value"] == drug for e in meds):
                hit += 1
                e = next(e for e in meds if e["fields"]["drug"]["value"] == drug)
                if e["fields"]["drug"]["source"] == "fuzzy":
                    flagged += 1
            elif meds:
                silent += 1
        out.append({"char_error_rate": lvl, "drug_recall": round(hit / n, 4), "auto_corrected_and_flagged": round(flagged / n, 4),
                    "wrong_drug": round(silent / n, 4), "missed": round((n - hit - silent) / n, 4)})
    return out


def compare(n: int = 400) -> dict:
    """Held-out comparison: rules vs DistilBERT-only vs hybrid on the *test* split of the
    NER corpus (different seed, unseen real brands, harsher ASR corruption)."""
    from rapidfuzz import fuzz, process
    from .nlp import lexicon as L
    from .nlp import transformer_ner as TN
    from .nlp.ner import normalise
    from .nlp.ner_data import HOLDOUT_BRANDS, generate_corpus
    data = generate_corpus(n, "test")
    aliases = {a: c for c, m in L.DRUGS.items() for a in m["aliases"]}
    engines = ["rules"] + (["distilbert", "hybrid"] if TN.available() else [])
    res = {}
    for eng in engines:
        det = norm = gold_n = fp = unseen = unseen_hit = silent_wrong = 0
        t0 = time.perf_counter()
        for ex in data:
            golds = [g for g in ex["gold"] if not g["negated"]]
            gold_n += len(golds)
            if eng == "distilbert":
                spans = [s for s in TN.predict(normalise(ex["text"])) if s["label"] == "DRUG"]
                preds = []
                for s_ in spans:
                    b = process.extractOne(s_["text"], list(aliases), scorer=fuzz.ratio, score_cutoff=72)
                    preds.append({"text": s_["text"], "drug": aliases[b[0]] if b else None, "flagged": True})
            else:
                r = extract(ex["text"], use_model=(eng == "hybrid"))
                preds = [{"text": e["text"], "drug": e["fields"]["drug"]["value"],
                          "flagged": e["confidence"] < 0.75 or any(f["level"] in ("critical", "warning") for f in e["flags"])}
                         for e in r["entities"] if e["kind"] == "medication" and not e["negated"]]
            used = set()
            for g in golds:
                hold = g["surface"] in HOLDOUT_BRANDS
                unseen += hold
                j = next((i for i, p in enumerate(preds) if i not in used and (p["text"] in g["surface"] or g["surface"] in p["text"])), None)
                if j is None:
                    continue
                used.add(j)
                det += 1
                unseen_hit += hold
                if preds[j]["drug"] == g["drug"]:
                    norm += 1
                elif not preds[j]["flagged"] and g["drug"] in L.DRUGS:
                    silent_wrong += 1
            fp += len(preds) - len(used)
        ms = (time.perf_counter() - t0) * 1000 / len(data)
        p = det / (det + fp) if det + fp else 0
        r_ = det / gold_n if gold_n else 0
        res[eng] = {"detection_precision": round(p, 4), "detection_recall": round(r_, 4),
                    "detection_f1": round(2 * p * r_ / (p + r_), 4) if p + r_ else 0,
                    "normalised_correct": round(norm / gold_n, 4), "unseen_brand_surfaced": round(unseen_hit / unseen, 4) if unseen else None,
                    "silent_wrong": silent_wrong, "ms_per_dictation": round(ms, 2)}
    return {"engines": res, "sentences": len(data), "transformer": TN.status(),
            "note": "Held-out split: different seed, real Indian brands never seen in training or in the lexicon, heavier corruption."}


# ----------------------------------------------------------------------------- code-mixed Hindi / Kannada

def codemix(use_model: bool | None = None, heldout: bool = False) -> dict:
    """Hindi and Kannada (Latin and native script) handovers, with and without the Indic layer."""
    from .nlp import codemix_set
    CASES = codemix_set.HELDOUT if heldout else codemix_set.CASES

    def meds(r):
        out = []
        for e in r["entities"]:
            if e["kind"] != "medication" or e.get("negated") or e.get("status") == "withheld":
                continue
            f = {k: (v or {}).get("value") for k, v in e["fields"].items()}
            dose = f.get("dose")
            if dose is None and f.get("rate"):                       # oxygen: "6 L/min" is a rate
                m = re.match(r"([\d.]+)", str(f["rate"]))
                dose = float(m.group(1)) if m else None
            out.append((f.get("drug"), dose, f.get("unit"), f.get("route")))
        return out

    def same(p, g):
        return p[0] == g[0] and p[1] is not None and abs(float(p[1]) - g[1]) < 1e-6 and \
            (p[2] or "").lower() == (g[2] or "").lower() and (g[3] is None or p[3] == g[3])

    def score(layer: bool):
        by: dict = {}
        rows = []
        for c in CASES:
            r = extract(c["text"], use_model=use_model, indic_layer=layer)
            pm, gm = meds(r), list(c["meds"])
            tp = 0
            left = list(pm)
            for g in gm:
                hit = next((p for p in left if same(p, g)), None)
                if hit:
                    tp += 1
                    left.remove(hit)
            drug_ok = sum(1 for g in gm if any(p[0] == g[0] for p in pm))
            b = by.setdefault(c["lang"], {"cases": 0, "tp": 0, "fp": 0, "fn": 0, "drug": 0, "gold": 0, "age_ok": 0, "age_n": 0,
                                          "sex_ok": 0, "sex_n": 0, "exact_cases": 0})
            b["cases"] += 1; b["tp"] += tp; b["fp"] += len(pm) - tp; b["fn"] += len(gm) - tp
            b["drug"] += drug_ok; b["gold"] += len(gm)
            if c["age"] is not None:
                b["age_n"] += 1; b["age_ok"] += int(r["patient"].get("age") == c["age"])
            if c["sex"] is not None:
                b["sex_n"] += 1; b["sex_ok"] += int(r["patient"].get("sex") == c["sex"])
            ok = tp == len(gm) == len(pm)
            b["exact_cases"] += int(ok)
            rows.append({"lang": c["lang"], "text": c["text"], "understood": r["normalised"], "ok": ok,
                         "expected": [f"{g[0]} {g[1]:g} {g[2]}" + (f" {g[3]}" if g[3] else "") for g in gm] or ["(nothing given)"],
                         "got": [f"{p[0]} {p[1]:g} {p[2]} {p[3] or ''}".strip() if p[1] is not None else f"{p[0]}" for p in pm] or ["(nothing)"]})
        tot = {k: sum(b[k] for b in by.values()) for k in next(iter(by.values()))}
        def fin(b):
            p = b["tp"] / (b["tp"] + b["fp"]) if b["tp"] + b["fp"] else 0
            rc = b["tp"] / (b["tp"] + b["fn"]) if b["tp"] + b["fn"] else 0
            return {"cases": b["cases"], "precision": round(p, 3), "recall": round(rc, 3), "f1": round(2 * p * rc / (p + rc), 3) if p + rc else 0,
                    "drug_accuracy": round(b["drug"] / b["gold"], 3) if b["gold"] else None,
                    "age_accuracy": round(b["age_ok"] / b["age_n"], 3) if b["age_n"] else None,
                    "sex_accuracy": round(b["sex_ok"] / b["sex_n"], 3) if b["sex_n"] else None,
                    "cases_fully_correct": round(b["exact_cases"] / b["cases"], 3)}
        return {"by_language": {k: fin(v) for k, v in by.items()}, "overall": fin(tot), "rows": rows}

    with_layer, without = score(True), score(False)
    return {"cases": len(CASES), "with_indic": {k: v for k, v in with_layer.items() if k != "rows"},
            "without_indic": {k: v for k, v in without.items() if k != "rows"}, "rows": with_layer["rows"],
            "note": "Hand-written test sentences, not real patient data. The Indic layer is a readable lookup table plus script romanisation; no model or network."}
