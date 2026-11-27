"""
Synthetic BIO-labelled corpus for the DistilBERT clinical NER.

Labels: DRUG, DOSE, UNIT, ROUTE, TIME, PROC, NEG (negation cue).
Text is generated in FieldScribe's *normalised* form (lowercase, digits,
HH:MM times) because the model runs after the same normaliser as the rules.

Two splits are generated so the comparison is honest:
  train  - lexicon aliases, random ASR-style corruptions, and invented
           pseudo-brand names in drug position (teaches context, not spelling)
  test   - different seed, plus HELD-OUT real brand names that are not in the
           lexicon and never seen in training, and harsher corruptions
"""
from __future__ import annotations

import random

from . import lexicon as L

LABELS = ["O", "B-DRUG", "I-DRUG", "B-DOSE", "I-DOSE", "B-UNIT", "I-UNIT", "B-ROUTE", "I-ROUTE",
          "B-TIME", "I-TIME", "B-PROC", "I-PROC", "B-NEG", "I-NEG"]
L2I = {l: i for i, l in enumerate(LABELS)}

# real Indian brands deliberately NOT in the lexicon -> only seen at test time
HOLDOUT_BRANDS = {"zofer": "Ondansetron", "pacimol": "Paracetamol", "pantodac": "Pantoprazole", "levipil": "Levetiracetam"}

DOSES = {
    "mg": [0.5, 1, 2, 4, 5, 8, 10, 22.75, 40, 50, 75, 100, 150, 200, 300, 500, 650, 1000],
    "mcg": [25, 50, 100, 250, 500], "g": [1, 2], "mL": [50, 100, 250, 500, 1000],
}
UNIT_SAY = {"mg": ["mg", "milligram", "mgs"], "mcg": ["mcg", "micrograms"], "g": ["g", "gram", "gm"], "mL": ["ml", "millilitres", "cc"]}
ROUTE_SAY = [a for v in L.ROUTES.values() for a in v if len(a) > 1 and a not in ("tablet",)]
PROC_SAY = [a for v in L.PROCEDURES.values() for a in v["aliases"] if len(a) > 3 and a not in ("cannula", "joules")]
OPEN = ["", "gave ", "administered ", "patient given ", "we gave ", "started ", "pushed ", "patient ko ", "then ", "repeat "]
CLOSE = ["", " given", " diya", " de diya", " done", " stat", " slowly", " as per protocol"]
VITALS = ["bp {a}/{b}", "pulse {p}", "spo2 {s}", "rr {r}", "gcs {g}", "grbs {gl}", "pain {pn}/10", "hr {p}"]
NEG = ["no ", "not given ", "withheld ", "refused ", "held ", "nahi diya "]
SYL = ["ra", "zo", "lin", "mo", "tex", "cef", "vi", "dol", "pan", "fen", "mox", "zol", "dex", "pro", "ner", "tas", "ka", "qui", "lev"]


def _pseudo(rng) -> str:
    return "".join(rng.choice(SYL) for _ in range(rng.randint(2, 3)))


def _corrupt(w: str, rate: float, rng) -> str:
    out = []
    for ch in w:
        r = rng.random()
        if ch == " " or r > rate:
            out.append(ch)
        elif r < rate * .35:
            out.append(rng.choice("aeiou"))
        elif r < rate * .6:
            continue
        elif r < rate * .85:
            out.append(ch + ch)
        else:
            out.append(ch)
    s = "".join(out).strip()
    return s if len(s) >= 3 else w


class _B:
    def __init__(self):
        self.text, self.spans = "", []

    def add(self, s: str, label: str | None = None):
        if not s:
            return
        st = len(self.text)
        self.text += s
        if label:
            self.spans.append((st, st + len(s), label))

    def sp(self):
        if self.text and not self.text.endswith(" "):
            self.text += " "


def _drug_surface(split: str, rng):
    """Returns (surface, gold_canonical or None)."""
    r = rng.random()
    if split == "test" and r < 0.18:
        b = rng.choice(list(HOLDOUT_BRANDS))
        return b, HOLDOUT_BRANDS[b]
    canon = rng.choice(list(L.DRUGS))
    aliases = [a for a in L.DRUGS[canon]["aliases"] if a not in L.AMBIGUOUS]
    if split == "train" and r < 0.22:
        return _pseudo(rng), None                          # context learning
    w = rng.choice(aliases)
    if r < 0.45:
        w = _corrupt(w, 0.12 if split == "train" else 0.2, rng)
    return w, canon


def _time(rng):
    return f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}"


def _med(b: _B, split, rng, gold):
    surf, canon = _drug_surface(split, rng)
    neg = rng.random() < 0.12
    unit = rng.choice(list(DOSES))
    dose = rng.choice(DOSES[unit])
    t = _time(rng)
    if neg:
        b.add(rng.choice(NEG).strip(), "NEG"); b.sp()
        b.add(surf, "DRUG")
        gold.append({"drug": canon, "surface": surf, "negated": True})
        return
    b.add(rng.choice(OPEN))
    order = rng.random()
    if order < 0.15:  # "300 mg aspirin"
        b.add(f"{dose:g}", "DOSE"); b.sp(); b.add(rng.choice(UNIT_SAY[unit]), "UNIT"); b.sp(); b.add(surf, "DRUG")
    else:
        b.add(surf, "DRUG"); b.sp()
        if rng.random() < 0.9:
            b.add(f"{dose:g}", "DOSE")
            if rng.random() < 0.85:
                if rng.random() < 0.5:
                    b.sp()
                b.add(rng.choice(UNIT_SAY[unit]), "UNIT")
    if rng.random() < 0.8:
        b.sp(); b.add(rng.choice(ROUTE_SAY), "ROUTE")
    if rng.random() < 0.6:
        b.sp(); b.add(rng.choice(["at ", "@ ", "time "]))
        b.add(t, "TIME")
    b.add(rng.choice(CLOSE))
    gold.append({"drug": canon, "surface": surf, "negated": False})


def _proc(b: _B, rng):
    b.add(rng.choice(PROC_SAY), "PROC")
    if rng.random() < 0.4:
        b.sp(); b.add("at "); b.add(_time(rng), "TIME")


FILLER = ["patient stable", "reassessed after 5 minutes", "on arrival", "due to allergy", "route changed", "dose repeated after review",
          "no improvement", "condition improved", "shifted to ambulance", "family informed", "pain reduced", "awaiting orders",
          "monitoring continued", "after reassessment patient alert", "as per medical officer", "en route", "stable on transfer",
          "bystander cpr before arrival", "refused transport initially", "history of diabetes", "known asthmatic", "dose not repeated"]


def _filler(b: _B, rng):
    b.add(rng.choice(FILLER))  # natural narrative words are O


def _vital(b: _B, rng):
    v = rng.choice(VITALS).format(a=rng.randint(80, 190), b=rng.randint(45, 110), p=rng.randint(40, 150), s=rng.randint(80, 100),
                                  r=rng.randint(8, 40), g=rng.randint(3, 15), gl=rng.randint(30, 400), pn=rng.randint(0, 10))
    b.add(v)  # vitals are O: numbers here must NOT be tagged as doses


def generate_corpus(n: int, split: str = "train", seed: int = 7) -> list[dict]:
    rng = random.Random(seed + (0 if split == "train" else 1000))
    out = []
    for _ in range(n):
        b, gold = _B(), []
        if rng.random() < 0.25:
            b.add(rng.choice(["55 year old male, ", "rta case. ", "patient unconscious. ", "chest pain. ", "4 year old girl 16 kg. ",
                              "allergic to penicillin. ", "on scene, "]))
        k = rng.randint(1, 4)
        for i in range(k):
            r = rng.random()
            if r < 0.5:
                _med(b, split, rng, gold)
            elif r < 0.68:
                _proc(b, rng)
            elif r < 0.84:
                _vital(b, rng)
            else:
                _filler(b, rng)
            if i < k - 1:
                b.add(rng.choice([", ", ". ", " and ", ", then ", "; "]))
        out.append({"text": b.text.rstrip(), "spans": b.spans, "gold": gold})
    return out
