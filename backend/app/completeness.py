"""
Handover readiness: what a receiving ED needs, checked against the signed record.
Base items apply to every patient; condition items are added from the chief complaint.
'required' items drive the score; 'recommended' items are prompts only.
"""
from __future__ import annotations

from . import services

PAIN_DRUGS = {"Morphine", "Fentanyl", "Tramadol", "Diclofenac", "Paracetamol", "Ketamine"}


def _has_vital(vitals, name, n=1):
    return sum(1 for v in vitals if v["name"] == name) >= n


def check(inc: dict) -> dict:
    p = inc.get("patient") or {}
    wf = inc.get("workflow") or {}
    vit = inc.get("vitals") or []
    ents = inc.get("entries") or []
    meds = [e for e in ents if e["kind"] == "medication"]
    given = {e["name"] for e in meds if e["status"] != "withheld"}
    procs = {e["name"] for e in ents if e["kind"] == "procedure"}
    complaints = " ".join([inc.get("complaint") or ""] + (p.get("chief_complaints") or [])).lower()
    items: list[dict] = []

    def item(key, label, ok, severity="required", hint=""):
        items.append({"key": key, "label": label, "ok": bool(ok), "severity": severity, "hint": hint})

    item("age_sex", "Age and sex", p.get("age") is not None and p.get("sex"), hint="e.g. '45 year old male'")
    item("allergies", "Allergy status (or NKDA)", p.get("allergies_status") or p.get("allergies"), hint="say 'no known allergies' or 'allergic to …'")
    item("complaint", "Chief complaint / mechanism", inc.get("complaint") or p.get("chief_complaints"))
    item("triage", "Triage category", inc.get("triage") or p.get("triage"), hint="'triage red / yellow / green'")
    item("vitals_core", "First set of vitals (HR, BP, SpO₂)", all(_has_vital(vit, n) for n in ("hr", "bp", "spo2")),
         hint="'bp 130/80, pulse 96, spo2 97'")
    item("consciousness", "Level of consciousness (GCS)", _has_vital(vit, "gcs"), hint="'GCS 15' or 'E4 V5 M6'")
    item("repeat_vitals", "Repeat vitals after treatment", _has_vital(vit, "hr", 2) or _has_vital(vit, "bp", 2) or _has_vital(vit, "spo2", 2),
         "recommended", "a second set before handover shows the trend")
    item("times", "Call and scene times", wf.get("call_received") and wf.get("at_scene"), "recommended", "'call received at …, reached scene at …'")
    item("destination", "Receiving hospital", inc.get("destination"))
    incomplete = [e["name"] for e in meds if e["status"] != "withheld" and
                  (e["payload"].get("dose") is None and not e["payload"].get("rate") or not e["payload"].get("route"))]
    item("med_details", "Every drug has dose and route", not incomplete, hint=("missing for: " + ", ".join(incomplete)) if incomplete else "")
    capture_timed = [e["name"] for e in ents if e["payload"].get("time_source") == "capture"]
    item("med_times", "Administration times dictated", not capture_timed, "recommended",
         ("using capture time for: " + ", ".join(capture_timed)) if capture_timed else "")
    condition = None
    if any(k in complaints for k in ("stroke", "facial droop", "slurred", "weakness of")):
        condition = "Suspected stroke"
        item("lkw", "Time last known well", wf.get("last_known_well"), hint="decides thrombolysis eligibility: 'last known well at 09:40'")
        item("glucose", "Blood glucose (rule out hypoglycaemia)", _has_vital(vit, "glucose"))
    if any(k in complaints for k in ("chest pain", "acs", "stemi", "heart attack")):
        condition = condition or "Chest pain / ACS"
        item("ecg", "12-lead ECG done", "Electrocardiogram" in procs)
        item("aspirin", "Aspirin given or reason documented", any(e["name"] == "Aspirin" for e in meds))
        item("pain", "Pain score", _has_vital(vit, "pain"), "recommended")
    if any(k in complaints for k in ("road traffic", "rta", "accident", "fall", "trauma", "bleeding", "injur")):
        condition = condition or "Trauma"
        item("gcs_trauma", "GCS for head-injury risk", _has_vital(vit, "gcs"))
        item("spine", "Spinal assessment / immobilisation", "Spinal immobilisation" in procs, "recommended",
             "record collar applied, or that spine was cleared")
        item("bleeding", "Haemorrhage control documented", "Haemorrhage control" in procs or "Wound dressing" in procs, "recommended")
    if "anaphylaxis" in complaints or "allergic reaction" in complaints:
        condition = condition or "Anaphylaxis"
        item("adrenaline", "Adrenaline given (time recorded)", "Adrenaline" in given)
        item("bp_ana", "Blood pressure after adrenaline", _has_vital(vit, "bp", 2), "recommended")
    if "hypoglyc" in complaints or "low sugar" in complaints:
        condition = condition or "Hypoglycaemia"
        item("grbs2", "Glucose before and after treatment", _has_vital(vit, "glucose", 2))
    if "seizure" in complaints or "fits" in complaints:
        condition = condition or "Seizure"
        item("grbs_seizure", "Blood glucose", _has_vital(vit, "glucose"))
    if "breath" in complaints or "asthma" in complaints or "wheez" in complaints:
        condition = condition or "Breathing difficulty"
        item("rr", "Respiratory rate", _has_vital(vit, "rr"))
        item("spo2_after", "SpO₂ after treatment", _has_vital(vit, "spo2", 2), "recommended")
    if "cardiac arrest" in complaints or "Cardiopulmonary resuscitation" in procs:
        condition = condition or "Cardiac arrest"
        item("cpr_time", "CPR start time", any(e["name"] == "Cardiopulmonary resuscitation" and e["payload"].get("time") for e in ents))
    if given & PAIN_DRUGS:
        item("pain_reassess", "Pain reassessed after analgesia", _has_vital(vit, "pain"), "recommended")
    req = [i for i in items if i["severity"] == "required"]
    score = round(100 * sum(i["ok"] for i in req) / len(req)) if req else 100
    missing = [i for i in items if not i["ok"]]
    return {"score": score, "ready": score >= 90 and not any(not i["ok"] for i in req), "condition": condition,
            "items": items, "missing": missing}


def for_incident(iid: str) -> dict | None:
    inc = services.get_incident(iid)
    return check(inc) if inc else None
