"""
FieldScribe hybrid clinical NER engine.

Pipeline (all offline, deterministic, explainable):
  1. normalise   - lowercase, code-mixed verb mapping, number-words -> digits,
                   spoken times ("at ten forty two") -> 10:42
  2. detect      - lexicon exact match (word-boundary) + fuzzy match (rapidfuzz)
                   for ASR misspellings; ambiguous brands are never auto-resolved
  3. attach      - per mention, a clause window is searched for dose, unit,
                   route, time, rate, device; negation cues mark "withheld"
  4. context     - patient (age/sex/weight/allergies/complaint/triage), vitals,
                   108 workflow timestamps, ABCDE/GCS/pupils
  5. safety      - reference-range, high-alert, controlled, allergy conflict,
                   duplicate administration, paediatric and unit-plausibility flags
  6. hybrid      - if a fine-tuned DistilBERT exists (backend/models/ner-distilbert, see
                   train_ner.py), its spans confirm rule hits and surface drug mentions the
                   rules missed; model-only finds are always flagged for EMT review
Every field carries its own confidence and a human-readable `evidence` trail.
The rule engine remains the source of truth for codes, doses and safety checks.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

try:
    from rapidfuzz import fuzz, process
    HAS_FUZZ = True
except Exception:  # pragma: no cover
    HAS_FUZZ = False

from . import lexicon as L
from . import transformer_ner as _tner

# ----------------------------------------------------------------- helpers

def _alias_index(table: dict, key: str = "aliases") -> list[tuple[str, str]]:
    out = []
    for canon, meta in table.items():
        aliases = meta[key] if isinstance(meta, dict) else meta
        for a in aliases:
            out.append((a.lower(), canon))
    out.sort(key=lambda x: -len(x[0]))  # longest first
    return out

DRUG_IDX = _alias_index(L.DRUGS)
PROC_IDX = _alias_index(L.PROCEDURES)
ROUTE_IDX = _alias_index(L.ROUTES)
UNIT_IDX = _alias_index(L.UNITS)
DEVICE_IDX = _alias_index(L.DEVICES)
FUZZY_CHOICES = {a: c for a, c in DRUG_IDX if len(a) >= 5 and " " not in a}
FUZZY_MULTI = {a: c for a, c in DRUG_IDX if " " in a and len(a) >= 9}


def _wb(alias: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])")

_DRUG_RX = [(a, c, _wb(a)) for a, c in DRUG_IDX]
_PROC_RX = [(a, c, _wb(a)) for a, c in PROC_IDX]
_ROUTE_RX = [(a, c, _wb(a)) for a, c in ROUTE_IDX]
_DEVICE_RX = [(a, c, _wb(a)) for a, c in DEVICE_IDX]
_UNIT_ALT = "|".join(re.escape(a) for a, _ in UNIT_IDX)
UNIT_LOOKUP = {a: c for a, c in UNIT_IDX}
DOSE_RX = re.compile(r"(?<![\d:.])(\d+(?:\.\d+)?)\s*(" + _UNIT_ALT + r")(?![a-z])")
BARE_NUM_RX = re.compile(r"(?<![\d:./])(\d+(?:\.\d+)?)(?![\d:./%])")
TIME_RX = re.compile(
    r"(?:\bat\s+|@\s*|\btime\s+|\baround\s+)?(?<![\d.])([01]?\d|2[0-3])[:.h ]([0-5]\d)(?:\s*(am|pm|hrs|hours|hr))?(?![\d])"
    r"|(?:\bat\s+)([01]\d|2[0-3])([0-5]\d)(?:\s*(?:hrs|hours|hr))?(?![\d.])"
)


def _parse_time(m: re.Match) -> str | None:
    if m.group(1) is not None:
        h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mi:02d}"
    if m.group(4) is not None:
        return f"{int(m.group(4)):02d}:{int(m.group(5)):02d}"
    return None


@dataclass
class Field:
    value: Any = None
    confidence: float = 0.0
    source: str = "missing"   # explicit | lexicon | fuzzy | default | inferred | missing


@dataclass
class Entity:
    id: str
    kind: str                       # medication | procedure
    text: str
    start: int
    end: int
    fields: dict[str, Field]
    confidence: float
    negated: bool = False
    status: str = "pending"         # pending | confirmed | rejected
    flags: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    codes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fields"] = {k: asdict(v) for k, v in self.fields.items()}
        return d


# ----------------------------------------------------------------- 1. normalise

_NUM_TOKEN = set(L.NUMBER_WORDS) | set(L.SCALE_WORDS) | {"point"}


def _words_to_number(tokens: list[str]) -> float | None:
    total, current, decimal, in_decimal = 0, 0, "", False
    for t in tokens:
        if t == "point":
            in_decimal = True
            continue
        if in_decimal:
            if t in L.NUMBER_WORDS and L.NUMBER_WORDS[t] < 10:
                decimal += str(int(L.NUMBER_WORDS[t]))
                continue
            return None
        if t in L.SCALE_WORDS:
            current = (current or 1) * L.SCALE_WORDS[t]
            if L.SCALE_WORDS[t] >= 1000:
                total += current
                current = 0
        elif t in L.NUMBER_WORDS:
            current += L.NUMBER_WORDS[t]
        else:
            return None
    val = total + current
    if decimal:
        val = float(f"{int(val)}.{decimal}")
    return val


def normalise(text: str) -> str:
    t = text.lower()
    t = t.replace("’", "'").replace("–", "-").replace("—", "-")
    t = re.sub(r"(\d),(\d{3})", r"\1\2", t)          # 1,000 -> 1000
    t = re.sub(r"(\d)\s*%", r"\1 percent", t)
    t = re.sub(r"\bo\s*2\b", "o2", t)
    t = re.sub(r"\bspo\s*2\b|\bsp o2\b|\bsats?\b|\bsaturation\b", "spo2", t)
    for k in sorted(L.CODE_MIX, key=len, reverse=True):
        t = re.sub(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", L.CODE_MIX[k], t)
    toks = re.findall(r"[a-z]+|\d+(?:\.\d+)?|[^\sa-z\d]+|\s+", t)
    out: list[str] = []
    i = 0
    while i < len(toks):
        if toks[i].strip() and toks[i] in _NUM_TOKEN and toks[i] != "point":
            j, words = i, []
            while j < len(toks) and (toks[j] in _NUM_TOKEN or (toks[j].isspace() and j + 1 < len(toks) and toks[j + 1] in _NUM_TOKEN)):
                if not toks[j].isspace():
                    words.append(toks[j])
                j += 1
            prev = "".join(out).rstrip()
            # spoken clock time: "at ten forty two" -> 10:42
            if prev.endswith(("at", "@")) and len(words) >= 2 and "point" not in words and words[0] in L.NUMBER_WORDS \
                    and 0 <= L.NUMBER_WORDS[words[0]] <= 23:
                mins = _words_to_number(words[1:])
                if mins is not None and 0 <= mins <= 59:
                    out.append(f"{int(L.NUMBER_WORDS[words[0]])}:{int(mins):02d}")
                    i = j
                    continue
            val = _words_to_number(words)
            if val is not None and not (words == ["half"]):
                out.append(str(int(val)) if float(val).is_integer() else str(val))
                i = j
                continue
        out.append(toks[i])
        i += 1
    t = "".join(out)
    t = re.sub(r"(\d+)\s+(\d{2})\s*(hrs|hours|hr)\b", r"\1:\2 \3", t)
    t = re.sub(r"(\d)\s*point\s*(\d)", r"\1.\2", t)
    t = re.sub(r"[ \t]+", " ", t).strip()
    return t


UNKNOWN_META = {"rxnorm": None, "class": "Unrecognised", "default_route": None, "default_unit": "mg", "range": None}

# ----------------------------------------------------------------- 2. detect

def _spans_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _find_drugs(t: str) -> list[dict]:
    found: list[dict] = []
    taken: list[tuple[int, int]] = []
    for alias, canon, rx in _DRUG_RX:
        for m in rx.finditer(t):
            sp = (m.start(), m.end())
            if any(_spans_overlap(sp, x) for x in taken):
                continue
            ambiguous = alias in L.AMBIGUOUS
            is_brand = alias not in (canon.lower(),) and alias not in [canon.lower().split()[0]]
            found.append({"canon": canon, "alias": alias, "start": sp[0], "end": sp[1],
                          "method": "ambiguous" if ambiguous else ("brand/alias" if is_brand else "exact"),
                          "score": 100})
            taken.append(sp)
    if HAS_FUZZ:
        for m in re.finditer(r"[a-z]{5,}", t):
            sp = (m.start(), m.end())
            if any(_spans_overlap(sp, x) for x in taken):
                continue
            word = m.group(0)
            if word in _COMMON_WORDS:
                continue
            hit = process.extractOne(word, list(FUZZY_CHOICES), scorer=fuzz.ratio, score_cutoff=84)
            if hit:
                found.append({"canon": FUZZY_CHOICES[hit[0]], "alias": word, "start": sp[0], "end": sp[1],
                              "method": "fuzzy", "score": hit[1], "matched": hit[0]})
                taken.append(sp)
        # two-word aliases ("normal salene", "ringer lactat")
        for m in re.finditer(r"(?=([a-z]{3,}\s[a-z]{3,}))", t):
            phrase = m.group(1)
            sp = (m.start(), m.start() + len(phrase))
            if any(_spans_overlap(sp, x) for x in taken):
                continue
            hit = process.extractOne(phrase, list(FUZZY_MULTI), scorer=fuzz.ratio, score_cutoff=86)
            if hit:
                found.append({"canon": FUZZY_MULTI[hit[0]], "alias": phrase, "start": sp[0], "end": sp[1],
                              "method": "fuzzy", "score": hit[1], "matched": hit[0]})
                taken.append(sp)
    return sorted(found, key=lambda x: x["start"])


_COMMON_WORDS = set("""patient given started applied minutes minute hours oxygen saline normal pressure
reached hospital ambulance breathing conscious stable vomiting history allergic allergy complaint
arrived contact departed handed scene dressing bleeding swelling seconds respiratory pulse
heart rhythm sinus tachycardia bradycardia litres liters around repeated another second third
after before during monitor transport position checked female male years refused declined
cannula infused improved reassessed status triage priority mechanism injury vehicle accident
because chewed tablet inhaled nebulised nebulized percent dextrose glucose against""".split())


def _find_procedures(t: str, drug_spans: list[tuple[int, int]]) -> list[dict]:
    out, taken = [], []
    for alias, canon, rx in _PROC_RX:
        for m in rx.finditer(t):
            sp = (m.start(), m.end())
            if any(_spans_overlap(sp, x) for x in taken):
                continue
            # "oxygen 4 litres" is a medication, keep only explicit therapy phrases
            if canon == "Oxygen therapy" and any(_spans_overlap(sp, d) for d in drug_spans):
                continue
            if alias == "cannula" and t[max(0, sp[0] - 6):sp[0]].endswith("nasal "):
                continue
            out.append({"canon": canon, "alias": alias, "start": sp[0], "end": sp[1]})
            taken.append(sp)
    return sorted(out, key=lambda x: x["start"])


# ----------------------------------------------------------------- 3. attach

_NEG_RX = re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(c.strip()) for c in L.NEGATION_CUES) + r")(?![a-z])")


def _negated(zone: str) -> bool:
    # a cue only counts if no other drug/verb resets scope between it and the mention
    return bool(_NEG_RX.search(zone))


_CLAUSE_BREAK = re.compile(r"\.(?=\s|$)|[;\n]|,\s*(?:then|and then|after that|later)\b|\bthen\b")
_SUB_BREAK = re.compile(r",|\band\b|\bstarted\b|\bgave\b|\bgiven\b")


def _clause_bounds(t: str, pos: int) -> tuple[int, int]:
    start = 0
    for m in _CLAUSE_BREAK.finditer(t):
        if m.end() <= pos:
            start = m.end()
        elif m.start() >= pos:
            return start, m.start()
    return start, len(t)


def _first(rx_list, s: str):
    best = None
    for alias, canon, rx in rx_list:
        m = rx.search(s)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), canon, alias)
    return best


def _attach_medication(t: str, mention: dict, next_start: int, prev_end: int, next_drug: int | None = None) -> Entity:
    cs, ce = _clause_bounds(t, mention["start"])
    win_end = min(ce, next_start)
    win_start = max(cs, prev_end)
    # "before" context only reaches back to the nearest sub-clause boundary
    seg = t[win_start:mention["start"]]
    cuts = [m.end() for m in re.finditer(r",", seg)]
    if cuts:
        win_start += cuts[-1]
    after = t[mention["end"]:win_end]
    # route/time may sit just past a procedure phrase ("500 ml iv started 09:30")
    after_wide = t[mention["end"]:min(ce, next_drug if next_drug is not None else ce)]
    before = t[win_start:mention["start"]]
    window = before + " " + t[mention["start"]:win_end]
    canon = mention["canon"]
    meta = L.DRUGS.get(canon) or UNKNOWN_META
    evidence: list[str] = []
    fields: dict[str, Field] = {}

    # drug
    if mention["method"] == "model-unknown":
        dconf = round(0.35 * mention.get("model_p", 0.5), 2)
        evidence.append(f"drug: DistilBERT tagged '{mention['alias']}' as a medication (p={mention.get('model_p', 0):.2f}) "
                        f"but it is not in the lexicon - confirm the drug name")
    elif mention["method"] == "model+fuzzy":
        dconf = round(0.4 + 0.3 * mention.get("model_p", 0.5) * mention["score"] / 100, 2)
        evidence.append(f"drug: missed by rules; DistilBERT tagged '{mention['alias']}' (p={mention.get('model_p', 0):.2f}), "
                        f"closest lexicon entry '{mention['matched']}' ({mention['score']:.0f}%)")
    elif mention["method"] == "exact":
        dconf = 0.98
        evidence.append(f"drug: exact lexicon match '{mention['alias']}'")
    elif mention["method"] == "brand/alias":
        dconf = 0.94
        evidence.append(f"drug: Indian brand/alias '{mention['alias']}' -> {canon}")
    elif mention["method"] == "fuzzy":
        dconf = round(0.55 + 0.4 * (mention["score"] - 84) / 16, 2)
        evidence.append(f"drug: fuzzy match '{mention['alias']}' ~ '{mention['matched']}' ({mention['score']:.0f}%) - likely ASR mis-hearing")
    else:
        dconf = 0.45
        evidence.append(f"drug: ambiguous alias '{mention['alias']}' - human must confirm")
    fields["drug"] = Field(canon, dconf, mention["method"])
    if mention.get("model_agrees"):
        evidence.append(f"DistilBERT agrees this is a medication (p={mention['model_agrees']:.2f})")

    # dose + unit: prefer after the drug, then before it ("300 mg aspirin")
    dm = DOSE_RX.search(after) or None
    dose_src = "after"
    if not dm:
        cands = list(DOSE_RX.finditer(before))
        dm = cands[-1] if cands else None
        dose_src = "before"
    rate = None
    if dm:
        val = float(dm.group(1))
        unit = UNIT_LOOKUP[dm.group(2)]
        if canon == "Oxygen" and unit in ("L", "L/min"):
            rate = Field(f"{val:g} L/min", 0.95, "explicit")
            fields["dose"] = Field(None, 1.0, "n/a")
            fields["unit"] = Field("L/min", 0.95, "explicit")
            evidence.append(f"rate: '{dm.group(0).strip()}' interpreted as flow rate")
        else:
            fields["dose"] = Field(val, 0.96, "explicit")
            fields["unit"] = Field(unit, 0.96, "explicit")
            evidence.append(f"dose: '{dm.group(0).strip()}' found {dose_src} drug name")
    else:
        bm = BARE_NUM_RX.search(after)
        if bm and not TIME_RX.match(after[bm.start():]):
            fields["dose"] = Field(float(bm.group(1)), 0.62, "explicit")
            fields["unit"] = Field(meta["default_unit"], 0.5, "default")
            evidence.append(f"dose: bare number '{bm.group(1)}' - unit defaulted to {meta['default_unit']}")
        else:
            fields["dose"] = Field(None, 0.0, "missing")
            fields["unit"] = Field(meta["default_unit"], 0.4, "default")
            evidence.append("dose: not stated")
    if rate:
        fields["rate"] = rate

    # route
    r = _first(_ROUTE_RX, after) or _first(_ROUTE_RX, after_wide) or _first(_ROUTE_RX, before)
    if r:
        fields["route"] = Field(r[1], 0.95, "explicit")
        evidence.append(f"route: '{r[2]}' -> {r[1]}")
    elif meta.get("default_route"):
        fields["route"] = Field(meta["default_route"], 0.55, "default")
        evidence.append(f"route: not stated - protocol default {meta['default_route']}")
    else:
        fields["route"] = Field(None, 0.0, "missing")
        evidence.append("route: not stated")

    # time
    tm = TIME_RX.search(after) or TIME_RX.search(after_wide) or TIME_RX.search(before)
    if tm:
        fields["time"] = Field(_parse_time(tm), 0.95, "explicit")
        evidence.append(f"time: '{tm.group(0).strip()}'")
    else:
        fields["time"] = Field(None, 0.4, "missing")
        evidence.append("time: not stated - will use capture time")

    # device
    dv = _first(_DEVICE_RX, after)
    if dv and (canon in ("Oxygen", "Salbutamol", "Ipratropium") or "cannula" in dv[1]):
        fields["device"] = Field(dv[1], 0.9, "explicit")

    # negation (look-behind in the clause, plus "X not given")
    neg_zone = t[cs:mention["start"]][-45:] + " | " + " ".join(t[mention["end"]:win_end].split()[:4])
    negated = _negated(neg_zone)
    if negated:
        evidence.append("negation cue in clause -> recorded as WITHHELD, not administered")

    weights = {"drug": 0.4, "dose": 0.25, "route": 0.15, "time": 0.1, "unit": 0.1}
    conf = sum(fields[k].confidence * w for k, w in weights.items() if k in fields)
    if fields["drug"].source in ("ambiguous",):
        conf = min(conf, 0.5)
    ent = Entity(
        id=str(uuid.uuid4())[:8], kind="medication", text=t[mention["start"]:mention["end"]],
        start=mention["start"], end=mention["end"], fields=fields, confidence=round(conf, 3),
        negated=negated, evidence=evidence,
        candidates=L.AMBIGUOUS.get(mention["alias"], []),
        codes={"rxnorm": meta.get("rxnorm"), "class": meta.get("class")},
    )
    return ent


def _attach_procedure(t: str, mention: dict, next_start: int) -> Entity:
    cs, ce = _clause_bounds(t, mention["start"])
    seg = t[cs:mention["start"]]
    cuts = [m.end() for m in re.finditer(r",", seg)]
    ws = cs + (cuts[-1] if cuts else 0)
    nxt_comma = t.find(",", mention["end"], ce)
    we = min(ce, max(next_start, mention["end"]))
    if nxt_comma != -1:
        # keep a trailing ", 18g left forearm at 10:45" style tail if it carries no new entity
        we = min(we, nxt_comma) if next_start < ce else we
    window = t[ws:we]
    meta = L.PROCEDURES[mention["canon"]]
    fields = {"procedure": Field(mention["canon"], 0.95, "exact")}
    evidence = [f"procedure: lexicon match '{mention['alias']}'" if "model" not in mention else
                f"procedure: DistilBERT tagged '{mention['alias']}' (p={mention['model']:.2f}) - verify"]
    tm = TIME_RX.search(window)
    fields["time"] = Field(_parse_time(tm), 0.95, "explicit") if tm else Field(None, 0.4, "missing")
    evidence.append(f"time: '{tm.group(0).strip()}'" if tm else "time: not stated")
    dv = _first(_DEVICE_RX, window)
    if dv:
        fields["device"] = Field(dv[1], 0.9, "explicit")
        evidence.append(f"device: '{dv[2]}'")
    j = re.search(r"(\d{2,3})\s*(?:j|joules)\b", window)
    if j:
        fields["energy"] = Field(f"{j.group(1)} J", 0.95, "explicit")
    site = re.search(r"\b(left|right)\s+(hand|forearm|arm|antecubital|leg|thigh|ankle|wrist)\b", window)
    if site:
        fields["site"] = Field(f"{site.group(1)} {site.group(2)}", 0.9, "explicit")
    neg_zone = t[cs:mention["start"]][-30:]
    negated = _negated(neg_zone)
    conf = 0.7 * fields["procedure"].confidence + 0.3 * fields["time"].confidence
    return Entity(id=str(uuid.uuid4())[:8], kind="procedure", text=t[mention["start"]:mention["end"]],
                  start=mention["start"], end=mention["end"], fields=fields, confidence=round(conf, 3),
                  negated=negated, evidence=evidence, codes={"snomed": meta["snomed"]})


# ----------------------------------------------------------------- 4. context

COMPLAINTS = {
    "Chest pain / suspected ACS": ["chest pain", "chest tightness", "stemi", "heart attack", "acs", "seene mein dard"],
    "Road traffic accident": ["rta", "road traffic accident", "bike accident", "car accident", "collision", "hit by", "two wheeler", "accident"],
    "Fall": ["fall from", "fell from", "fallen", "fall at home", "slipped"],
    "Breathlessness / asthma": ["breathless", "shortness of breath", "sob", "wheeze", "wheezing", "asthma", "saans"],
    "Hypoglycaemia": ["hypoglycemia", "hypoglycaemia", "low sugar", "hypo"],
    "Anaphylaxis": ["anaphylaxis", "allergic reaction", "urticaria", "angioedema"],
    "Seizure": ["seizure", "fits", "convulsion", "seizing", "mirgi"],
    "Stroke": ["stroke", "facial droop", "slurred speech", "hemiparesis", "weakness of left", "weakness of right"],
    "Snake bite": ["snake bite", "snakebite", "saanp"],
    "Burns": ["burn", "burns", "scald"],
    "Obstetric / labour": ["labour", "labor pains", "delivery", "pregnant", "prasav"],
    "Poisoning": ["poisoning", "organophosphate", "ingested", "overdose", "consumed poison"],
    "Cardiac arrest": ["cardiac arrest", "no pulse", "pulseless", "arrest"],
    "Unconscious / syncope": ["unconscious", "unresponsive", "syncope", "fainted", "collapsed"],
}

WORKFLOW = {
    "call_received": [r"call (?:received|came) (?:at )?", r"dispatch(?:ed)? (?:at )?"],
    "at_scene": [r"(?:reached|arrived (?:at)?|on) scene (?:at )?", r"scene arrival (?:at )?"],
    "patient_contact": [r"patient contact (?:at )?"],
    "left_scene": [r"(?:left|departed) (?:the )?scene (?:at )?", r"departed (?:at )?"],
    "at_hospital": [r"(?:reached|arrived (?:at)?) (?:the )?(?:hospital|ed|er|casualty)(?: at)? ", r"hospital arrival (?:at )?"],
    "handover": [r"hand(?:ed)? ?over (?:at )?", r"handover (?:at )?"],
    "last_known_well": [r"last (?:known|seen) (?:well|normal) (?:at |was )?", r"lkw (?:at )?", r"(?:symptom |stroke )?onset (?:at |was )?"],
}


def _extract_context(t: str) -> dict:
    ctx: dict[str, Any] = {}
    m = re.search(r"(\d{1,3})\s*(?:year|yr|yrs|years|y)(?:s)?(?:[- ]old)?|\bage\s*(\d{1,3})|(\d{1,3})\s*yo\b", t)
    if m:
        ctx["age"] = int(next(g for g in m.groups() if g))
    m = re.search(r"\b(\d{1,2})\s*(?:month|months)\s*old\b", t)
    if m:
        ctx["age"] = round(int(m.group(1)) / 12, 2)
    if re.search(r"\b(female|woman|lady|girl|mahila|she)\b", t):
        ctx["sex"] = "female"
    elif re.search(r"\b(male|man|boy|gentleman|he)\b", t):
        ctx["sex"] = "male"
    m = re.search(r"(\d{1,3}(?:\.\d)?)\s*(?:kg|kilo|kilos|kilogram)", t)
    if m:
        ctx["weight_kg"] = float(m.group(1))
    allergies = []
    if re.search(r"\bnkda\b|no known (?:drug )?allerg", t):
        ctx["allergies_status"] = "NKDA"
    for m in re.finditer(r"allerg(?:ic|y)\s+(?:to\s+)?([a-z ,/]+?)(?:[.;]|$|\s+(?:and|patient|given|bp|pulse))", t):
        for part in re.split(r",|/| and ", m.group(1)):
            p = part.strip()
            if p in L.ALLERGY_TERMS:
                allergies.append(L.ALLERGY_TERMS[p])
            else:
                for k, v in L.ALLERGY_TERMS.items():
                    if k in p:
                        allergies.append(v)
    if allergies:
        ctx["allergies"] = sorted(set(allergies))
        ctx["allergies_status"] = "documented"
    comps = [c for c, al in COMPLAINTS.items() if any(re.search(r"(?<![a-z])" + re.escape(a) + r"(?![a-z])", t) for a in al)]
    if comps:
        ctx["chief_complaints"] = comps
    m = re.search(r"\btriage\s*(?:category|code)?\s*(red|yellow|green|black)\b|\b(red|yellow|green|black)\s+(?:category|triage|tag)\b", t)
    if m:
        ctx["triage"] = (m.group(1) or m.group(2)).upper()
    elif re.search(r"\bpriority\s*(1|one)\b", t):
        ctx["triage"] = "RED"
    if re.search(r"\b(mlc|medico[- ]legal|police (?:informed|case))\b", t):
        ctx["medico_legal"] = True
    if re.search(r"\b(refused|refusal|against medical advice|lama|dama)\b", t):
        ctx["refusal_noted"] = True
    m = re.search(r"\b(?:veh(?:icle)?|ambulance|unit)\s*(?:no\.?|number)?\s*([a-z]{2}\s?\d{1,2}\s?[a-z]{0,2}\s?\d{3,4}|\d{3,4})\b", t)
    if m:
        ctx["vehicle"] = m.group(1).upper().replace(" ", "")
    return ctx


def _extract_vitals(t: str) -> list[dict]:
    out = []

    def add(name, value, unit, m, conf=0.95):
        cs, ce = _clause_bounds(t, m.start())
        tm = TIME_RX.search(t[cs:ce])
        out.append({"name": name, "value": value, "unit": unit, "start": m.start(), "end": m.end(),
                    "time": _parse_time(tm) if tm else None, "confidence": conf})

    for m in re.finditer(r"\b(?:bp|blood pressure)\s*(?:is|was|of)?\s*(\d{2,3})\s*(?:/|by|over)\s*(\d{2,3})", t):
        add("bp", f"{m.group(1)}/{m.group(2)}", "mmHg", m)
    for m in re.finditer(r"\b(?:pulse|hr|heart rate|pr)\s*(?:is|was|of|rate)?\s*(\d{2,3})", t):
        add("hr", int(m.group(1)), "/min", m)
    for m in re.finditer(r"\bspo2\s*(?:is|was|of|at)?\s*(\d{2,3})", t):
        add("spo2", int(m.group(1)), "%", m)
    for m in re.finditer(r"\b(?:rr|resp(?:iratory)? rate|respiration)\s*(?:is|was|of)?\s*(\d{1,2})", t):
        add("rr", int(m.group(1)), "/min", m)
    for m in re.finditer(r"\bgcs\s*(?:is|was|of)?\s*(\d{1,2})(?:\s*/\s*15)?", t):
        v = int(m.group(1))
        if 3 <= v <= 15:
            add("gcs", v, "/15", m)
    for m in re.finditer(r"\be\s*(\d)\s*v\s*(\d)\s*m\s*(\d)\b", t):
        add("gcs", int(m.group(1)) + int(m.group(2)) + int(m.group(3)), "/15", m, 0.97)
    for m in re.finditer(r"\b(?:grbs|cbg|rbs|blood sugar|sugar|glucose)\s*(?:is|was|of|level)?\s*(\d{2,3})(?!\s*(?:ml|mg|percent))", t):
        add("glucose", int(m.group(1)), "mg/dL", m)
    for m in re.finditer(r"\b(?:temp|temperature)\s*(?:is|was|of)?\s*(\d{2,3}(?:\.\d)?)", t):
        v = float(m.group(1))
        add("temp", v, "°F" if v > 50 else "°C", m)
    for m in re.finditer(r"\bpain(?: score)?\s*(?:is|was|of)?\s*(\d{1,2})\s*(?:/|out of|by)\s*10", t):
        add("pain", int(m.group(1)), "/10", m)
    for m in re.finditer(r"\bpupils?\s+([a-z ]{3,40}?)(?:[.,;]|$)", t):
        add("pupils", m.group(1).strip(), "", m, 0.85)
    return out


def _extract_workflow(t: str) -> dict:
    wf = {}
    for key, pats in WORKFLOW.items():
        for p in pats:
            m = re.search(p + r"((?:[01]?\d|2[0-3])[:.][0-5]\d(?:\s*(?:am|pm))?)", t)
            if m:
                tm = TIME_RX.search(m.group(1))
                if tm:
                    wf[key] = _parse_time(tm)
                    break
    return wf


# ----------------------------------------------------------------- 5. safety

VITAL_LIMITS = {"hr": (50, 120), "spo2": (94, 100), "rr": (10, 24), "gcs": (15, 15), "glucose": (70, 200)}


def safety_review(entities: list[Entity], ctx: dict, vitals: list[dict], history: list[dict] | None = None) -> list[dict]:
    alerts: list[dict] = []
    history = history or []
    allergies = set(ctx.get("allergies", []))
    age = ctx.get("age")
    seen: dict[str, list[Entity]] = {}
    for e in entities:
        if e.kind != "medication":
            continue
        drug = e.fields["drug"].value
        meta = L.DRUGS.get(drug, {})
        dose = e.fields.get("dose", Field()).value
        unit = e.fields.get("unit", Field()).value

        def flag(level, code, msg):
            item = {"level": level, "code": code, "message": msg, "entity_id": e.id}
            e.flags.append(item)
            alerts.append(item)

        if e.fields["drug"].source == "model-unknown":
            flag("critical", "UNKNOWN_DRUG", f"'{e.text}' looks like a medication (DistilBERT) but is not in the lexicon - confirm or correct the drug")
        if e.fields["drug"].source == "model+fuzzy":
            flag("warning", "MODEL_DETECTED", f"'{e.text}' found by DistilBERT, missed by rules; mapped to {drug} - verify")
        if e.fields["drug"].source in ("ambiguous",):
            flag("critical", "AMBIGUOUS_DRUG", f"'{e.text}' could mean {', '.join(e.candidates) or drug}; confirm drug before signing")
        if e.fields["drug"].source == "fuzzy":
            flag("warning", "ASR_UNCERTAIN", f"'{e.text}' auto-corrected to {drug}; verify")
        if e.negated:
            flag("info", "WITHHELD", f"{drug} documented as NOT given / withheld")
        rng = meta.get("range")
        if dose is not None and rng and unit == meta.get("default_unit"):
            if dose > rng[1] * 10 or dose < rng[0] / 10:
                flag("critical", "UNIT_IMPLAUSIBLE", f"{drug} {dose:g} {unit} is >10x outside reference - probable unit/decimal error")
            elif dose > rng[1]:
                flag("warning", "ABOVE_REFERENCE", f"{drug} {dose:g} {unit} above demo reference max {rng[1]:g} {unit}")
            elif dose < rng[0]:
                flag("info", "BELOW_REFERENCE", f"{drug} {dose:g} {unit} below demo reference min {rng[0]:g} {unit}")
        elif dose is not None and unit and meta.get("default_unit") and unit != meta.get("default_unit") \
                and not (meta.get("default_unit") == "mg" and unit in ("mcg", "g")):
            flag("warning", "UNIT_MISMATCH", f"{drug} recorded in {unit}; protocol unit is {meta['default_unit']}")
        if dose is None and drug != "Oxygen" and not e.negated:
            flag("warning", "DOSE_MISSING", f"{drug}: dose not captured")
        if e.negated:
            continue
        if meta.get("high_alert"):
            flag("info", "HIGH_ALERT", f"{drug} is a high-alert medication - double-check dose & route")
        if meta.get("controlled"):
            flag("info", "CONTROLLED", f"{drug} is a controlled substance - witness & batch number required")
        hit = allergies & set(meta.get("contra_allergy", [])) or ({drug.lower()} & allergies)
        if hit and not e.negated:
            flag("critical", "ALLERGY_CONFLICT", f"{drug} given but patient allergy documented: {', '.join(sorted(hit))}")
        if age is not None and age < 12:
            flag("warning", "PAEDIATRIC", f"Patient age {age} - verify weight-based dosing for {drug}")
        if e.fields.get("route") and e.fields["route"].source == "default":
            flag("info", "ROUTE_DEFAULTED", f"{drug}: route not dictated, defaulted to {e.fields['route'].value}")
        if not e.negated:
            prior = [p for p in seen.get(drug, [])] + [h for h in history if h.get("drug") == drug and not h.get("negated")]
            if prior:
                flag("warning", "DUPLICATE_DOSE", f"{drug} already recorded {len(prior)}x for this incident - confirm repeat dose is intended")
            seen.setdefault(drug, []).append(e)
        if e.confidence < 0.75 and not any(f["code"] == "AMBIGUOUS_DRUG" for f in e.flags):
            flag("warning", "LOW_CONFIDENCE", f"{drug}: overall confidence {e.confidence:.0%} - review before signing")
    for v in vitals:
        lim = VITAL_LIMITS.get(v["name"])
        if lim and isinstance(v["value"], (int, float)) and not (lim[0] <= v["value"] <= lim[1]):
            rng_txt = f"normal {lim[0]}" if lim[0] == lim[1] else f"outside {lim[0]}-{lim[1]}"
            alerts.append({"level": "warning", "code": "VITAL_OUT_OF_RANGE",
                           "message": f"{v['name'].upper()} {v['value']}{v['unit']} ({rng_txt})"})
        if v["name"] == "bp":
            sbp = int(str(v["value"]).split("/")[0])
            if sbp < 90 or sbp > 180:
                alerts.append({"level": "warning", "code": "VITAL_OUT_OF_RANGE", "message": f"BP {v['value']} mmHg - systolic outside 90-180"})
    if not ctx.get("allergies_status") and any(e.kind == "medication" and not e.negated for e in entities):
        alerts.append({"level": "info", "code": "ALLERGY_UNKNOWN", "message": "Allergy status not documented (SAMPLE)"})
    return alerts


# ----------------------------------------------------------------- hybrid merge

ALL_DRUG_ALIASES = {a: c for a, c in DRUG_IDX}
ALL_PROC_ALIASES = {a: c for a, c in PROC_IDX}


_MODEL_STOP = _COMMON_WORDS | {w for v in L.ROUTES.values() for a in v for w in a.split()} | \
    {w for v in L.UNITS.values() for a in v for w in a.split()} | set(L.CODE_MIX) | set("""after stable dose arrival due allergy route
    reassessed reassess review improved transfer informed orders protocol repeat repeated again given gave not no then and the with
    patient pt history known shifted monitoring condition family bystander initially before medical officer""".split())


def _whole_word(t: str, s: int, e: int) -> bool:
    return (s == 0 or not t[s - 1].isalnum()) and (e >= len(t) or not t[e].isalnum())


def _drug_context(t: str, sp: dict, spans: list[dict]) -> bool:
    """A model-only drug needs a dose, unit or route right after it (or a dose just before)."""
    after = t[sp["end"]:sp["end"] + 28]
    if DOSE_RX.search(after) or BARE_NUM_RX.match(after.strip() or "x") or _first(_ROUTE_RX, after):
        return True
    return any(o["label"] in ("DOSE", "UNIT", "ROUTE") and 0 <= o["start"] - sp["end"] <= 28 for o in spans) or \
        bool(DOSE_RX.search(t[max(0, sp["start"] - 14):sp["start"]]))


def _merge_model(t: str, drugs: list[dict], procs: list[dict], spans: list[dict]):
    """Rules stay authoritative for codes and fields. DistilBERT can (a) confirm a rule
    mention, (b) surface a medication or procedure the rules missed - always flagged for review."""
    if not spans:
        return drugs, procs
    taken = [(d["start"], d["end"]) for d in drugs] + [(p["start"], p["end"]) for p in procs]
    for sp in spans:
        rng = (sp["start"], sp["end"])
        if sp["label"] == "DRUG":
            hit = next((d for d in drugs if _spans_overlap(rng, (d["start"], d["end"]))), None)
            if hit:
                hit["model_agrees"] = sp["score"]
                continue
            surf = sp["text"].strip()
            if any(_spans_overlap(rng, x) for x in taken) or len(surf) < 3 or not _whole_word(t, sp["start"], sp["end"]):
                continue
            if any(w in _MODEL_STOP for w in surf.split()) or not _drug_context(t, sp, spans):
                continue
            best = process.extractOne(surf, list(ALL_DRUG_ALIASES), scorer=fuzz.ratio, score_cutoff=72) if HAS_FUZZ else None
            m = {"alias": surf, "start": sp["start"], "end": sp["end"], "model_p": sp["score"]}
            if best and sp["score"] >= 0.7:
                m.update({"canon": ALL_DRUG_ALIASES[best[0]], "method": "model+fuzzy", "score": best[1], "matched": best[0]})
            elif not best and sp["score"] >= 0.85:
                m.update({"canon": surf.title(), "method": "model-unknown", "score": 0})
            else:
                continue
            drugs.append(m)
            taken.append(rng)
        elif sp["label"] == "PROC":
            if any(_spans_overlap(rng, x) for x in taken) or sp["score"] < 0.6:
                continue
            best = process.extractOne(sp["text"], list(ALL_PROC_ALIASES), scorer=fuzz.ratio, score_cutoff=75) if HAS_FUZZ else None
            if best:
                procs.append({"canon": ALL_PROC_ALIASES[best[0]], "alias": sp["text"], "start": sp["start"], "end": sp["end"],
                              "model": sp["score"]})
                taken.append(rng)
    drugs.sort(key=lambda x: x["start"])
    procs.sort(key=lambda x: x["start"])
    return drugs, procs


# ----------------------------------------------------------------- public API

def _fval(f):
    return f.get("value") if isinstance(f, dict) else getattr(f, "value", None)


def _fset(f, v):
    if isinstance(f, dict):
        f["value"] = v
    else:
        f.value = v


def extract(text: str, history: list[dict] | None = None, use_model: bool | None = None, indic_layer: bool = True) -> dict:
    from . import indic
    mix = indic.to_english(text) if indic_layer else {"text": text, "mixed": False, "script": "latin", "replaced": []}          # Hindi / Kannada (any script) → English clinical text; plain English passes through
    t = normalise(mix["text"])
    drugs = _find_drugs(t)
    drug_spans = [(d["start"], d["end"]) for d in drugs]
    procs = _find_procedures(t, drug_spans)
    entities: list[Entity] = []
    all_starts = sorted([d["start"] for d in drugs] + [p["start"] for p in procs])
    model_spans = _tner.predict(t) if (_tner.available() if use_model is None else (use_model and _tner.available())) else []
    drugs, procs = _merge_model(t, drugs, procs, model_spans)
    drugs = [d for d in drugs if not re.search(r"(allerg(?:ic|y|ies)\s*(?:to|:)?\s*(?:[a-z]+\s*(?:,|and|/)\s*)*)$", t[max(0, d["start"] - 40):d["start"]])]
    all_starts = sorted([d["start"] for d in drugs] + [p["start"] for p in procs])
    # a route-like procedure straight after a drug ("salbutamol nebulisation 5 mg") belongs to that drug's phrase
    route_like = {p["start"] for p in procs if re.match(r"nebuli[sz]", t[p["start"]:p["end"]])}
    for i, d in enumerate(drugs):
        nxt = next((s for s in all_starts if s > d["start"] and not (s in route_like and s - d["end"] <= 3)), len(t))
        prev_end = drugs[i - 1]["end"] if i > 0 else 0
        nxt_drug = drugs[i + 1]["start"] if i + 1 < len(drugs) else None
        entities.append(_attach_medication(t, d, nxt, prev_end, nxt_drug))
    for p in procs:
        nxt = next((s for s in all_starts if s > p["start"]), len(t))
        entities.append(_attach_procedure(t, p, nxt))
    entities.sort(key=lambda e: e.start)
    for e in entities:   # "oxygen ... applied/lagaya/haakiddini": oxygen is always inhaled, never topical
        rf = e.fields.get("route") if isinstance(getattr(e, "fields", None), dict) else None
        df = e.fields.get("drug") if isinstance(getattr(e, "fields", None), dict) else None
        if df and rf and _fval(df) == "Oxygen" and _fval(rf) == "TOP":
            _fset(rf, "INH")
    ctx = _extract_context(t)
    vitals = _extract_vitals(t)
    workflow = _extract_workflow(t)
    alerts = safety_review(entities, ctx, vitals, history)
    abcde = _abcde(t)
    return {
        "input": text,
        "normalised": t,
        "language": {"code_mixed": mix["mixed"], "language": mix.get("language"), "script": mix["script"],
                     "translated": [{"from": a, "to": b} for a, b in mix["replaced"]][:40]},
        "entities": [e.to_dict() for e in entities],
        "patient": ctx,
        "vitals": vitals,
        "workflow": workflow,
        "abcde": abcde,
        "alerts": alerts,
        "stats": {
            "medications": sum(1 for e in entities if e.kind == "medication"),
            "procedures": sum(1 for e in entities if e.kind == "procedure"),
            "vitals": len(vitals),
            "needs_review": sum(1 for e in entities if e.confidence < 0.75 or any(f["level"] == "critical" for f in e.flags)),
            "mean_confidence": round(sum(e.confidence for e in entities) / len(entities), 3) if entities else None,
        },
        "engine": {"name": "fieldscribe-hybrid-ner", "version": "2.2", "fuzzy": HAS_FUZZ,
                   "transformer": _tner.available(), "model_spans": model_spans},
    }


def _abcde(t: str) -> dict:
    def pick(pats):
        for p in pats:
            m = re.search(p, t)
            if m:
                return m.group(0)
        return None
    return {
        "A": pick([r"airway (?:patent|clear|compromised|obstructed)", r"patent airway", r"(?:intubated|igel|i-gel|lma)"]),
        "B": pick([r"(?:breathing|air entry) [a-z ]{3,25}", r"wheez\w*", r"bilateral air entry"]),
        "C": pick([r"(?:capillary refill|crt) [<>]?\s*\d+ ?(?:sec|seconds|s)", r"(?:bleeding|haemorrhage|hemorrhage) [a-z ]{3,20}", r"pulse (?:weak|thready|strong|absent)"]),
        "D": pick([r"gcs \d{1,2}", r"\bavpu \w+", r"(?:alert|responds to voice|responds to pain|unresponsive)", r"pupils [a-z ]{3,25}"]),
        "E": pick([r"(?:abrasion|laceration|deformity|swelling|fracture|burns?)[a-z ]{0,30}"]),
    }
