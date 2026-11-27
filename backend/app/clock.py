"""
Clinical clock: time-critical reminders derived from the signed record.
Times in entries are local HH:MM on the incident's date (as dictated by the crew).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import services

RECHECK_MIN = {"RED": 5, "YELLOW": 10, "GREEN": 15}
OPIOID_NSAID = {"Morphine", "Fentanyl", "Tramadol", "Diclofenac", "Ketamine"}
BENZO = {"Midazolam", "Diazepam"}


def _at(inc: dict, hhmm: str | None, fallback: str | None = None) -> datetime | None:
    base = datetime.fromisoformat(inc["created_at"]).astimezone()
    if hhmm:
        try:
            h, m = map(int, hhmm.split(":"))
            t = base.replace(hour=h, minute=m, second=0, microsecond=0)
            if t < base - timedelta(hours=2):      # crossed midnight
                t += timedelta(days=1)
            return t
        except ValueError:
            pass
    return datetime.fromisoformat(fallback).astimezone() if fallback else None


def timers(inc: dict, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now().astimezone()
    if inc["status"] in ("handed_over", "closed"):
        return []
    out = []
    ents = inc.get("entries") or []
    vit = inc.get("vitals") or []
    triage = (inc.get("triage") or (inc.get("patient") or {}).get("triage") or "").upper()

    def add(tid, label, started, due_min=None, warn_min=None, crit_min=None, message="", repeat=False):
        if started is None:
            return
        el = (now - started).total_seconds() / 60
        if el < 0:
            el = 0
        status, sev = "running", "info"
        if due_min is not None:
            if el >= due_min:
                status, sev = "due", "warning"
            if repeat and el >= due_min * 2:
                status, sev = "overdue", "critical"
        if warn_min is not None and el >= warn_min:
            status, sev = "due", "warning"
        if crit_min is not None and el >= crit_min:
            status, sev = "overdue", "critical"
        out.append({"id": f"{inc['id']}:{tid}", "incident_id": inc["id"], "vehicle": inc.get("vehicle"), "label": label,
                    "started": started.strftime("%H:%M"), "elapsed_min": round(el, 1),
                    "due_in_min": round(due_min - el, 1) if due_min is not None else None,
                    "status": status, "severity": sev, "message": message})

    # 1) vitals recheck by triage
    if vit:
        last = max((_at(inc, v.get("time"), v.get("created_at")) for v in vit), default=None)
        every = RECHECK_MIN.get(triage, 10)
        add("vitals", f"Recheck vitals (every {every} min, {triage.lower() or 'untriaged'})", last, due_min=every, repeat=True,
            message=f"Vitals last recorded at {last.strftime('%H:%M') if last else '?'}; repeat HR, BP, SpO2 now")
    # 2) tourniquet time
    for e in ents:
        if e["kind"] == "procedure" and (e["payload"].get("device") == "tourniquet" or "tourniquet" in (e.get("original") or {}).get("procedure", "").lower()):
            add(f"tq:{e['id']}", "Tourniquet on", _at(inc, e["payload"].get("time"), e["created_at"]), warn_min=60, crit_min=120,
                message="Note tourniquet time on handover; over 2 hours risks limb damage")
    # 3) repeat-dose windows
    for e in ents:
        if e["kind"] != "medication" or e["status"] == "withheld":
            continue
        t = _at(inc, e["payload"].get("time"), e["created_at"])
        if e["name"] == "Adrenaline" and e["payload"].get("route") == "IM":
            add(f"adr:{e['id']}", "Adrenaline IM: reassess for repeat dose", t, due_min=5,
                message="If no improvement after 5 minutes, repeat dose per protocol")
        elif e["name"] == "Adrenaline":
            add(f"adr:{e['id']}", "Adrenaline IV/IO cycle (3-5 min)", t, due_min=4, message="Next adrenaline due per ALS protocol")
        elif e["name"] in OPIOID_NSAID:
            add(f"pain:{e['id']}", f"Reassess pain after {e['name']}", t, due_min=15, message="Record pain score and RR")
        elif e["name"] in BENZO:
            add(f"benzo:{e['id']}", f"Airway / RR watch after {e['name']}", t, due_min=10, message="Check RR and SpO2 after benzodiazepine")
        elif e["name"] == "Dextrose":
            add(f"glu:{e['id']}", "Recheck glucose after dextrose", t, due_min=10, message="Repeat GRBS")
    # 4) CPR cycles
    cpr = [e for e in ents if e["name"] == "Cardiopulmonary resuscitation"]
    if cpr and "rosc" not in " ".join((r.get("final_text") or "").lower() for r in inc.get("records", [])):
        t = _at(inc, cpr[-1]["payload"].get("time"), cpr[-1]["created_at"])
        if t:
            el = (now - t).total_seconds() / 60
            nxt = 2 - (el % 2)
            out.append({"id": f"{inc['id']}:cpr", "incident_id": inc["id"], "vehicle": inc.get("vehicle"), "label": "CPR: rhythm check / swap compressor",
                        "started": t.strftime("%H:%M"), "elapsed_min": round(el, 1), "due_in_min": round(nxt, 1),
                        "status": "due" if nxt < 0.25 else "running", "severity": "warning" if nxt < 0.25 else "info",
                        "message": "2-minute cycle"})
    # 5) golden hour for time-critical conditions
    wf = inc.get("workflow") or {}
    cc = (inc.get("complaint") or "").lower()
    if wf.get("call_received") and not wf.get("at_hospital") and any(k in cc for k in ("accident", "trauma", "stroke", "chest", "arrest", "bleeding")):
        add("golden", "Golden hour (call to hospital)", _at(inc, wf["call_received"]), warn_min=45, crit_min=60,
            message="Time-critical patient: minimise scene time")
    rank = {"critical": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda x: (rank[x["severity"]], x.get("due_in_min") if x.get("due_in_min") is not None else 999))


def all_active(now: datetime | None = None) -> list[dict]:
    out = []
    for i in services.list_incidents():
        if i["status"] in ("on_scene", "transporting"):
            inc = services.get_incident(i["id"])
            out.extend(timers(inc, now))
    return out
