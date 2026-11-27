"""
Real-world 108 field features:

* Right-hospital routing: rank receiving hospitals by the capability the patient needs, then drive time.
* Medico-legal case (MLC) detection and police-intimation record.
* ABHA (Ayushman Bharat Health Account, ABDM) identity linking with format checks.
* Refusal of care / LAMA with on-screen signature, sealed into the audit ledger.
* Mass-casualty incident (MCI) mode with START triage tags.
* Record access log (who viewed or exported a patient record), as the DPDP Act 2023 expects.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import audit, db, routing, services

# ----------------------------------------------------------------------------- hospital capabilities

CAP_LABEL = {
    "stroke": "Stroke unit (CT + thrombolysis)", "pci": "Cath lab (primary PCI)", "trauma": "Trauma centre",
    "neurosurgery": "Neurosurgery", "burns": "Burns unit", "paeds": "Paediatric emergency", "obstetric": "Obstetric emergency",
    "icu": "ICU beds", "toxicology": "Poison management", "ed": "24×7 emergency",
}

_DEFAULT_CAPS = {
    "H1": ["ed", "trauma", "burns", "icu", "toxicology", "obstetric", "paeds"],
    "H2": ["ed", "stroke", "neurosurgery", "trauma", "icu"],
    "H3": ["ed", "pci", "icu"],
    "H4": ["ed", "obstetric", "paeds", "toxicology"],
    "H5": ["ed", "pci", "stroke", "trauma", "icu", "paeds", "obstetric", "toxicology"],
}
HOSP_FILE = Path(os.environ.get("FIELDSCRIBE_HOSPITALS", Path(__file__).resolve().parent.parent / "hospitals.json"))


def hospitals() -> list[dict]:
    """Hospital directory. Edit backend/hospitals.json to match your 108 control room's list."""
    if HOSP_FILE.exists():
        try:
            data = json.loads(HOSP_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    return [dict(h, capabilities=_DEFAULT_CAPS.get(h["id"], ["ed"])) for h in services.HOSPITALS]


def _needs(inc: dict, condition: str | None) -> list[tuple[str, str]]:
    """(capability, why) pairs the receiving hospital must have, from the condition and the record."""
    text = _incident_text(inc)
    pat = inc.get("patient") or {}
    out: list[tuple[str, str]] = []
    c = (condition or "").lower()
    if "stroke" in c:
        out.append(("stroke", "Suspected stroke: needs CT and thrombolysis within the window"))
    if "chest" in c or "acs" in c or "arrest" in c:
        out.append(("pci", "Possible heart attack: primary PCI saves the most muscle"))
    if "trauma" in c or re.search(r"\b(rta|accident|fall from|fracture|stab|assault)\b", text):
        out.append(("trauma", "Major trauma: needs a trauma team"))
        if re.search(r"\b(head injury|gcs [3-9]\b|unconscious|skull)", text):
            out.append(("neurosurgery", "Head injury: neurosurgery may be needed"))
    if re.search(r"\bburn", text):
        out.append(("burns", "Burns: needs a burns unit"))
    if re.search(r"\b(poison|insecticide|pesticide|organophosph|overdose|ingest)", text):
        out.append(("toxicology", "Poisoning: needs antidotes and poison management"))
    if re.search(r"\b(pregnan|labou?r|antepartum|postpartum|eclampsia|delivery)\b", text):
        out.append(("obstetric", "Pregnancy-related: needs obstetric emergency care"))
    age = pat.get("age")
    if isinstance(age, (int, float)) and age < 14:
        out.append(("paeds", "Child: paediatric emergency preferred"))
    if (inc.get("triage") == "RED") and not any(k == "icu" for k, _ in out):
        out.append(("icu", "Red triage: ICU bed likely"))
    return out or [("ed", "Any 24×7 emergency department")]


def destinations(iid: str) -> dict:
    from . import completeness
    inc = services.get_incident(iid)
    if not inc:
        raise KeyError(iid)
    cond = completeness.check(inc).get("condition")
    needs = _needs(inc, cond)
    need_keys = [k for k, _ in needs]
    here = (inc.get("lat"), inc.get("lng"))
    online = services.is_online()
    rows = []
    for h in hospitals():
        caps = set(h.get("capabilities") or [])
        have = [k for k in need_keys if k in caps]
        missing = [k for k in need_keys if k not in caps]
        if here[0] is not None and here[1] is not None:
            r = routing.route((here[0], here[1]), (h["lat"], h["lng"]), online)
            eta = round(r["duration_s"] / 60)
            src = r.get("source")
            dist = round(r["distance_m"] / 1000, 1)
        else:
            eta, src, dist = None, None, None
        critical_missing = [k for k in missing if k in ("stroke", "pci", "trauma", "burns", "neurosurgery")]
        score = len(have) * 100 - len(critical_missing) * 250 - (eta or 30)
        rows.append({"id": h["id"], "name": h["name"], "type": h.get("type"), "eta_min": eta, "distance_km": dist, "route_source": src,
                     "has": have, "missing": missing, "capabilities": sorted(caps), "score": score,
                     "suitable": not critical_missing, "current": inc.get("destination") == h["name"]})
    rows.sort(key=lambda r: (-r["score"], r["eta_min"] or 999))
    nearest = min((r for r in rows if r["eta_min"] is not None), key=lambda r: r["eta_min"], default=None)
    best = rows[0] if rows else None
    note = None
    if best and nearest and nearest["id"] != best["id"] and not nearest["suitable"]:
        note = (f"The nearest hospital ({nearest['name']}, {nearest['eta_min']} min) can't provide "
                f"{', '.join(CAP_LABEL[k].split(' (')[0].lower() for k in nearest['missing'] if k in ('stroke','pci','trauma','burns','neurosurgery'))}. "
                f"Going straight to {best['name']} avoids a second transfer.")
    return {"condition": cond, "needs": [{"key": k, "label": CAP_LABEL[k], "why": w} for k, w in needs],
            "hospitals": rows, "recommended": best["id"] if best else None, "note": note,
            "directory": "Edit backend/hospitals.json to match your control room's directory."}


# ----------------------------------------------------------------------------- medico-legal

MLC_RULES = [
    (r"\b(rta|road traffic|accident|collision|hit by|run over|bike skid|two[- ]wheeler)\b", "Road traffic accident"),
    (r"\b(assault|stab|stabbed|fight|attacked|beaten|gunshot|knife)\b", "Assault / injury by another person"),
    (r"\bburn", "Burns"),
    (r"\b(poison|insecticide|pesticide|organophosph|overdose|consumed .*tablets)\b", "Poisoning / overdose"),
    (r"\b(fall from height|fell from|fall from)\b", "Fall from height"),
    (r"\b(hanging|strangulat)\b", "Hanging / strangulation"),
    (r"\b(drown)", "Drowning"),
    (r"\b(electrocut|electric shock)\b", "Electrocution"),
    (r"\b(snake ?bite|dog ?bite|animal bite)\b", "Bite (check local MLC rules)"),
    (r"\b(found unconscious|unknown cause|brought dead|unidentified)\b", "Unknown cause / found unconscious"),
]


def _incident_text(inc: dict) -> str:
    parts = [inc.get("complaint") or "", inc.get("place") or ""]
    for r in db.q("SELECT final_text FROM records WHERE incident_id=?", (inc["id"],)):
        parts.append(r["final_text"] or "")
    return " ".join(parts).lower()


def mlc_suggest(inc: dict) -> list[str]:
    text = _incident_text(inc)
    return [label for rx, label in MLC_RULES if re.search(rx, text)]


# ----------------------------------------------------------------------------- ABHA

ABHA_NUM = re.compile(r"^\d{14}$")
ABHA_ADDR = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._]{2,31}@(abdm|sbx)$")


def check_abha(v: str) -> dict:
    v = (v or "").strip()
    digits = re.sub(r"[\s-]", "", v)
    if ABHA_NUM.match(digits):
        pretty = f"{digits[:2]}-{digits[2:6]}-{digits[6:10]}-{digits[10:]}"
        return {"ok": True, "kind": "number", "value": pretty}
    if ABHA_ADDR.match(v):
        return {"ok": True, "kind": "address", "value": v.lower()}
    return {"ok": False, "error": "Enter a 14-digit ABHA number (e.g. 91-1234-5678-9012) or an ABHA address like name@abdm"}


def mask_abha(v: str | None) -> str | None:
    if not v:
        return v
    if "@" in v:
        n, d = v.split("@", 1)
        return n[:2] + "•" * max(1, len(n) - 2) + "@" + d
    return "••-••••-••••-" + v[-4:]


# ----------------------------------------------------------------------------- legal record (patient identity, MLC, refusal)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def legal(iid: str) -> dict:
    r = db.q1("SELECT legal FROM incidents WHERE id=?", (iid,))
    return db.jload(r["legal"], {}) if r and r["legal"] else {}


def update_patient(iid: str, fields: dict, actor: str) -> dict:
    inc = db.q1("SELECT patient FROM incidents WHERE id=?", (iid,))
    if not inc:
        raise KeyError(iid)
    pat = db.jload(inc["patient"], {})
    log: dict = {}
    if "abha" in fields:
        if fields["abha"]:
            chk = check_abha(fields["abha"])
            if not chk["ok"]:
                raise ValueError(chk["error"])
            pat["abha"], pat["abha_kind"], pat["abha_verified"] = chk["value"], chk["kind"], False
            log["abha_linked"] = mask_abha(chk["value"])
        else:
            for k in ("abha", "abha_kind", "abha_verified"):
                pat.pop(k, None)
            log["abha_removed"] = True
    for k in ("name", "relative_name", "relative_phone", "address"):
        if k in fields:
            v = (fields[k] or "").strip()[:120]
            if v:
                pat[k] = v
            else:
                pat.pop(k, None)
            log[k] = "updated" if v else "cleared"     # the ledger records that it changed, not the personal detail
    if "age" in fields and fields["age"] not in (None, ""):
        pat["age"] = int(fields["age"])
        log["age"] = pat["age"]
    if fields.get("sex") in ("male", "female", "other", "unknown"):
        pat["sex"] = fields["sex"]
        log["sex"] = pat["sex"]
    t = _now()
    with db.tx() as c:
        c.execute("UPDATE incidents SET patient=?, updated_at=?, version=version+1 WHERE id=?", (json.dumps(pat), t, iid))
        audit.append("PATIENT_UPDATED", iid, log, actor, ts=t, con=c)
        services._enqueue(c, "incident", iid, iid, {"op": "patient", **{k: v for k, v in pat.items()}}, datetime.now(timezone.utc))
    return services.get_incident(iid)


def set_mlc(iid: str, body: dict, actor: str) -> dict:
    lg = legal(iid)
    if not body.get("is_mlc"):
        lg["mlc"] = {"is_mlc": False, "decided_by": actor, "decided_at": _now(), "reason": (body.get("reason") or "")[:200]}
    else:
        lg["mlc"] = {
            "is_mlc": True, "category": (body.get("category") or "")[:80], "police_station": (body.get("police_station") or "")[:80],
            "informed": bool(body.get("informed")), "informed_at": (body.get("informed_at") or "")[:5],
            "officer": (body.get("officer") or "")[:80], "gd_number": (body.get("gd_number") or "")[:40],
            "brought_by": (body.get("brought_by") or "")[:80], "belongings": (body.get("belongings") or "")[:200],
            "decided_by": actor, "decided_at": _now(),
        }
    t = _now()
    with db.tx() as c:
        c.execute("UPDATE incidents SET legal=?, updated_at=?, version=version+1 WHERE id=?", (json.dumps(lg), t, iid))
        audit.append("MLC_RECORDED", iid, {k: v for k, v in lg["mlc"].items() if k not in ("belongings",)}, actor, ts=t, con=c)
        services._enqueue(c, "incident", iid, iid, {"op": "mlc", **lg["mlc"]}, datetime.now(timezone.utc))
    return lg


_SIG = re.compile(r"^data:image/png;base64,[A-Za-z0-9+/=]{100,400000}$")


def set_refusal(iid: str, body: dict, actor: str) -> dict:
    sig = body.get("signature") or ""
    if not _SIG.match(sig):
        raise ValueError("A signature from the patient or their representative is required")
    if not body.get("risks_explained"):
        raise ValueError("Confirm that the risks of refusing were explained")
    if not (body.get("signed_by") or "").strip():
        raise ValueError("Enter who signed")
    if body.get("capacity") not in ("yes", "representative"):
        raise ValueError("Record whether the patient has decision-making capacity, or who is deciding for them")
    sig_hash = hashlib.sha256(sig.encode()).hexdigest()
    lg = legal(iid)
    lg["refusal"] = {
        "what": body.get("what") if body.get("what") in ("transport", "treatment", "both") else "both",
        "reason": (body.get("reason") or "")[:300], "risks_explained": True, "capacity": body["capacity"],
        "signed_by": body["signed_by"].strip()[:80], "relation": (body.get("relation") or "Self")[:40],
        "witness": (body.get("witness") or "")[:80], "advice_given": (body.get("advice_given") or "")[:300],
        "signature": sig, "signature_sha256": sig_hash, "recorded_by": actor, "recorded_at": _now(),
    }
    t = _now()
    with db.tx() as c:
        c.execute("UPDATE incidents SET legal=?, updated_at=?, version=version+1 WHERE id=?", (json.dumps(lg), t, iid))
        audit.append("CARE_REFUSED", iid, {k: v for k, v in lg["refusal"].items() if k != "signature"}, actor, ts=t, con=c)
        services._enqueue(c, "incident", iid, iid, {"op": "refusal", **{k: v for k, v in lg["refusal"].items() if k != "signature"}},
                          datetime.now(timezone.utc))
    return lg


# ----------------------------------------------------------------------------- access log (DPDP Act 2023)

def log_access(iid: str, user: dict | None, action: str) -> None:
    if not user or not iid:
        return
    t = datetime.now(timezone.utc)
    recent = db.q1("SELECT at FROM access_log WHERE incident_id=? AND user_id=? AND action=? ORDER BY id DESC LIMIT 1",
                   (iid, user["id"], action))
    if recent and recent["at"] > (t - timedelta(minutes=10)).isoformat(timespec="seconds"):
        return       # one entry per person per 10 minutes per action; screens refresh often
    with db.tx() as c:
        c.execute("INSERT INTO access_log(incident_id,user_id,user_name,role,action,at) VALUES(?,?,?,?,?,?)",
                  (iid, user["id"], user["name"], user["role"], action, t.isoformat(timespec="seconds")))


def access(iid: str) -> list[dict]:
    return db.q("SELECT user_name, role, action, at FROM access_log WHERE incident_id=? ORDER BY id DESC LIMIT 200", (iid,))


# ----------------------------------------------------------------------------- mass-casualty incident

def mci_active() -> dict | None:
    ev = db.q1("SELECT * FROM mci_events WHERE closed_at IS NULL ORDER BY started_at DESC LIMIT 1")
    if not ev:
        return None
    pts = db.q("SELECT id, dispatch_id, mci_tag, triage, complaint, status, destination, created_at, patient FROM incidents "
               "WHERE mci_id=? ORDER BY created_at", (ev["id"],))
    for p in pts:
        p["patient"] = db.jload(p["patient"], {})
    counts = {k: sum(1 for p in pts if p["triage"] == k) for k in ("RED", "YELLOW", "GREEN", "BLACK")}
    moved = sum(1 for p in pts if p["status"] in ("transporting", "handed_over", "closed"))
    return {**ev, "patients": pts, "counts": counts, "total": len(pts), "transported": moved}


def mci_start(name: str, place: str, actor: str, lat=None, lng=None) -> dict:
    if mci_active():
        raise ValueError("A mass-casualty incident is already active. Close it before starting another.")
    eid = "MCI-" + uuid.uuid4().hex[:5].upper()
    t = _now()
    with db.tx() as c:
        c.execute("INSERT INTO mci_events(id,name,place,lat,lng,started_at,started_by) VALUES(?,?,?,?,?,?,?)",
                  (eid, (name or "Mass casualty incident")[:80], (place or "")[:120], lat, lng, t, actor))
        audit.append("MCI_DECLARED", None, {"mci_id": eid, "name": name, "place": place}, actor, ts=t, con=c)
    return mci_active()


def mci_add(eid: str, triage: str, note: str, actor: str, start: dict | None = None) -> dict:
    ev = db.q1("SELECT * FROM mci_events WHERE id=? AND closed_at IS NULL", (eid,))
    if not ev:
        raise KeyError(eid)
    if triage not in ("RED", "YELLOW", "GREEN", "BLACK"):
        raise ValueError("Triage must be RED, YELLOW, GREEN or BLACK")
    n = db.q1("SELECT COUNT(*) n FROM incidents WHERE mci_id=?", (eid,))["n"] + 1
    tag = f"T-{n:02d}"
    inc = services.create_incident({"complaint": f"MCI casualty {tag}" + (f": {note.strip()[:80]}" if note and note.strip() else ""),
                                    "triage": triage, "place": ev["place"], "lat": ev["lat"], "lng": ev["lng"], "crew": actor,
                                    "status": "on_scene"})
    with db.tx() as c:
        c.execute("UPDATE incidents SET mci_id=?, mci_tag=? WHERE id=?", (eid, tag, inc["id"]))
        audit.append("MCI_TRIAGED", inc["id"], {"mci_id": eid, "tag": tag, "triage": triage, "start": start or {}}, actor, con=c)
    return {"incident": services.get_incident(inc["id"]), "tag": tag, "event": mci_active()}


def mci_retriage(iid: str, triage: str, actor: str) -> dict:
    if triage not in ("RED", "YELLOW", "GREEN", "BLACK"):
        raise ValueError("Triage must be RED, YELLOW, GREEN or BLACK")
    services.update_incident(iid, {"triage": triage}, actor)
    return mci_active() or {}


def mci_close(eid: str, actor: str) -> dict:
    t = _now()
    with db.tx() as c:
        c.execute("UPDATE mci_events SET closed_at=? WHERE id=? AND closed_at IS NULL", (t, eid))
        audit.append("MCI_CLOSED", None, {"mci_id": eid}, actor, ts=t, con=c)
    return {"ok": True}
