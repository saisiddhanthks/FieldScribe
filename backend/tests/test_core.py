import os
import tempfile

os.environ["FIELDSCRIBE_DATA"] = tempfile.mkdtemp()
os.environ["FIELDSCRIBE_AUTOSEED"] = "1"
os.environ["FIELDSCRIBE_AUTH"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.nlp.ner import extract, normalise  # noqa: E402


def meds(text):
    return [e for e in extract(text)["entities"] if e["kind"] == "medication"]


def f(e, k):
    return e["fields"][k]["value"]


def test_deck_example():
    m = meds("Gave aspirin 300 mg oral at 10:42, started IV normal saline 500 ml, oxygen 4 litres by mask.")
    assert [f(e, "drug") for e in m] == ["Aspirin", "Normal saline", "Oxygen"]
    assert f(m[0], "dose") == 300 and f(m[0], "route") == "PO" and f(m[0], "time") == "10:42"
    assert f(m[1], "route") == "IV" and f(m[1], "unit") == "mL"
    assert f(m[2], "rate") == "4 L/min" and f(m[2], "device") == "face mask"


def test_spoken_numbers_and_time():
    assert normalise("ecosprin three hundred milligram at ten forty two") == "ecosprin 300 milligram at 10:42"


def test_brand_hinglish():
    m = meds("patient ko avil diya 22.75 mg IM")
    assert f(m[0], "drug") == "Pheniramine" and f(m[0], "dose") == 22.75 and f(m[0], "route") == "IM"


def test_negation_and_allergy_conflict():
    r = extract("allergic to aspirin. ecosprin 300 mg chewed. no morphine given")
    ms = [e for e in r["entities"] if e["kind"] == "medication"]
    assert len(ms) == 2
    assert any(x["code"] == "ALLERGY_CONFLICT" for x in ms[0]["flags"])
    assert ms[1]["negated"]


def test_fuzzy_flagged():
    m = meds("gave ondansatron 4 mg iv")
    assert f(m[0], "drug") == "Ondansetron"
    assert any(x["code"] == "ASR_UNCERTAIN" for x in m[0]["flags"])


def test_unit_implausible():
    m = meds("adrenaline 50 mg im")
    assert any(x["code"] == "UNIT_IMPLAUSIBLE" for x in m[0]["flags"])


def test_api_flow_and_tamper():
    with TestClient(app) as c:
        inc = c.post("/api/incidents", json={"place": "Test", "crew": "EMT-99 Test"}).json()
        ex = c.post("/api/extract", json={"text": "aspirin 300 mg oral at 10:42. bp 120/80", "incident_id": inc["id"]}).json()
        ents = [dict(e, status="confirmed") for e in ex["entities"]]
        r = c.post(f"/api/incidents/{inc['id']}/records", json={"final_text": ex["input"], "entries": ents, "vitals": ex["vitals"]}).json()
        assert r["entries"] == 1
        assert c.get("/api/ledger/verify").json()["valid"]
        fh = c.get(f"/api/incidents/{inc['id']}/fhir").json()
        types = {e["resource"]["resourceType"] for e in fh["entry"]}
        assert {"MedicationAdministration", "Observation", "Provenance"} <= types
        assert c.get(f"/api/incidents/{inc['id']}/pdf").status_code == 200
        t = c.post("/api/ledger/tamper").json()
        assert not t["verify"]["valid"]
        assert c.post("/api/ledger/restore").json()["verify"]["valid"]
        # duplicate dose detection uses incident history
        ex2 = c.post("/api/extract", json={"text": "aspirin 300 mg oral", "incident_id": inc["id"]}).json()
        assert any(a["code"] == "DUPLICATE_DOSE" for a in ex2["alerts"])


def test_offline_queue():
    with TestClient(app) as c:
        c.post("/api/settings/online", json={"online": False})
        assert not c.post("/api/sync/run").json()["ok"]
        r = c.post("/api/settings/online", json={"online": True}).json()
        assert r["sync"]["queued"] == 0


def test_eval_quality_floor():
    from app.evaluation import run
    r = run(10)
    assert r["entity"]["f1"] >= 0.9
    assert r["silent_critical_error_rate"] <= 0.05


def test_hybrid_compare_runs_without_model():
    from app.evaluation import compare
    r = compare(60)
    assert "rules" in r["engines"]
    assert r["engines"]["rules"]["detection_recall"] > 0.5


def test_hybrid_merge_with_simulated_model(monkeypatch):
    """Exercise the rules+DistilBERT merge without torch by simulating model spans."""
    from app.nlp import ner, transformer_ner
    text = "gave levipil 500 mg iv, patient stable after"

    def fake_predict(t):
        out = []
        for w, lab, p in [("levipil", "DRUG", 0.95), ("500", "DOSE", 0.99), ("stable", "DRUG", 0.9), ("after", "DRUG", 0.9)]:
            i = t.find(w)
            out.append({"start": i, "end": i + len(w), "label": lab, "score": p, "text": w})
        return out
    monkeypatch.setattr(transformer_ner, "available", lambda: True)
    monkeypatch.setattr(transformer_ner, "predict", fake_predict)
    r = ner.extract(text)
    meds = [e for e in r["entities"] if e["kind"] == "medication"]
    assert [e["text"] for e in meds] == ["levipil"]          # 'stable'/'after' rejected: stopword, no drug context
    assert any(f["code"] == "UNKNOWN_DRUG" and f["level"] == "critical" for f in meds[0]["flags"])


def test_routes_fallback_estimate():
    from app import routing
    r = routing.estimate((12.9177, 77.6233), (12.9173, 77.5996))
    assert r["source"] == "estimate" and 2000 < r["distance_m"] < 5000
    with TestClient(app) as c:
        out = c.get("/api/routes").json()
        assert "routes" in out
        for rt in out["routes"]:
            assert len(rt["position"]) == 2 and rt["duration_s"] > 0


def test_offline_road_routing(tmp_path, monkeypatch):
    from app import routing
    from tests.synthetic_map import make
    f = tmp_path / "map.json"
    make(f)
    monkeypatch.setattr(routing, "MAP_FILE", f)
    routing._G.clear(); routing._mem.clear()
    a, b = (12.9177, 77.6233), (12.9173, 77.5996)       # Silk Board -> Jayadeva
    r = routing.route(a, b, online=False)
    assert r["source"] == "offline-roads"
    straight = routing.haversine_m(a, b)
    assert straight <= r["distance_m"] <= straight * 2.0
    assert len(r["coords"]) > 3 and r["duration_s"] > 0
    st = routing.map_status()
    assert st["available"] and st["nodes"] > 1000
    with TestClient(app) as c:
        assert c.get("/api/map/status").json()["available"]
    routing._G.clear(); routing._mem.clear()
