"""Tools the Copilot can call. Read tools are free; the only write tools are
open_incident (on request) and log_care (only for care the EMT says was done)."""
from __future__ import annotations

import time
import uuid

from .. import audit, services
from ..nlp.ner import extract
from . import protocols as P

SPECS: list[dict] = [
    {"name": "find_protocols",
     "description": "Find first-aid / prehospital protocol cards matching a description of the incident or condition. "
                    "Call this before giving first-aid guidance. Returns ordered steps, red flags, things not to do and protocol medication references.",
     "parameters": {"type": "object", "properties": {"description": {"type": "string", "description": "What happened / symptoms, in plain words"}},
                    "required": ["description"]}},
    {"name": "get_incident",
     "description": "Get the current record of an incident: patient, allergies, vitals, medications and procedures already logged, 108 timeline, safety flags.",
     "parameters": {"type": "object", "properties": {"incident_id": {"type": "string"}}, "required": ["incident_id"]}},
    {"name": "list_active_incidents",
     "description": "List incidents that are on scene or transporting, with triage, complaint, vehicle and counts.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "check_medication",
     "description": "Check a medication BEFORE it is given: dose range, allergy conflict with this patient, duplicates already given, high-alert status. Does not log anything.",
     "parameters": {"type": "object", "properties": {
         "incident_id": {"type": "string"}, "drug": {"type": "string"}, "dose": {"type": "number"},
         "unit": {"type": "string"}, "route": {"type": "string"}}, "required": ["incident_id", "drug"]}},
    {"name": "log_care",
     "description": "Log care that the EMT says has ALREADY been given or done (medications, procedures, vitals) into the signed patient record. "
                    "Pass the EMT's own words as the statement, e.g. 'gave aspirin 300 mg chewed at 10:42, bp 140/90'. "
                    "Never use this for suggestions or plans. Safe items are signed immediately; items with a critical safety flag are held "
                    "and returned with a pending_id for the EMT to confirm.",
     "parameters": {"type": "object", "properties": {
         "incident_id": {"type": "string"}, "statement": {"type": "string"}},
         "required": ["incident_id", "statement"]}},
    {"name": "confirm_flagged_care",
     "description": "Log items that were held for a critical safety flag. Call ONLY after the EMT explicitly confirms in their latest message (e.g. 'yes, checked, log it').",
     "parameters": {"type": "object", "properties": {"pending_id": {"type": "string"}}, "required": ["pending_id"]}},
    {"name": "open_incident",
     "description": "Open a new incident record when the EMT reports a new call and no incident is selected.",
     "parameters": {"type": "object", "properties": {"complaint": {"type": "string"}, "place": {"type": "string"},
                                                     "triage": {"type": "string", "enum": ["RED", "YELLOW", "GREEN"]}},
                    "required": ["complaint"]}},
    {"name": "draft_handover",
     "description": "Produce an ATMIST handover summary for the receiving ED from the signed record.",
     "parameters": {"type": "object", "properties": {"incident_id": {"type": "string"}}, "required": ["incident_id"]}},
    {"name": "verify_audit_chain",
     "description": "Verify the hash-chained, signed audit ledger and report any tampering.",
     "parameters": {"type": "object", "properties": {}}},
]
WRITE_TOOLS = {"log_care", "open_incident", "confirm_flagged_care"}


def _deid(inc: dict, cloud: bool) -> dict:
    """Trim an incident to what the model needs; drop location detail for cloud models."""
    out = {
        "incident_id": inc["id"], "status": inc["status"], "triage": inc.get("triage"), "complaint": inc.get("complaint"),
        "patient": {k: v for k, v in (inc.get("patient") or {}).items() if k in
                    ("age", "sex", "weight_kg", "allergies", "allergies_status", "chief_complaints", "medico_legal", "triage")},
        "workflow": inc.get("workflow"), "destination": inc.get("destination"),
    }
    if not cloud:
        out.update({"place": inc.get("place"), "vehicle": inc.get("vehicle"), "crew": inc.get("crew")})
    if "entries" in inc:
        out["care_logged"] = [{"kind": e["kind"], "name": e["name"], "status": e["status"],
                               **{k: e["payload"].get(k) for k in ("dose", "unit", "route", "rate", "time", "device") if e["payload"].get(k) is not None}}
                              for e in inc["entries"]]
        out["vitals"] = [{"name": v["name"], "value": v["value"], "time": v.get("time")} for v in inc.get("vitals", [])]
        out["flags"] = sorted({f"{a['level']}:{a['code']}" for a in inc.get("alerts", []) if a.get("level") != "info"})
    return out


def run(name: str, args: dict, ctx: dict) -> dict:
    """Execute a tool. ctx: {cloud: bool, incident_id: str|None, signer: str|None}"""
    t0 = time.perf_counter()
    try:
        res = _dispatch(name, args or {}, ctx)
    except KeyError as e:
        res = {"error": f"not found: {e}"}
    except Exception as e:  # pragma: no cover - surfaced to the model
        res = {"error": str(e)}
    res_ms = round((time.perf_counter() - t0) * 1000, 1)
    ctx.setdefault("trace", []).append({"name": name, "args": args, "ms": res_ms, "ok": "error" not in res,
                                        "summary": _summ(name, res)})
    return res


def _iid(args, ctx):
    iid = args.get("incident_id") or ctx.get("incident_id")
    if not iid:
        raise KeyError("incident_id (no incident selected)")
    return iid


def _dispatch(name: str, a: dict, ctx: dict) -> dict:
    cloud = ctx.get("cloud", False)
    if name in WRITE_TOOLS and not ctx.get("can_write", True):
        return {"error": "Your role can read the record but cannot log care or open incidents. Ask the EMT crew to log it."}
    if name == "find_protocols":
        cards = P.match(a.get("description", ""))
        ctx.setdefault("protocols", [])
        for c in cards:
            if c["id"] not in [p["id"] for p in ctx["protocols"]]:
                ctx["protocols"].append(c)
        if not cards:
            return {"matches": [], "note": "No specific card matched. Apply general primary survey: scene safety, ABCDE, vitals, call for ALS if unstable.",
                    "catalogue": P.catalogue()}
        return {"matches": [{k: c[k] for k in ("id", "title", "priority", "steps", "red_flags", "do_not", "meds", "log_hints")} for c in cards],
                "note": "Medication lines are protocol references; present them as 'per your 108 protocol / medical direction'."}
    if name == "get_incident":
        inc = services.get_incident(_iid(a, ctx))
        if not inc:
            raise KeyError(a.get("incident_id"))
        return _deid(inc, cloud)
    if name == "list_active_incidents":
        return {"incidents": [_deid(i, cloud) | {"meds": i["counts"]["meds"], "procs": i["counts"]["procs"]}
                              for i in services.list_incidents() if i["status"] in ("on_scene", "transporting")]}
    if name == "check_medication":
        iid = _iid(a, ctx)
        stmt = f"{a['drug']} {a.get('dose', '')} {a.get('unit', '')} {a.get('route', '')}".strip()
        inc = services.get_incident(iid) or {}
        # run the safety engine with this incident's allergies, age and dose history
        allergies = (inc.get("patient") or {}).get("allergies", [])
        txt = stmt + (f". allergic to {', '.join(allergies)}" if allergies else "")
        if (inc.get("patient") or {}).get("age") is not None:
            txt += f". {inc['patient']['age']} year old"
        r = extract(txt, services.history_for(iid))
        meds = [e for e in r["entities"] if e["kind"] == "medication"]
        if not meds:
            return {"recognised": False, "note": f"'{a['drug']}' is not in the FieldScribe drug lexicon; check spelling or protocol."}
        e = meds[0]
        return {"recognised": True, "drug": e["fields"]["drug"]["value"], "rxnorm": e["codes"].get("rxnorm"),
                "dose": e["fields"]["dose"]["value"], "unit": e["fields"]["unit"]["value"], "route": e["fields"]["route"]["value"],
                "flags": [{"level": f["level"], "code": f["code"], "message": f["message"]} for f in e["flags"]],
                "safe_to_proceed": not any(f["level"] == "critical" for f in e["flags"])}
    if name == "log_care":
        return log_care(_iid(a, ctx), a.get("statement", ""), False, ctx)
    if name == "confirm_flagged_care":
        return confirm_pending(a.get("pending_id", ""), ctx)
    if name == "open_incident":
        inc = services.create_incident({"complaint": a.get("complaint"), "place": a.get("place") or "Reported by crew via Copilot",
                                        "triage": a.get("triage"), "crew": ctx.get("signer") or services.CREW[0],
                                        "lat": 12.9716, "lng": 77.5946, "destination": "Victoria Hospital", "eta_min": 15})
        ctx["incident_id"] = inc["id"]
        ctx["opened"] = inc["id"]
        return {"incident_id": inc["id"], "dispatch_id": inc["dispatch_id"], "status": inc["status"]}
    if name == "draft_handover":
        return {"handover": draft_handover(_iid(a, ctx))}
    if name == "verify_audit_chain":
        v = audit.verify()
        return {k: v[k] for k in ("valid", "blocks", "first_bad_seq", "problems", "algorithm")}
    return {"error": f"unknown tool {name}"}


PENDING: dict[str, dict] = {}


def log_care(iid: str, statement: str, ack: bool, ctx: dict) -> dict:
    """Log what the EMT reports as done. Safe items are signed immediately; items with a
    critical flag are held as a pending confirmation (never silently dropped, never auto-logged)."""
    inc = services.get_incident(iid)
    if not inc:
        raise KeyError(iid)
    r = extract(statement, services.history_for(iid))
    pat = inc.get("patient") or {}
    if pat.get("allergies") or pat.get("age") is not None:
        # re-run safety with this patient's known allergies / age
        ctx_text = statement + (f". allergic to {', '.join(pat['allergies'])}" if pat.get("allergies") else "") + \
            (f". {pat['age']} year old" if pat.get("age") is not None else "")
        r2 = extract(ctx_text, services.history_for(iid))
        r["alerts"] = [a for a in r2["alerts"] if a["code"] != "ALLERGY_UNKNOWN"]
        for e, e2 in zip(r["entities"], r2["entities"]):
            e["flags"] = e2["flags"]
            for a in r["alerts"]:
                if a.get("entity_id") == e2["id"]:
                    a["entity_id"] = e["id"]
    if not r["entities"] and not r["vitals"]:
        return {"logged": False, "reason": "No medication, procedure or vital sign recognised in the statement. Ask the EMT to restate drug, dose and route."}
    for e in r["entities"]:
        e["status"] = "withheld" if e["negated"] else "confirmed"
    crit_ids = {e["id"] for e in r["entities"] if any(f["level"] == "critical" for f in e["flags"])} if not ack else set()
    safe = [e for e in r["entities"] if e["id"] not in crit_ids]
    held = [e for e in r["entities"] if e["id"] in crit_ids]
    out: dict = {"logged": False}
    if safe or r["vitals"]:
        item = _sign(iid, inc, statement, safe, r["vitals"], r, ctx, ack)
        out.update({"logged": True, **{k: item[k] for k in ("record_id", "block", "entries", "vitals", "warnings")}})
    if held:
        pid = "P-" + uuid.uuid4().hex[:8]
        crit_alerts = [a for a in r["alerts"] if a.get("entity_id") in crit_ids and a["level"] == "critical"]
        PENDING[pid] = {"incident_id": iid, "statement": statement, "entities": held, "alerts": crit_alerts, "r": r}
        ctx["pending"] = {"id": pid, "incident_id": iid, "statement": statement,
                          "items": [(e["fields"].get("drug") or e["fields"].get("procedure"))["value"] for e in held],
                          "alerts": [{"level": a["level"], "code": a["code"], "message": a["message"]} for a in crit_alerts]}
        out.update({"needs_confirmation": True, "pending_id": pid, "held_items": ctx["pending"]["items"],
                    "critical_flags": [a["message"] for a in crit_alerts],
                    "instruction": "Tell the EMT exactly which item is held and why. Only after they explicitly confirm, call confirm_flagged_care with this pending_id."})
    return out


def confirm_pending(pid: str, ctx: dict) -> dict:
    p = PENDING.pop(pid, None)
    if not p:
        return {"logged": False, "reason": "That confirmation has expired or was already handled."}
    inc = services.get_incident(p["incident_id"])
    item = _sign(p["incident_id"], inc, p["statement"], p["entities"], [], p["r"], ctx, True)
    return {"logged": True, **{k: item[k] for k in ("record_id", "block", "entries", "vitals", "warnings")}}


def _sign(iid, inc, statement, entities, vitals, r, ctx, ack) -> dict:
    signer = (ctx.get("signer") or inc["crew"]) + " via Copilot"
    ids = {e["id"] for e in entities}
    alerts = [a for a in r["alerts"] if not a.get("entity_id") or a["entity_id"] in ids]
    out = services.sign_record(iid, {
        "source": "agent", "final_text": statement, "signer": signer, "entries": entities, "vitals": vitals,
        "patient": r["patient"], "workflow": r["workflow"], "alerts": alerts, "stats": r["stats"],
        "asr_meta": {"agent_provider": ctx.get("provider"), "acknowledged_critical": ack},
    })
    item = {"record_id": out["record_id"], "block": out["ledger"]["seq"], "hash": out["ledger"]["hash"], "incident_id": iid,
            "acknowledged": ack,
            "entries": [{"kind": e["kind"], "name": (e["fields"].get("drug") or e["fields"].get("procedure"))["value"],
                         "status": e["status"], **{k: e["fields"][k]["value"] for k in ("dose", "unit", "route", "time", "rate") if k in e["fields"] and e["fields"][k]["value"] is not None}}
                        for e in entities],
            "vitals": [{"name": v["name"], "value": v["value"]} for v in vitals],
            "warnings": [a["message"] for a in alerts if a["level"] == "warning"]}
    ctx.setdefault("logged", []).append(item)
    return item


def draft_handover(iid: str) -> str:
    inc = services.get_incident(iid)
    if not inc:
        raise KeyError(iid)
    p = inc.get("patient") or {}
    wf = inc.get("workflow") or {}
    latest = {}
    for v in inc["vitals"]:
        latest[v["name"]] = v["value"]
    meds = [e for e in inc["entries"] if e["kind"] == "medication" and e["status"] != "withheld"]
    held = [e for e in inc["entries"] if e["kind"] == "medication" and e["status"] == "withheld"]
    procs = [e for e in inc["entries"] if e["kind"] == "procedure"]
    def _dose(m):
        pl = m["payload"]
        if pl.get("rate"):
            return pl["rate"]
        return "{:g} {}".format(float(pl["dose"]), pl.get("unit")) if pl.get("dose") is not None else ""
    tx = "; ".join("{} {} {} at {}".format(m["payload"].get("drug"), _dose(m), m["payload"].get("route") or "",
                                           m["payload"].get("time") or "?").replace("  ", " ") for m in meds)
    lines = [
        f"A - {p.get('age', '?')} year old {p.get('sex', 'patient')}" + (f", {p['weight_kg']:g} kg" if p.get("weight_kg") else ""),
        f"T - call {wf.get('call_received', '?')}, on scene {wf.get('at_scene', '?')}" + (f", left scene {wf['left_scene']}" if wf.get("left_scene") else ""),
        f"M - {inc.get('complaint') or 'not stated'}",
        f"I - {', '.join(p.get('chief_complaints', [])) or 'see record'}" + (f"; ALLERGY: {', '.join(p['allergies'])}" if p.get("allergies") else ""),
        "S - " + (", ".join(f"{k.upper()} {v}" for k, v in latest.items() if k != "pupils") or "no vitals recorded"),
        "T - " + (tx or "no medications") + (("; procedures: " + ", ".join(x["payload"].get("procedure") for x in procs)) if procs else "")
        + (("; withheld: " + ", ".join(x["payload"].get("drug") for x in held)) if held else ""),
    ]
    return "\n".join(lines)


def _summ(name: str, res: dict) -> str:
    if "error" in res:
        return res["error"]
    if name == "find_protocols":
        return ", ".join(m["title"] for m in res.get("matches", [])) or "no specific card"
    if name in ("log_care", "confirm_flagged_care"):
        parts = []
        if res.get("logged"):
            parts.append(f"block #{res['block']}: " + ", ".join(e["name"] for e in res["entries"]) + (f" + {len(res['vitals'])} vitals" if res["vitals"] else ""))
        if res.get("needs_confirmation"):
            parts.append("held for confirmation: " + ", ".join(res["held_items"]))
        return "; ".join(parts) or res.get("reason", "not logged")
    if name == "check_medication":
        return ("ok" if res.get("safe_to_proceed") else "critical flag") if res.get("recognised") else "unknown drug"
    if name == "get_incident":
        return f"{res.get('complaint')} · {len(res.get('care_logged', []))} entries"
    if name == "list_active_incidents":
        return f"{len(res['incidents'])} active"
    if name == "open_incident":
        return res["dispatch_id"]
    if name == "verify_audit_chain":
        return "chain valid" if res["valid"] else f"break at #{res['first_bad_seq']}"
    return "done"
