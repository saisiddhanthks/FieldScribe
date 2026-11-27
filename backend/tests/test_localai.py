"""Offline Copilot through Ollama: a fake Ollama server stands in for the real one."""
import json
import os
import socket
import tempfile
import threading
import time

os.environ.setdefault("FIELDSCRIBE_DATA", tempfile.mkdtemp())
os.environ["FIELDSCRIBE_AUTH"] = "0"
os.environ["FIELDSCRIBE_OLLAMA"] = "0"          # don't try to launch a real Ollama during tests

import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402

_s = socket.socket(); _s.bind(("127.0.0.1", 0)); PORT = _s.getsockname()[1]; _s.close()
os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{PORT}/v1"

fake = FastAPI()
STATE = {"models": [], "chat_calls": [], "pulled": []}


@fake.get("/api/tags")
def tags():
    return {"models": [{"name": m, "size": 1_900_000_000} for m in STATE["models"]]}


@fake.post("/api/pull")
async def pull(req: Request):
    body = await req.json()

    def gen():
        for done in (0, 950, 1900):
            yield json.dumps({"status": "pulling", "total": 1900, "completed": done}) + "\n"
        STATE["models"].append(body["model"]); STATE["pulled"].append(body["model"])
        yield json.dumps({"status": "success"}) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")


@fake.post("/api/generate")
async def gen_(req: Request):
    return {"response": "", "done": True}


@fake.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    STATE["chat_calls"].append(body)
    if body.get("tools") and not any(m["role"] == "tool" for m in body["messages"]):
        return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "verify_audit_chain", "arguments": {}}}]}}
    return {"message": {"role": "assistant", "content": "Audit chain checked on this laptop. Keep the airway clear."}}


threading.Thread(target=lambda: uvicorn.run(fake, host="127.0.0.1", port=PORT, log_level="error"), daemon=True).start()
for _ in range(50):
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.2).close(); break
    except OSError:
        time.sleep(0.1)

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import db, localai  # noqa: E402


def test_recommendation_fits_memory():
    rec = localai.recommended()
    assert rec["name"] in {m["name"] for m in localai.CATALOG}
    assert localai.ram_gb() >= rec["min_ram_gb"]


def test_pull_then_offline_copilot_uses_local_model(monkeypatch):
    monkeypatch.setenv("FIELDSCRIBE_AGENT_ORDER", "gemini,groq,openai,ollama,offline")
    monkeypatch.setenv("OLLAMA_URL", f"http://127.0.0.1:{PORT}/v1")
    with TestClient(app) as c:
        st = c.get("/api/localai").json()
        assert st["running"] is True and st["model"] is None
        assert c.post("/api/localai/pull", json={"model": "nonsense:1b"}).status_code == 400
        c.post("/api/localai/pull", json={"model": "qwen2.5:3b"})
        for _ in range(50):
            p = c.get("/api/localai/progress").json()
            if p["status"] in ("success", "error"):
                break
            time.sleep(0.1)
        assert p["status"] == "success", p
        assert c.get("/api/localai").json()["model"] == "qwen2.5:3b"

        localai.running(fresh=True)
        db.set_setting("online", "0")                      # dead zone: cloud providers are skipped
        try:
            r = c.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "verify the audit chain"}]}).json()
        finally:
            db.set_setting("online", "1")
        assert r["provider"]["name"] == "ollama" and r["provider"]["model"] == "qwen2.5:3b" and r["provider"]["cloud"] is False
        assert "Audit chain checked" in r["reply"]
        assert any(t["name"] == "verify_audit_chain" for t in r["tool_calls"])
        last = STATE["chat_calls"][-1]
        assert last["options"]["num_ctx"] >= 8192 and last["keep_alive"] == "30m"
        assert any(m["role"] == "tool" and m.get("tool_name") == "verify_audit_chain" for m in last["messages"])


def test_prefer_offline_puts_local_ai_first(monkeypatch):
    monkeypatch.setenv("FIELDSCRIBE_AGENT_ORDER", "gemini,groq,openai,ollama,offline")
    monkeypatch.setenv("OLLAMA_URL", f"http://127.0.0.1:{PORT}/v1")
    with TestClient(app) as c:
        c.post("/api/localai/prefer", json={"on": True})
        from app.agent import agent
        assert agent.provider_config()[0]["name"] == "ollama"
        c.post("/api/localai/prefer", json={"on": False})
        assert agent.provider_config()[0]["name"] != "ollama"
