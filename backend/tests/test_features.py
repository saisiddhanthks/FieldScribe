"""Login/roles, amendments, completeness, clinical clock, encrypted DB and PostgreSQL hub."""
import os
import tempfile
from datetime import datetime, timedelta

os.environ.setdefault("FIELDSCRIBE_DATA", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import auth, db, services, clock, completeness  # noqa: E402


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setenv("FIELDSCRIBE_AUTH", "1")


def login(c, uid, pin):
    r = c.post("/api/auth/login", json={"user_id": uid, "pin": pin})
    return r


def test_login_roles_and_signer(auth_on):
    with TestClient(app) as c:
        assert c.get("/api/incidents").status_code == 401
        assert login(c, "emt07", "0000").status_code == 401
        r = login(c, "emt07", "1080")
        assert r.status_code == 200 and r.json()["user"]["role"] == "emt"
        inc = c.post("/api/incidents", json={"place": "Auth test"}).json()
        ex = c.post("/api/extract", json={"text": "aspirin 300 mg oral at 10:42"}).json()
        ents = [dict(e, status="confirmed") for e in ex["entities"]]
        s = c.post(f"/api/incidents/{inc['id']}/records", json={"final_text": "x", "signer": "Someone Else", "entries": ents}).json()
        d = c.get(f"/api/incidents/{inc['id']}").json()
        assert d["entries"][0]["signer"] == "EMT-07 R. Kumar"          # signer comes from session, not the body
        assert c.post("/api/ledger/tamper").status_code == 403          # EMT cannot run admin drills
        assert c.post(f"/api/incidents/{inc['id']}/handover", json={}).status_code == 403
        c.post("/api/auth/logout")
        login(c, "edrao", "2020")
        assert c.post(f"/api/incidents/{inc['id']}/records", json={"final_text": "x", "entries": []}).status_code == 403
        h = c.post(f"/api/incidents/{inc['id']}/handover", json={"received_by": "fake"}).json()
        assert h["incident"]["handover_by"] == "Dr. A. Rao (ED)"


def test_pin_lockout(auth_on):
    with TestClient(app) as c:
        for _ in range(5):
            r = login(c, "emt12", "9999")
        assert r.json().get("locked")
        assert login(c, "emt12", "1080").status_code == 401            # locked even with right PIN
        with db.tx() as con:
            con.execute("UPDATE users SET locked_until=0, failed=0 WHERE id='emt12'")


def test_amend_and_void_are_signed_blocks(monkeypatch):
    monkeypatch.setenv("FIELDSCRIBE_AUTH", "0")
    with TestClient(app) as c:
        inc = c.post("/api/incidents", json={"place": "Amend test"}).json()
        ex = c.post("/api/extract", json={"text": "aspirin 3000 mg oral at 10:42, ondansetron 4 mg iv"}).json()
        sr = c.post(f"/api/incidents/{inc['id']}/records", json={"final_text": "x", "entries": [dict(e, status="confirmed") for e in ex["entities"]]})
        assert sr.status_code == 200, sr.text
        d = c.get(f"/api/incidents/{inc['id']}").json()
        assert "entries" in d, (inc, d)
        asp = next(e for e in d["entries"] if e["name"] == "Aspirin")
        assert c.post(f"/api/entries/{asp['id']}/amend", json={"fields": {"dose": 300}, "reason": ""}).status_code == 400
        r = c.post(f"/api/entries/{asp['id']}/amend", json={"fields": {"dose": 300}, "reason": "dictated 3000 by mistake"}).json()
        assert r["changes"]["dose"] == {"from": 3000.0, "to": 300}
        ond = next(e for e in d["entries"] if e["name"] == "Ondansetron")
        c.post(f"/api/entries/{ond['id']}/void", json={"reason": "entered on wrong patient"})
        d = c.get(f"/api/incidents/{inc['id']}").json()
        active = {e["name"]: e for e in d["entries"]}
        assert active["Aspirin"]["payload"]["dose"] == 300 and "Ondansetron" not in active
        assert {h["status"] for h in d["history"]} == {"superseded", "voided"}
        types = [b["event_type"] for b in d["ledger"]]
        assert "ENTRY_AMENDED" in types and "ENTRY_VOIDED" in types
        assert d["integrity"]["valid"]
        assert c.post(f"/api/entries/{asp['id']}/amend", json={"fields": {"dose": 1}, "reason": "again"}).status_code == 400


def test_completeness_stroke():
    inc = {"complaint": "Stroke", "patient": {"age": 67, "sex": "male", "allergies_status": "NKDA", "chief_complaints": ["Stroke"], "triage": "RED"},
           "triage": "RED", "workflow": {"call_received": "09:10", "at_scene": "09:22"}, "destination": "NIMHANS",
           "vitals": [{"name": "hr", "value": 90}, {"name": "bp", "value": "180/100"}, {"name": "spo2", "value": 97}, {"name": "gcs", "value": 14}],
           "entries": []}
    r = completeness.check(inc)
    keys = {i["key"]: i["ok"] for i in r["items"]}
    assert r["condition"] == "Suspected stroke" and keys["lkw"] is False and keys["glucose"] is False
    inc["workflow"]["last_known_well"] = "08:40"
    inc["vitals"].append({"name": "glucose", "value": 120})
    assert completeness.check(inc)["score"] == 100


def test_ner_last_known_well():
    from app.nlp.ner import extract
    assert extract("weakness of right arm, last known well at 08:40")["workflow"]["last_known_well"] == "08:40"


def test_clinical_clock():
    now = datetime.now().astimezone()
    t = lambda m: (now - timedelta(minutes=m)).strftime("%H:%M")
    inc = {"id": "I1", "status": "transporting", "triage": "RED", "vehicle": "KA-01", "complaint": "Road traffic accident",
           "created_at": (now - timedelta(minutes=70)).isoformat(), "workflow": {"call_received": t(65)}, "patient": {}, "records": [],
           "vitals": [{"name": "hr", "value": 120, "time": t(8), "created_at": now.isoformat()}],
           "entries": [{"id": "E1", "kind": "procedure", "name": "Haemorrhage control", "status": "confirmed", "created_at": now.isoformat(),
                        "payload": {"procedure": "Haemorrhage control", "device": "tourniquet", "time": t(70)}, "original": {}},
                       {"id": "E2", "kind": "medication", "name": "Fentanyl", "status": "confirmed", "created_at": now.isoformat(),
                        "payload": {"drug": "Fentanyl", "route": "IV", "time": t(16)}}]}
    by = {x["label"].split(" (")[0].split(":")[0]: x for x in clock.timers(inc, now)}
    assert by["Recheck vitals"]["status"] == "due"                    # RED -> every 5 min, last 8 min ago
    assert by["Tourniquet on"]["status"] == "due"                     # 70 min > 60 warn
    assert by["Golden hour"]["severity"] == "critical"                # 65 min since call
    assert by["Reassess pain after Fentanyl"]["status"] == "due"


def test_database_is_encrypted():
    info = db.info()
    if not info["sqlcipher_installed"]:
        pytest.skip("sqlcipher3 not installed")
    assert info["encrypted"]
    with open(db.DB_PATH, "rb") as f:
        assert f.read(16) != b"SQLite format 3\x00"


PG = os.environ.get("TEST_PG_URL")


@pytest.mark.skipif(not PG, reason="set TEST_PG_URL to test the PostgreSQL hub")
def test_postgres_hub(monkeypatch):
    monkeypatch.setenv("FIELDSCRIBE_HUB_URL", PG)
    monkeypatch.setenv("FIELDSCRIBE_AUTH", "0")
    from app import hub
    with TestClient(app) as c:
        c.post("/api/settings/online", json={"online": True})
        inc = c.post("/api/incidents", json={"place": "PG test"}).json()
        r = c.post("/api/sync/run").json()
        assert r["ok"] and r["hub"] == "postgresql" and r["queued"] == 0
        st = hub.status()
        assert st["ok"] and st["engine"] == "postgresql" and st["items"] >= 1
        c.post(f"/api/incidents/{inc['id']}/hub-edit")
        c.patch(f"/api/incidents/{inc['id']}", json={"triage": "RED"})
        r2 = c.post("/api/sync/run").json()
        assert r2["conflicts_now"] >= 1
        # idempotent: re-running sync with nothing queued keeps counts stable
        n = hub.status()["items"]
        c.post("/api/sync/run")
        assert hub.status()["items"] == n
    monkeypatch.setenv("FIELDSCRIBE_HUB_URL", "postgresql://fs@127.0.0.1:1/nope")
    with TestClient(app) as c:
        c.post("/api/incidents", json={"place": "PG down"})
        r = c.post("/api/sync/run").json()
        assert not r["ok"] and "unreachable" in r["error"] and r["queued"] >= 1


def test_pin_change_and_user_admin(auth_on):
  with TestClient(app) as c:
    with db.tx() as x:
        x.execute("UPDATE users SET failed=0, locked_until=0")
    assert c.get("/api/auth/users").json()["demo_pins"] is True
    c.post("/api/auth/login", json={"user_id": "emt07", "pin": "1080"})
    assert c.post("/api/auth/pin", json={"old": "0000", "new": "5831"}).status_code == 400
    assert c.post("/api/auth/pin", json={"old": "1080", "new": "1111"}).status_code == 400
    assert c.post("/api/auth/pin", json={"old": "1080", "new": "5831"}).json()["ok"]
    assert c.get("/api/admin/users").status_code == 403          # crew can't manage users
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"user_id": "emt07", "pin": "5831"}).status_code == 200
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"user_id": "admin", "pin": "9090"})
    rows = c.get("/api/admin/users").json()
    assert next(r for r in rows if r["id"] == "emt07")["pin_default"] is False
    assert c.post("/api/admin/users", json={"id": "emt99", "name": "EMT-99 Test", "role": "emt", "pin": "7302"}).json()["ok"]
    assert c.post("/api/admin/users", json={"id": "emt99", "name": "dup", "role": "emt", "pin": "7302"}).status_code == 400
    assert c.patch("/api/admin/users/admin", json={"active": False}).status_code == 400   # can't disable yourself
    assert c.patch("/api/admin/users/emt12", json={"active": False}).json()["ok"]
    assert "emt12" not in [u["id"] for u in c.get("/api/auth/users").json()["users"]]
    assert c.patch("/api/admin/users/emt12", json={"active": True, "pin": "6420"}).json()["ok"]
    h = c.get("/api/health/checks").json()
    keys = {i["key"] for i in h["items"]}
    assert {"database", "pins", "asr", "copilot", "map", "hub"} <= keys
    c.patch("/api/admin/users/emt07", json={"pin": "5831"})
    with db.tx() as x:   # put the demo PIN back for any later test
        x.execute("UPDATE users SET pin_hash=?, pin_default=1 WHERE id IN ('emt07','emt12')", (auth._hash("1080"),))
