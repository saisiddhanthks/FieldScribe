"""FHIR R4 export: full Bundle plus the compact "FHIR-lite" handover JSON."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .nlp import lexicon as L

RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"
LOCAL = "https://fieldscribe.local/CodeSystem/procedure"

ROUTE_SNOMED = {
    "PO": ("26643006", "Oral route"), "IV": ("47625008", "Intravenous route"),
    "IM": ("78421000", "Intramuscular route"), "SL": ("37839007", "Sublingual route"),
    "SC": ("34206005", "Subcutaneous route"), "IO": ("60213007", "Intraosseous route"),
    "NEB": ("447694001", "Respiratory tract route"), "INH": ("447694001", "Respiratory tract route"),
    "IN": ("46713006", "Nasal route"), "PR": ("37161004", "Rectal route"), "TOP": ("6064005", "Topical route"),
}
UCUM_UNIT = {"mg": "mg", "mcg": "ug", "g": "g", "mL": "mL", "L": "L", "L/min": "L/min", "units": "[iU]", "mEq": "meq"}
VITAL_LOINC = {
    "hr": ("8867-4", "Heart rate", "/min"), "spo2": ("59408-5", "Oxygen saturation by pulse oximetry", "%"),
    "rr": ("9279-1", "Respiratory rate", "/min"), "gcs": ("9269-2", "Glasgow coma score total", "{score}"),
    "glucose": ("2339-0", "Glucose [Mass/volume] in Blood", "mg/dL"), "temp": ("8310-5", "Body temperature", "[degF]"),
    "pain": ("72514-3", "Pain severity - 0-10 verbal numeric rating", "{score}"),
}


def _uuid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "fieldscribe:" + seed))


def _dt(date_iso: str, hhmm: str | None) -> str:
    if not hhmm:
        return date_iso
    d = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
    h, m = map(int, hhmm.split(":"))
    return d.replace(hour=h, minute=m, second=0).isoformat()


def bundle(inc: dict, entries: list[dict], vitals: list[dict], ledger_head: str | None) -> dict:
    pid, eid, oid = _uuid(inc["id"] + "/pt"), _uuid(inc["id"] + "/enc"), _uuid("org/108")
    pr_id = _uuid(inc["id"] + "/emt/" + (inc.get("crew") or "emt"))
    pat = inc.get("patient") or {}
    base_date = inc["created_at"]
    res: list[dict] = []
    res.append({"resourceType": "Organization", "id": oid, "name": "108 Emergency Response Service",
                "type": [{"text": "Emergency Medical Services"}]})
    res.append({"resourceType": "Practitioner", "id": pr_id,
                "identifier": [{"system": "https://fieldscribe.local/crew", "value": inc.get("crew") or "EMT"}],
                "name": [{"text": inc.get("crew") or "EMT"}], "qualification": [{"code": {"text": "Emergency Medical Technician"}}]})
    patient = {"resourceType": "Patient", "id": pid,
               "identifier": [{"system": "https://fieldscribe.local/incident-patient", "value": inc["id"]}],
               "active": True}
    if pat.get("abha"):
        if pat.get("abha_kind") == "address":
            patient["identifier"].append({"type": {"text": "ABHA address"}, "system": "https://healthid.abdm.gov.in", "value": pat["abha"]})
        else:
            patient["identifier"].append({"type": {"text": "ABHA number"}, "system": "https://healthid.abdm.gov.in", "value": pat["abha"]})
    if pat.get("name"):
        patient["name"] = [{"text": pat["name"]}]
    if pat.get("sex"):
        patient["gender"] = pat["sex"]
    if pat.get("age") is not None:
        patient["extension"] = [{"url": "https://fieldscribe.local/StructureDefinition/estimated-age",
                                 "valueQuantity": {"value": pat["age"], "unit": "a", "system": UCUM, "code": "a"}}]
    res.append(patient)
    wf = inc.get("workflow") or {}
    enc = {"resourceType": "Encounter", "id": eid, "status": "finished" if inc.get("status") in ("handed_over", "closed") else "in-progress",
           "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "EMER", "display": "emergency"},
           "subject": {"reference": f"Patient/{pid}"}, "serviceProvider": {"reference": f"Organization/{oid}"},
           "identifier": [{"system": "https://108.gov.in/dispatch", "value": inc.get("dispatch_id")}],
           "reasonCode": [{"text": inc.get("complaint") or "Unspecified"}],
           "period": {"start": _dt(base_date, wf.get("at_scene") or wf.get("call_received")),
                      **({"end": _dt(base_date, wf.get("handover") or wf.get("at_hospital"))} if (wf.get("handover") or wf.get("at_hospital")) else {})},
           "priority": {"text": inc.get("triage") or "UNTRIAGED"},
           "location": [{"location": {"display": inc.get("place") or "Scene"}}]}
    if inc.get("destination"):
        enc["hospitalization"] = {"destination": {"display": inc["destination"]}}
    res.append(enc)
    if pat.get("allergies"):
        for a in pat["allergies"]:
            res.append({"resourceType": "AllergyIntolerance", "id": _uuid(inc["id"] + "/alg/" + a),
                        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}]},
                        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification", "code": "unconfirmed"}]},
                        "code": {"text": a}, "patient": {"reference": f"Patient/{pid}"}})
    targets = []
    for e in entries:
        p = e["payload"]
        rid = _uuid(e["id"])
        targets.append(rid)
        if e["kind"] == "medication":
            drug = p.get("drug")
            meta = L.DRUGS.get(drug, {})
            coding = [{"system": RXNORM, "code": meta["rxnorm"], "display": drug}] if meta.get("rxnorm") else []
            ma = {"resourceType": "MedicationAdministration", "id": rid,
                  "status": "not-done" if e["status"] == "withheld" else "completed",
                  "medicationCodeableConcept": {"coding": coding, "text": drug},
                  "subject": {"reference": f"Patient/{pid}"}, "context": {"reference": f"Encounter/{eid}"},
                  "effectiveDateTime": _dt(base_date, p.get("time") or e.get("time")),
                  "performer": [{"actor": {"reference": f"Practitioner/{pr_id}"}}]}
            if e["status"] == "withheld":
                ma["statusReason"] = [{"text": "Documented as withheld / not given by EMT"}]
            dosage: dict = {}
            r = p.get("route")
            if r in ROUTE_SNOMED:
                dosage["route"] = {"coding": [{"system": SNOMED, "code": ROUTE_SNOMED[r][0], "display": ROUTE_SNOMED[r][1]}], "text": r}
            if p.get("dose") not in (None, ""):
                u = p.get("unit") or meta.get("default_unit")
                dosage["dose"] = {"value": float(p["dose"]), "unit": u, "system": UCUM, "code": UCUM_UNIT.get(u, u)}
            if p.get("rate"):
                try:
                    val = float(str(p["rate"]).split()[0])
                    dosage["rateQuantity"] = {"value": val, "unit": "L/min", "system": UCUM, "code": "L/min"}
                except ValueError:
                    pass
            if p.get("device"):
                dosage["text"] = f"via {p['device']}"
            if dosage:
                ma["dosage"] = dosage
            res.append(ma)
        else:
            meta = L.PROCEDURES.get(p.get("procedure"), {})
            code = meta.get("snomed", "")
            proc = {"resourceType": "Procedure", "id": rid, "status": "not-done" if e["status"] == "withheld" else "completed",
                    "code": {"coding": [{"system": SNOMED if code.isdigit() else LOCAL, "code": code, "display": p.get("procedure")}],
                             "text": p.get("procedure")},
                    "subject": {"reference": f"Patient/{pid}"}, "encounter": {"reference": f"Encounter/{eid}"},
                    "performedDateTime": _dt(base_date, p.get("time") or e.get("time")),
                    "performer": [{"actor": {"reference": f"Practitioner/{pr_id}"}}]}
            notes = [f"{k}: {v}" for k, v in p.items() if k in ("device", "site", "energy") and v]
            if notes:
                proc["note"] = [{"text": "; ".join(notes)}]
            if p.get("site"):
                proc["bodySite"] = [{"text": p["site"]}]
            res.append(proc)
    for i, v in enumerate(vitals):
        oid_v = _uuid(f"{inc['id']}/obs/{i}/{v['name']}")
        obs = {"resourceType": "Observation", "id": oid_v, "status": "final",
               "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs"}]}],
               "subject": {"reference": f"Patient/{pid}"}, "encounter": {"reference": f"Encounter/{eid}"},
               "effectiveDateTime": _dt(base_date, v.get("time"))}
        if v["name"] == "bp":
            s, d = str(v["value"]).split("/")
            obs["code"] = {"coding": [{"system": LOINC, "code": "85354-9", "display": "Blood pressure panel"}]}
            obs["component"] = [
                {"code": {"coding": [{"system": LOINC, "code": "8480-6", "display": "Systolic blood pressure"}]},
                 "valueQuantity": {"value": int(s), "unit": "mmHg", "system": UCUM, "code": "mm[Hg]"}},
                {"code": {"coding": [{"system": LOINC, "code": "8462-4", "display": "Diastolic blood pressure"}]},
                 "valueQuantity": {"value": int(d), "unit": "mmHg", "system": UCUM, "code": "mm[Hg]"}}]
        elif v["name"] in VITAL_LOINC:
            code, disp, uc = VITAL_LOINC[v["name"]]
            obs["code"] = {"coding": [{"system": LOINC, "code": code, "display": disp}]}
            try:
                obs["valueQuantity"] = {"value": float(v["value"]), "unit": v.get("unit"), "system": UCUM, "code": uc}
            except (TypeError, ValueError):
                obs["valueString"] = str(v["value"])
        else:
            obs["code"] = {"text": v["name"]}
            obs["valueString"] = str(v["value"])
        res.append(obs)
        targets.append(oid_v)
    res.append({"resourceType": "Provenance", "id": _uuid(inc["id"] + "/prov"),
                "target": [{"reference": t} for t in targets[:50]],
                "recorded": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "activity": {"text": "EMT dictation -> FieldScribe extraction -> EMT confirmed & signed"},
                "agent": [{"who": {"reference": f"Practitioner/{pr_id}"}, "type": {"text": "author"}},
                          {"who": {"display": "FieldScribe edge device"}, "type": {"text": "assembler"}}],
                "signature": [{"type": [{"system": "urn:iso-astm:E1762-95:2013", "code": "1.2.840.10065.1.12.1.1", "display": "Author's Signature"}],
                               "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "who": {"reference": f"Practitioner/{pr_id}"},
                               "sigFormat": "application/fieldscribe-ledger-head",
                               "data": ledger_head or ""}]})
    return {"resourceType": "Bundle", "id": _uuid(inc["id"] + "/bundle"), "type": "collection",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "meta": {"tag": [{"system": "https://fieldscribe.local", "code": "fhir-r4-ems-handover"}]},
            "entry": [{"fullUrl": f"urn:uuid:{r['id']}", "resource": r} for r in res]}


def lite(inc: dict, entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        p = e["payload"]
        if e["kind"] == "medication":
            item = {"type": "MedicationAdministration", "drug": p.get("drug"), "dose": p.get("dose"), "unit": p.get("unit"),
                    "route": p.get("route"), "time": p.get("time"), "by": e.get("signer"), "status": e["status"]}
            if p.get("rate"):
                item["rate"] = p["rate"]
            if p.get("device"):
                item["device"] = p["device"]
        else:
            item = {"type": "Procedure", "procedure": p.get("procedure"), "time": p.get("time"), "by": e.get("signer"),
                    **{k: p[k] for k in ("device", "site", "energy") if p.get(k)}}
        out.append({k: v for k, v in item.items() if v is not None})
    return out
