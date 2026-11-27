"""Readiness checklist: every component of the device, whether it's ready, and the exact fix if not."""
from __future__ import annotations

import os
from pathlib import Path

from . import asr, auth, db


def _item(key, label, status, detail, fix=None, group="Core"):
    return {"key": key, "label": label, "status": status, "detail": detail, "fix": fix, "group": group}


def checks(dist: Path) -> dict:
    out = []
    out.append(_item("dashboard", "Dashboard", "ok" if (dist / "index.html").exists() else "fail",
                     "Built and served by the backend" if (dist / "index.html").exists() else "frontend/dist is missing",
                     "cd frontend; npm install; npm run build"))

    d = db.info()
    out.append(_item("database", "Device database", "ok" if d["encrypted"] else "warn",
                     f"{d['engine']} · {d['size_kb']} KB",
                     None if d["encrypted"] else ".\\.venv\\Scripts\\pip install -r backend\\requirements.txt  (installs SQLCipher), then restart",
                     "Security"))

    out.append(_item("pins", "Login PINs", "warn" if auth.enabled() and auth.demo_pins_in_use() else "ok",
                     ("Some accounts still use the demo PINs" if auth.demo_pins_in_use() else "All accounts have their own PINs")
                     if auth.enabled() else "Login is switched off (FIELDSCRIBE_AUTH=0)",
                     "Supervisor: Settings → Users → Reset PIN for each account. Everyone else: Settings → My account → Change PIN" if auth.enabled() else
                     "Remove FIELDSCRIBE_AUTH=0 from backend\\.env", "Security"))

    a = asr.status()
    name = str(a.get("model") or "")
    local = os.path.isdir(name)
    if not a["available"]:
        st, det, fix = "fail", "faster-whisper is not installed", ".\\.venv\\Scripts\\pip install -r backend\\requirements-asr.txt"
    elif a.get("error"):
        st, det, fix = "fail", a["error"][:160], "Check the model folder, or run: .\\.venv\\Scripts\\python backend\\fetch_model.py small"
    elif local:
        st, det, fix = "ok", f"Offline model: {Path(name).name} ({'loaded' if a['loaded'] else 'loads on first use'})", None
    else:
        st, det, fix = "warn", f"Model '{name}' will download from the internet on first use", \
            ".\\.venv\\Scripts\\python backend\\fetch_model.py large-v3-turbo   (or small for slower laptops)"
    out.append(_item("asr", "Speech recognition (Whisper)", st, det, fix, "AI models"))

    try:
        from .nlp import transformer_ner
        t = transformer_ner.status()
        if t["available"]:
            m = t.get("metrics") or {}
            f1 = m.get("f1") or (m.get("micro") or {}).get("f1") if isinstance(m, dict) else None
            out.append(_item("distilbert", "DistilBERT clinical NER", "ok",
                             "Trained model ready" + (f" · F1 {f1:.2f}" if isinstance(f1, (int, float)) else ""), None, "AI models"))
        else:
            out.append(_item("distilbert", "DistilBERT clinical NER", "warn",
                             "Not trained yet; rule + lexicon NER is running" if t["deps"] else "PyTorch / transformers not installed",
                             "train_distilbert_windows.bat" if t["deps"] else ".\\.venv\\Scripts\\pip install -r backend\\requirements-ml.txt", "AI models"))
    except Exception as e:  # pragma: no cover
        out.append(_item("distilbert", "DistilBERT clinical NER", "warn", str(e)[:120], None, "AI models"))

    from .agent import agent as copilot
    provs = copilot.status()["providers"]
    cloud = [p for p in provs if p["cloud"] and p["configured"]]
    out.append(_item("copilot", "Copilot (cloud AI)", "ok" if cloud else "warn",
                     ", ".join(f"{p['label']} · {p['model']}" for p in cloud) if cloud else "No cloud key; using the offline protocol engine",
                     None if cloud else "Add GEMINI_API_KEY (free, aistudio.google.com/apikey) to backend\\.env", "AI models"))
    from . import localai
    la = localai.status()
    if la["model"]:
        st, det, fix = "ok", f"{la['model']} on this laptop · works with no internet", None
    elif la["running"]:
        st, det, fix = "warn", "Ollama is running but no model is downloaded", f"Settings → Offline AI → Download {la['recommended']['label']} ({la['recommended']['size_gb']} GB)"
    elif la["installed"]:
        st, det, fix = "warn", "Ollama is installed but not running", "Settings → Offline AI → Start"
    else:
        st, det, fix = "warn", "Optional: not installed. The offline protocol engine covers it", "winget install Ollama.Ollama   then Settings → Offline AI → Download"
    out.append(_item("ollama", "Copilot offline AI (Ollama)", st, det, fix, "AI models"))

    from . import routing
    m = routing.MAP_FILE
    out.append(_item("map", "Offline street map", "ok" if m.exists() else "warn",
                     f"{round(m.stat().st_size / 1e6, 1)} MB of Bengaluru roads on the device" if m.exists() else
                     "Not downloaded; the live map is used when online",
                     None if m.exists() else ".\\.venv\\Scripts\\python backend\\fetch_map.py", "Maps"))

    from . import hub
    h = hub.status()
    if h["engine"] == "postgresql":
        out.append(_item("hub", "ED / state hub", "ok" if h.get("ok") else "fail",
                         "PostgreSQL connected" if h.get("ok") else (h.get("error") or "Unreachable")[:160],
                         None if h.get("ok") else "Check PostgreSQL is running and FIELDSCRIBE_HUB_URL in backend\\.env", "Sync"))
    else:
        out.append(_item("hub", "ED / state hub", "ok", "Built-in simulated hub (set FIELDSCRIBE_HUB_URL for PostgreSQL)", None, "Sync"))

    score = sum(1 for i in out if i["status"] == "ok")
    return {"items": out, "ok": score, "total": len(out),
            "ready": not any(i["status"] == "fail" for i in out)}
