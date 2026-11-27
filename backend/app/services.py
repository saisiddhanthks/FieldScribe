"""Domain services: incidents, signed records, analytics, sync."""
from __future__ import annotations

import json
import random
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from . import audit, db
from .nlp import lexicon as L

HOSPITALS = [
    {"id": "H1", "name": "Victoria Hospital", "lat": 12.9602, "lng": 77.5737, "type": "Govt tertiary", "beds_ed": 40},
    {"id": "H2", "name": "NIMHANS", "lat": 12.9416, "lng": 77.5960, "type": "Neuro / trauma", "beds_ed": 24},
    {"id": "H3", "name": "Jayadeva Institute of Cardiology", "lat": 12.9173, "lng": 77.5996, "type": "Cardiac", "beds_ed": 30},
    {"id": "H4", "name": "K.C. General Hospital", "lat": 12.9925, "lng": 77.5708, "type": "Govt district", "beds_ed": 20},
    {"id": "H5", "name": "St. John's Medical College Hospital", "lat": 12.9298, "lng": 77.6194, "type": "Private tertiary", "beds_ed": 36},
]
CREW = ["EMT-07 R. Kumar", "EMT-12 S. Nair", "EMT-03 A. Gowda", "EMT-21 P. Reddy", "EMT-15 M. Iyer", "EMT-09 F. Khan"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def _row_incident(r: dict) -> dict:
    r = dict(r)
    r["patient"] = db.jload(r.get("patient"), {})
    r["workflow"] = db.jload(r.get("workflow"), {})
    r["legal"] = db.jload(r.get("legal"), {}) if r.get("legal") else {}
    return r


def list_incidents(status: str | None = None) -> list[dict]:
    rows = db.q("SELECT * FROM incidents " + ("WHERE status=? " if status else "") + "ORDER BY created_at DESC", (status,) if status else ())
    out = []
    counts = {r["incident_id"]: r for r in db.q(
        "SELECT incident_id, SUM(kind='medication' AND status!='withheld') meds, SUM(kind='procedure') procs, "
        "SUM(json_array_length(flags) > 0) flagged FROM entries WHERE status NOT IN ('superseded','voided') GROUP BY incident_id")}
    for r in rows:
        inc = _row_incident(r)
        c = counts.get(inc["id"], {})
        inc["counts"] = {"meds": c.get("meds") or 0, "procs": c.get("procs") or 0, "flagged": c.get("flagged") or 0}
        out.append(inc)
    return out


def get_incident(iid: str) -> dict | None:
    r = db.q1("SELECT * FROM incidents WHERE id=?", (iid,))
    if not r:
        return None
    inc = _row_incident(r)
    inc["entries"] = entries(iid)
    inc["history"] = [e for e in entries(iid, history=True) if e["status"] in ("superseded", "voided")]
    inc["vitals"] = db.q("SELECT name,value,unit,time,created_at FROM vitals WHERE incident_id=? ORDER BY COALESCE(time, created_at), id", (iid,))
    for v in inc["vitals"]:
        try:
            v["value"] = json.loads(v["value"])
        except Exception:
            pass
    recs = db.q("SELECT id,source,asr_text,final_text,capture_ms,signer,created_at,ledger_seq,extraction FROM records WHERE incident_id=? ORDER BY created_at", (iid,))
    for rc in recs:
        ex = db.jload(rc.pop("extraction"), {})
        rc["alerts"] = ex.get("alerts", [])
    inc["records"] = recs
    inc["alerts"] = [a for rc in recs for a in rc["alerts"]]
    inc["ledger"] = db.q("SELECT seq,ts,event_type,hash,prev_hash,signer FROM ledger WHERE incident_id=? ORDER BY seq", (iid,))
    return inc


def entries(iid: str, history: bool = False) -> list[dict]:
    """Active clinical entries (amended originals and voided entries excluded unless history=True)."""
    out = []
    where = "" if history else " AND status NOT IN ('superseded','voided')"
    for e in db.q("SELECT * FROM entries WHERE incident_id=?" + where + " ORDER BY COALESCE(time,'99:99'), created_at", (iid,)):
        e["payload"] = db.jload(e["payload"], {})
        e["original"] = db.jload(e["original"], None)
        e["flags"] = db.jload(e["flags"], [])
        out.append(e)
    return out


def history_for(iid: str | None) -> list[dict]:
    if not iid:
        return []
    return [{"drug": e["payload"].get("drug"), "negated": e["status"] == "withheld", "time": e["payload"].get("time")}
            for e in entries(iid) if e["kind"] == "medication"]


def create_incident(data: dict, ts: datetime | None = None) -> dict:
    t = ts or now()
    iid = data.get("id") or "INC-" + uuid.uuid4().hex[:6].upper()
    dispatch = data.get("dispatch_id") or f"108-KA-{t.strftime('%y%m%d')}-{random.randint(1000, 9999)}"
    row = {"id": iid, "dispatch_id": dispatch, "vehicle": data.get("vehicle") or f"KA-01-G-{random.randint(1000, 9999)}",
           "crew": data.get("crew") or CREW[0], "status": data.get("status") or "on_scene",
           "complaint": data.get("complaint"), "triage": data.get("triage"),
           "patient": json.dumps(data.get("patient") or {}), "workflow": json.dumps(data.get("workflow") or {}),
           "lat": data.get("lat"), "lng": data.get("lng"), "place": data.get("place"),
           "destination": data.get("destination"), "eta_min": data.get("eta_min"),
           "created_at": t.isoformat(timespec="seconds"), "updated_at": t.isoformat(timespec="seconds"), "version": 1}
    with db.tx() as c:
        c.execute(f"INSERT INTO incidents({','.join(row)}) VALUES({','.join('?' * len(row))})", tuple(row.values()))
        audit.append("INCIDENT_OPENED", iid, {"dispatch_id": dispatch, "vehicle": row["vehicle"], "crew": row["crew"],
                                               "place": row["place"], "complaint": row["complaint"]}, row["crew"],
                     ts=t.isoformat(timespec="seconds"), con=c)
        _enqueue(c, "incident", iid, iid, {"op": "open", **{k: row[k] for k in ("dispatch_id", "vehicle", "status")}}, t)
    return get_incident(iid)


def update_incident(iid: str, data: dict, actor: str = "system", ts: datetime | None = None) -> dict:
    inc = db.q1("SELECT * FROM incidents WHERE id=?", (iid,))
    if not inc:
        raise KeyError(iid)
    sets, args = [], []
    for k in ("status", "destination", "eta_min", "triage", "complaint", "place"):
        if k in data and data[k] is not None:
            sets.append(f"{k}=?")
            args.append(data[k])
    wf = db.jload(inc["workflow"], {})
    if data.get("workflow"):
        wf.update({k: v for k, v in data["workflow"].items() if v})
        sets.append("workflow=?")
        args.append(json.dumps(wf))
    if not sets:
        return get_incident(iid)
    t = (ts or now()).isoformat(timespec="seconds")
    sets += ["updated_at=?", "version=version+1"]
    args += [t]
    with db.tx() as c:
        c.execute(f"UPDATE incidents SET {','.join(sets)} WHERE id=?", (*args, iid))
        audit.append("INCIDENT_UPDATED", iid, {k: data[k] for k in data if data[k] is not None}, actor, ts=t, con=c)
        _enqueue(c, "incident", iid, iid, {"op": "update", **data}, ts or now())
    return get_incident(iid)


def sign_record(iid: str, body: dict, ts: datetime | None = None) -> dict:
    inc = db.q1("SELECT * FROM incidents WHERE id=?", (iid,))
    if not inc:
        raise KeyError(iid)
    t = ts or now()
    tiso = t.isoformat(timespec="seconds")
    rid = "REC-" + uuid.uuid4().hex[:8].upper()
    signer = body.get("signer") or inc["crew"]
    kept = []
    for e in body.get("entries", []):
        if e.get("status") == "rejected":
            continue
        f = e.get("fields") or {}
        payload = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in f.items()}
        if e["kind"] == "medication":
            meta = L.DRUGS.get(payload.get("drug"), {})
            payload["rxnorm"] = meta.get("rxnorm")
            name = payload.get("drug")
        else:
            payload["snomed"] = L.PROCEDURES.get(payload.get("procedure"), {}).get("snomed")
            name = payload.get("procedure")
        if not payload.get("time"):
            payload["time"] = t.astimezone().strftime("%H:%M")
            payload["time_source"] = "capture"
        status = "withheld" if e.get("negated") or e.get("status") == "withheld" else "confirmed"
        kept.append({"id": "ENT-" + uuid.uuid4().hex[:8].upper(), "kind": e["kind"], "name": name, "payload": payload,
                     "original": e.get("original"), "status": status, "confidence": e.get("confidence"),
                     "edited": 1 if e.get("edited") else 0, "flags": e.get("flags") or [], "time": payload.get("time")})
    vitals = body.get("vitals") or []
    ledger_payload = {
        "record_id": rid, "source": body.get("source", "text"), "signer": signer,
        "text_sha256": audit.sha256((body.get("final_text") or "").encode()),
        "entries": [{"id": k["id"], "kind": k["kind"], "name": k["name"], "status": k["status"], "edited": bool(k["edited"]),
                     "fields": k["payload"]} for k in kept],
        "vitals": [{"name": v["name"], "value": v["value"], "time": v.get("time") or t.astimezone().strftime("%H:%M")} for v in vitals],
        "acknowledged_alerts": sorted({a["code"] for a in body.get("alerts", []) if a.get("level") in ("critical", "warning")}),
    }
    with db.tx() as c:
        blk = audit.append("RECORD_SIGNED", iid, ledger_payload, signer, ts=tiso, con=c)
        c.execute("INSERT INTO records(id,incident_id,source,asr_text,final_text,extraction,capture_ms,asr_meta,signer,created_at,ledger_seq)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (rid, iid, body.get("source", "text"), body.get("asr_text"), body.get("final_text"),
                   json.dumps({"alerts": body.get("alerts", []), "stats": body.get("stats")}), body.get("capture_ms"),
                   json.dumps(body.get("asr_meta") or {}), signer, tiso, blk["seq"]))
        for k in kept:
            c.execute("INSERT INTO entries(id,incident_id,record_id,kind,name,payload,original,status,confidence,edited,flags,time,signer,created_at)"
                      " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (k["id"], iid, rid, k["kind"], k["name"], json.dumps(k["payload"]), json.dumps(k["original"]), k["status"],
                       k["confidence"], k["edited"], json.dumps(k["flags"]), k["time"], signer, tiso))
        cap_time = t.astimezone().strftime("%H:%M")
        for v in vitals:
            v = {**v, "time": v.get("time") or cap_time}
            c.execute("INSERT INTO vitals(incident_id,record_id,name,value,unit,time,created_at) VALUES(?,?,?,?,?,?,?)",
                      (iid, rid, v["name"], json.dumps(v["value"]), v.get("unit"), v.get("time"), tiso))
        pat = db.jload(inc["patient"], {})
        for k, v in (body.get("patient") or {}).items():
            if k == "allergies":
                pat["allergies"] = sorted(set(pat.get("allergies", [])) | set(v))
            elif k == "chief_complaints":
                pat["chief_complaints"] = sorted(set(pat.get("chief_complaints", [])) | set(v))
            elif v is not None:
                pat[k] = v
        wf = db.jload(inc["workflow"], {})
        wf.update({k: v for k, v in (body.get("workflow") or {}).items() if v})
        complaint = inc["complaint"] or (pat.get("chief_complaints") or [None])[0]
        triage = inc["triage"] or pat.get("triage")
        c.execute("UPDATE incidents SET patient=?, workflow=?, complaint=?, triage=?, updated_at=?, version=version+1 WHERE id=?",
                  (json.dumps(pat), json.dumps(wf), complaint, triage, tiso, iid))
        _enqueue(c, "record", rid, iid, ledger_payload, t)
    return {"record_id": rid, "ledger": blk, "entries": len(kept), "incident": get_incident(iid)}


def handover(iid: str, received_by: str, ts: datetime | None = None) -> dict:
    t = ts or now()
    inc = db.q1("SELECT * FROM incidents WHERE id=?", (iid,))
    if not inc:
        raise KeyError(iid)
    wf = db.jload(inc["workflow"], {})
    wf.setdefault("handover", t.astimezone().strftime("%H:%M"))
    with db.tx() as c:
        c.execute("UPDATE incidents SET status='handed_over', handover_by=?, handover_at=?, workflow=?, updated_at=?, version=version+1 WHERE id=?",
                  (received_by, t.isoformat(timespec="seconds"), json.dumps(wf), t.isoformat(timespec="seconds"), iid))
        blk = audit.append("HANDOVER_ACK", iid, {"received_by": received_by, "at": t.isoformat(timespec="seconds")}, received_by, ts=t.isoformat(timespec="seconds"), con=c)
        _enqueue(c, "handover", iid, iid, {"received_by": received_by}, t)
    return {"ok": True, "ledger": blk, "incident": get_incident(iid)}


# ------------------------------------------------------------------ sync

def _enqueue(c, kind, ref, iid, payload, t):
    body = json.dumps(payload, default=str)
    c.execute("INSERT INTO outbox(kind,ref_id,incident_id,payload,status,created_at,bytes) VALUES(?,?,?,?,?,?,?)",
              (kind, ref, iid, body, "queued", t.isoformat(timespec="seconds"), len(body.encode())))


def is_online() -> bool:
    return db.setting("online", "1") == "1"


def sync_state() -> dict:
    items = db.q("SELECT id,kind,ref_id,incident_id,status,attempts,created_at,synced_at,bytes,note FROM outbox ORDER BY id DESC LIMIT 60")
    counts = Counter(r["status"] for r in db.q("SELECT status FROM outbox"))
    return {"online": is_online(), "queued": counts.get("queued", 0), "synced": counts.get("synced", 0),
            "conflicts": counts.get("conflict", 0), "items": items,
            "queued_bytes": (db.q1("SELECT COALESCE(SUM(bytes),0) b FROM outbox WHERE status='queued'") or {}).get("b", 0),
            "last_sync": db.setting("last_sync")}


def run_sync() -> dict:
    """Push queued items to the hub (PostgreSQL or simulated). Clinical items are append-only and
    idempotent; if the hub holds a newer incident header (edited by the ED) the header follows the
    hub and the conflict is recorded for audit."""
    from . import hub
    if not is_online():
        return {**sync_state(), "ok": False, "error": "Device is offline - records stay queued and signed locally"}
    pending = db.q("SELECT * FROM outbox WHERE status='queued' ORDER BY id")
    t = now().isoformat(timespec="seconds")
    try:
        h = hub.open_hub()
    except hub.HubError as e:
        return {**sync_state(), "ok": False, "error": f"ED hub unreachable ({e}). Items stay queued."}
    device = audit.key_id()
    results = []
    synced = conflicts = 0
    try:
        for item in pending:
            inc = db.q1("SELECT version FROM incidents WHERE id=?", (item["incident_id"],))
            local_v = inc["version"] if inc else 0
            hv = h.version(item["incident_id"])
            note, status = None, "synced"
            if hv is not None and hv > local_v:
                note = f"hub v{hv} > local v{local_v}: entries merged (append-only), header kept from hub"
                status = "conflict"
                conflicts += 1
            else:
                synced += 1
            h.receive(device, item, local_v)
            results.append((status, t, note, item["id"]))
        h.commit()
    except Exception as e:
        h.close()
        return {**sync_state(), "ok": False, "error": f"Sync interrupted ({str(e)[:160]}). Items stay queued."}
    h.close()
    with db.tx() as c:
        for status, tt, note, oid in results:
            c.execute("UPDATE outbox SET status=?, synced_at=?, attempts=attempts+1, note=? WHERE id=?", (status, tt, note, oid))
        c.execute("INSERT INTO settings(key,value) VALUES('last_sync',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (t,))
    return {**sync_state(), "ok": True, "synced_now": synced, "conflicts_now": conflicts, "hub": hub.engine()}


def simulate_hub_edit(iid: str) -> dict:
    """Demo: the ED hub edits the incident header while the ambulance is offline."""
    from . import hub
    inc = db.q1("SELECT version FROM incidents WHERE id=?", (iid,))
    if not inc:
        raise KeyError(iid)
    h = hub.open_hub()
    h.set_version(iid, inc["version"] + 5)
    h.commit()
    h.close()
    return {"ok": True, "hub_version": inc["version"] + 5, "hub": hub.engine()}


# ------------------------------------------------------------------ analytics

def analytics() -> dict:
    incs = list_incidents()
    ents = db.q("SELECT kind,name,payload,status,confidence,edited,flags,created_at,incident_id FROM entries WHERE status NOT IN ('superseded','voided')")
    recs = db.q("SELECT capture_ms, source, created_at, asr_text, final_text FROM records")
    by_hour = defaultdict(lambda: {"records": 0, "meds": 0, "procs": 0})
    t0 = now() - timedelta(hours=23)
    for h in range(24):
        k = (t0 + timedelta(hours=h)).astimezone().strftime("%H:00")
        by_hour[k]
    for e in ents:
        k = datetime.fromisoformat(e["created_at"]).astimezone().strftime("%H:00")
        if k in by_hour:
            by_hour[k]["meds" if e["kind"] == "medication" else "procs"] += 1
    for r in recs:
        k = datetime.fromisoformat(r["created_at"]).astimezone().strftime("%H:00")
        if k in by_hour:
            by_hour[k]["records"] += 1
    drugs = Counter(e["name"] for e in ents if e["kind"] == "medication" and e["status"] != "withheld")
    procs = Counter(e["name"] for e in ents if e["kind"] == "procedure")
    routes = Counter((db.jload(e["payload"], {}) or {}).get("route") for e in ents if e["kind"] == "medication")
    flags = Counter(f["code"] for e in ents for f in db.jload(e["flags"], []))
    conf_bins = Counter(min(9, int((e["confidence"] or 0) * 10)) for e in ents)
    triage = Counter(i.get("triage") or "UNTRIAGED" for i in incs)
    status = Counter(i["status"] for i in incs)
    complaints = Counter(i.get("complaint") or "Other" for i in incs)
    cap = [r["capture_ms"] for r in recs if r["capture_ms"]]
    avg_cap = sum(cap) / len(cap) / 1000 if cap else 0
    manual_baseline = float(db.setting("manual_baseline_s", "210"))
    edited = sum(1 for e in ents if e["edited"])
    from .asr import wer
    voice = [r for r in recs if r["source"] == "voice" and r["asr_text"] and r["final_text"]]
    wers = [wer(r["final_text"], r["asr_text"])["wer"] for r in voice]
    v = audit.verify()
    return {
        "kpi": {
            "incidents": len(incs), "active": sum(1 for i in incs if i["status"] in ("on_scene", "transporting")),
            "meds": sum(drugs.values()), "procedures": sum(procs.values()), "records": len(recs),
            "avg_capture_s": round(avg_cap, 1), "manual_baseline_s": manual_baseline,
            "time_saved_min": round(max(0, manual_baseline - avg_cap) * len(recs) / 60, 1),
            "flagged": sum(1 for e in ents if db.jload(e["flags"], [])), "edited": edited,
            "edit_rate": round(edited / len(ents), 3) if ents else 0,
            "mean_confidence": round(sum(e["confidence"] or 0 for e in ents) / len(ents), 3) if ents else 0,
            "chain_valid": v["valid"], "blocks": v["blocks"], "field_wer": round(sum(wers) / len(wers), 3) if wers else None,
            "queued": sync_state()["queued"], "online": is_online(),
        },
        "hourly": [{"hour": k, **v_} for k, v_ in by_hour.items()],
        "drugs": [{"name": k, "count": c} for k, c in drugs.most_common(10)],
        "procedures": [{"name": k, "count": c} for k, c in procs.most_common(8)],
        "routes": [{"name": k or "—", "count": c} for k, c in routes.most_common()],
        "flags": [{"code": k, "count": c} for k, c in flags.most_common(10)],
        "confidence": [{"bin": f"{b * 10}-{b * 10 + 10}%", "count": conf_bins.get(b, 0)} for b in range(4, 10)],
        "triage": [{"name": k, "count": c} for k, c in triage.items()],
        "status": [{"name": k, "count": c} for k, c in status.items()],
        "complaints": [{"name": k, "count": c} for k, c in complaints.most_common(8)],
        "hospitals": HOSPITALS,
        "fleet": [{"id": i["id"], "vehicle": i["vehicle"], "lat": i["lat"], "lng": i["lng"], "status": i["status"],
                   "triage": i.get("triage"), "destination": i.get("destination"), "eta_min": i.get("eta_min"),
                   "complaint": i.get("complaint")} for i in incs if i.get("lat")],
    }


# ------------------------------------------------------------------ amendments

def amend_entry(eid: str, fields: dict, reason: str, by: str) -> dict:
    """Correct a signed entry. The original is kept (status 'superseded') and a new entry
    replaces it; both changes are committed to the audit chain as one ENTRY_AMENDED block."""
    old = db.q1("SELECT * FROM entries WHERE id=?", (eid,))
    if not old:
        raise KeyError(eid)
    if old["status"] in ("superseded", "voided"):
        raise ValueError("This entry was already amended or voided")
    if not (reason or "").strip():
        raise ValueError("A reason is required")
    before = db.jload(old["payload"], {})
    after = dict(before)
    for k, v in fields.items():
        if k in ("drug", "dose", "unit", "route", "time", "rate", "device", "procedure", "site", "energy"):
            after[k] = v if v not in ("",) else None
    if old["kind"] == "medication":
        meta = L.DRUGS.get(after.get("drug"), {})
        after["rxnorm"] = meta.get("rxnorm")
        name = after.get("drug")
    else:
        after["snomed"] = L.PROCEDURES.get(after.get("procedure"), {}).get("snomed")
        name = after.get("procedure")
    after.pop("time_source", None) if fields.get("time") else None
    status = fields.get("status") if fields.get("status") in ("confirmed", "withheld") else ("withheld" if old["status"] == "withheld" else "confirmed")
    new_id = "ENT-" + uuid.uuid4().hex[:8].upper()
    t = now().isoformat(timespec="seconds")
    diff = {k: {"from": before.get(k), "to": after.get(k)} for k in set(before) | set(after) if before.get(k) != after.get(k) and k not in ("rxnorm", "snomed")}
    with db.tx() as c:
        blk = audit.append("ENTRY_AMENDED", old["incident_id"], {"original": eid, "replacement": new_id, "name": name, "changes": diff,
                                                                  "status": status, "reason": reason.strip(), "by": by}, by, con=c)
        c.execute("UPDATE entries SET status='superseded', superseded_by=?, change_reason=?, changed_by=?, changed_at=? WHERE id=?",
                  (new_id, reason.strip(), by, t, eid))
        c.execute("INSERT INTO entries(id,incident_id,record_id,kind,name,payload,original,status,confidence,edited,flags,time,signer,created_at,amends,change_reason,changed_by,changed_at)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (new_id, old["incident_id"], old["record_id"], old["kind"], name, json.dumps(after), old["payload"], status, 1.0, 1, "[]",
                   after.get("time") or old["time"], by, t, eid, reason.strip(), by, t))
        c.execute("UPDATE incidents SET updated_at=?, version=version+1 WHERE id=?", (t, old["incident_id"]))
        _enqueue(c, "amendment", new_id, old["incident_id"], {"original": eid, "replacement": new_id, "changes": diff, "reason": reason}, now())
    return {"ok": True, "replacement": new_id, "ledger": blk, "changes": diff}


def void_entry(eid: str, reason: str, by: str) -> dict:
    """Mark an entry as entered in error. Nothing is deleted; the void is a signed block."""
    old = db.q1("SELECT * FROM entries WHERE id=?", (eid,))
    if not old:
        raise KeyError(eid)
    if old["status"] in ("superseded", "voided"):
        raise ValueError("This entry was already amended or voided")
    if not (reason or "").strip():
        raise ValueError("A reason is required")
    t = now().isoformat(timespec="seconds")
    with db.tx() as c:
        blk = audit.append("ENTRY_VOIDED", old["incident_id"], {"entry": eid, "name": old["name"], "reason": reason.strip(), "by": by}, by, con=c)
        c.execute("UPDATE entries SET status='voided', change_reason=?, changed_by=?, changed_at=? WHERE id=?", (reason.strip(), by, t, eid))
        c.execute("UPDATE incidents SET updated_at=?, version=version+1 WHERE id=?", (t, old["incident_id"]))
        _enqueue(c, "void", eid, old["incident_id"], {"entry": eid, "reason": reason}, now())
    return {"ok": True, "ledger": blk}
