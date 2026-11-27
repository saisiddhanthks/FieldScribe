"""Right-hospital routing, MLC, ABHA, refusal of care, access log and mass-casualty mode."""
import base64
import os
import tempfile

os.environ.setdefault("FIELDSCRIBE_DATA", tempfile.mkdtemp())
os.environ["FIELDSCRIBE_AUTH"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import auth, db, field  # noqa: E402

SIG = "data:image/png;base64," + base64.b64encode(b"\x89PNG" + b"0" * 400).decode()


def _inc(c, complaint, lat=12.95, lng=77.60):
    return c.post("/api/incidents", json={"complaint": complaint, "place": "Test", "lat": lat, "lng": lng, "triage": "RED"}).json()


def test_destinations_pick_capability_over_nearest():
    with TestClient(app) as c:
        inc = _inc(c, "Chest pain radiating to left arm, sweating", lat=12.990, lng=77.572)   # beside K.C. General
        d = c.get(f"/api/incidents/{inc['id']}/destinations").json()
        assert any(n["key"] == "pci" for n in d["needs"])
        best = next(h for h in d["hospitals"] if h["id"] == d["recommended"])
        assert "pci" in best["has"]
        kc = next(h for h in d["hospitals"] if h["id"] == "H4")
        assert kc["suitable"] is False and best["id"] != "H4"
        assert d["note"] and "K.C. General" in d["note"]


def test_mlc_suggest_and_record():
    with TestClient(app) as c:
        inc = _inc(c, "RTA two-wheeler skid, head injury")
        full = c.get(f"/api/incidents/{inc['id']}").json()
        assert "Road traffic accident" in full["mlc_suggest"]
        r = c.post(f"/api/incidents/{inc['id']}/mlc", json={"is_mlc": True, "category": "Road traffic accident",
                                                           "police_station": "Madiwala", "informed": True, "informed_at": "10:55"}).json()
        assert r["mlc"]["police_station"] == "Madiwala"
        assert any(b["event_type"] == "MLC_RECORDED" for b in c.get(f"/api/ledger?incident_id={inc['id']}").json())


def test_abha_validation_and_fhir():
    assert field.check_abha("91-1234-5678-9012")["ok"]
    assert field.check_abha("ravi.k@abdm")["kind"] == "address"
    assert not field.check_abha("12345")["ok"]
    with TestClient(app) as c:
        inc = _inc(c, "Fever")
        assert c.post(f"/api/incidents/{inc['id']}/patient", json={"abha": "123"}).status_code == 400
        p = c.post(f"/api/incidents/{inc['id']}/patient", json={"abha": "91 1234 5678 9012", "relative_phone": "98450 00000"}).json()
        assert p["patient"]["abha"] == "91-1234-5678-9012"
        b = c.get(f"/api/incidents/{inc['id']}/fhir").json()
        pt = next(e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "Patient")
        assert any(i.get("value") == "91-1234-5678-9012" for i in pt["identifier"])
        led = c.get(f"/api/ledger?incident_id={inc['id']}").json()
        blk = next(x for x in led if x["event_type"] == "PATIENT_UPDATED")
        assert "9012" in str(blk["payload"]) and "1234-5678" not in str(blk["payload"])   # masked in the ledger


def test_refusal_requires_signature_and_seals_it():
    with TestClient(app) as c:
        inc = _inc(c, "Fall at home, refuses hospital")
        bad = c.post(f"/api/incidents/{inc['id']}/refusal", json={"risks_explained": True, "capacity": "yes", "signed_by": "Self"})
        assert bad.status_code == 400
        ok = c.post(f"/api/incidents/{inc['id']}/refusal", json={"what": "transport", "reason": "Wants family doctor", "risks_explained": True,
                                                                "capacity": "yes", "signed_by": "R. Shetty", "signature": SIG}).json()
        assert ok["refusal"]["signature_sha256"]
        blk = next(x for x in c.get(f"/api/ledger?incident_id={inc['id']}").json() if x["event_type"] == "CARE_REFUSED")
        assert "signature" not in blk["payload"] and blk["payload"]["signature_sha256"] == ok["refusal"]["signature_sha256"]
        assert c.get(f"/api/incidents/{inc['id']}/pdf").status_code == 200


def test_access_log_records_views_and_exports():
    with TestClient(app) as c:
        inc = _inc(c, "Seizure")
        c.get(f"/api/incidents/{inc['id']}"); c.get(f"/api/incidents/{inc['id']}")
        c.get(f"/api/incidents/{inc['id']}/pdf")
        acts = [a["action"] for a in c.get(f"/api/incidents/{inc['id']}/access").json()]
        assert acts.count("viewed") == 1 and "downloaded PDF" in acts


def test_mass_casualty_flow():
    with TestClient(app) as c:
        cur = c.get("/api/mci").json()["active"]
        if cur:
            c.post(f"/api/mci/{cur['id']}/close")
        ev = c.post("/api/mci", json={"name": "Bus overturned", "place": "Hosur Road", "lat": 12.9, "lng": 77.62}).json()
        assert c.post("/api/mci", json={"name": "again"}).status_code == 400
        for t in ("RED", "YELLOW", "GREEN", "GREEN"):
            r = c.post(f"/api/mci/{ev['id']}/casualty", json={"triage": t, "note": "adult"}).json()
        assert r["tag"] == "T-04"
        a = c.get("/api/mci").json()["active"]
        assert a["counts"] == {"RED": 1, "YELLOW": 1, "GREEN": 2, "BLACK": 0} and a["total"] == 4
        c.post(f"/api/mci/retriage/{a['patients'][2]['id']}", json={"triage": "YELLOW"})
        assert c.get("/api/mci").json()["active"]["counts"]["YELLOW"] == 2
        assert c.post(f"/api/mci/{ev['id']}/casualty", json={"triage": "PINK"}).status_code == 400
        c.post(f"/api/mci/{ev['id']}/close")
        assert c.get("/api/mci").json()["active"] is None
