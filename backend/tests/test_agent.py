"""Copilot tests: offline engine end to end, and the Gemini / OpenAI-compatible tool loops
against a simulated model (so they run without network or keys)."""
import json
import os
import tempfile

os.environ["FIELDSCRIBE_DATA"] = tempfile.mkdtemp()
os.environ["FIELDSCRIBE_AUTH"] = "0"
for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
    os.environ.pop(k, None)
os.environ["FIELDSCRIBE_AGENT_ORDER"] = "gemini,groq,offline"

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.agent import agent as A  # noqa: E402


def _new_incident(c):
    return c.post("/api/incidents", json={"place": "Test", "crew": "EMT-99 Test"}).json()["id"]


def test_offline_first_aid_and_logging():
    with TestClient(app) as c:
        iid = _new_incident(c)
        r = c.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "58 year old man, crushing chest pain, sweating, bp 150/90"}],
                                            "incident_id": iid}).json()
        assert r["provider"]["name"] == "offline"
        assert r["protocols"] and r["protocols"][0]["id"] == "chest_pain"
        assert "Aspirin" in r["reply"]
        # vitals in the description were logged
        assert r["logged"] and r["logged"][0]["vitals"]
        r2 = c.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "gave ecosprin 300 mg chewed at 10:42"}],
                                             "incident_id": iid}).json()
        assert r2["logged"][0]["entries"][0]["name"] == "Aspirin"
        inc = c.get(f"/api/incidents/{iid}").json()
        assert any(e["name"] == "Aspirin" for e in inc["entries"])
        assert any(r_["source"] == "agent" for r_ in inc["records"])
        assert inc["integrity"]["valid"]


def test_offline_critical_needs_confirmation():
    with TestClient(app) as c:
        iid = _new_incident(c)
        c.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "patient allergic to aspirin, bp 130/80"}], "incident_id": iid})
        r = c.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "gave aspirin 300 mg oral"}], "incident_id": iid}).json()
        assert r["pending"] and not r["logged"]
        assert "allergy" in r["reply"].lower()
        r2 = c.post("/api/agent/confirm", json={"pending": r["pending"]}).json()
        assert r2["logged"][0]["entries"][0]["name"] == "Aspirin"
        # a second confirm of the same item must not double-log
        r3 = c.post("/api/agent/confirm", json={"pending": r["pending"]}).json()
        assert not r3["logged"]


def test_safe_items_logged_while_flagged_item_held():
    with TestClient(app) as c:
        iid = _new_incident(c)
        r = c.post("/api/agent/chat", json={"messages": [{"role": "user", "content":
               "patient allergic to diclofenac. tourniquet applied at 10:05, txa 1 g iv given, voveran 75 mg im"}], "incident_id": iid}).json()
        logged = [e["name"] for e in r["logged"][0]["entries"]]
        assert "Tranexamic acid" in logged and "Haemorrhage control" in logged and "Diclofenac" not in logged
        assert r["pending"]["items"] == ["Diclofenac"]


def test_offline_opens_incident_when_none_selected():
    with TestClient(app) as c:
        r = c.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "snake bite on the leg 20 minutes ago, swelling"}]}).json()
        assert r["opened"] and r["protocols"][0]["id"] == "snake_bite"
        assert "Do not" in r["reply"]


def _mock_client(handler):
    real = httpx.Client

    class C(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **k)
    return C


def test_gemini_tool_loop(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    calls = {"n": 0}

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        calls["n"] += 1
        assert req.headers["x-goog-api-key"] == "test-key"
        last = body["contents"][-1]
        if calls["n"] == 1:
            return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [
                {"functionCall": {"name": "find_protocols", "args": {"description": "anaphylaxis"}}, "thoughtSignature": "sig1"}]}}]})
        if calls["n"] == 2:
            assert "functionResponse" in last["parts"][0]
            # thought signature preserved in history
            assert body["contents"][-2]["parts"][0]["thoughtSignature"] == "sig1"
            return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [
                {"functionCall": {"name": "log_care", "args": {"statement": "adrenaline 0.5 mg im at 14:11"}}}]}}]})
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "Adrenaline logged. Lie flat, oxygen."}]}}]})

    monkeypatch.setattr(A.httpx, "Client", _mock_client(handler))
    with TestClient(app) as c:
        iid = _new_incident(c)
        c.post("/api/settings/online", json={"online": True})
        r = c.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "lip swelling after bee sting, gave adrenaline"}], "incident_id": iid}).json()
        assert r["provider"]["name"] == "gemini"
        assert [t["name"] for t in r["tool_calls"]] == ["find_protocols", "log_care"]
        assert r["logged"][0]["entries"][0]["name"] == "Adrenaline"


def test_fallback_to_groq_then_offline(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "bad")
    monkeypatch.setenv("GROQ_API_KEY", "g")

    def handler(req: httpx.Request):
        if "generativelanguage" in str(req.url):
            return httpx.Response(429, json={"error": {"message": "quota"}})
        body = json.loads(req.content)
        if body["messages"][-1]["role"] == "user":
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "list_active_incidents", "arguments": "{}"}}]}}]})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "3 units active."}}]})

    monkeypatch.setattr(A.httpx, "Client", _mock_client(handler))
    with TestClient(app) as c:
        r = c.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "how many units are active?"}]}).json()
        assert r["provider"]["name"] == "groq"
        assert r["fallbacks"][0]["provider"] == "gemini"
        assert "bad" not in json.dumps(r)  # key never echoed


def test_offline_mode_skips_cloud(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    with TestClient(app) as c:
        c.post("/api/settings/online", json={"online": False})
        r = c.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "patient having fits"}]}).json()
        assert r["provider"]["name"] == "offline"
        assert r["fallbacks"][0]["error"] == "device offline"
        c.post("/api/settings/online", json={"online": True})


def test_status_never_returns_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret")
    with TestClient(app) as c:
        s = c.get("/api/agent/status").json()
        assert "super-secret" not in json.dumps(s)
        assert s["active"]["name"] == "gemini"
