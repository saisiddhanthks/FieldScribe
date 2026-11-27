"""
Offline Copilot brain: a local language model run by Ollama on this laptop.

* finds Ollama (PATH or the default Windows / macOS / Linux install locations) and starts `ollama serve` if it isn't running
* picks a model that fits this machine's memory (Qwen 2.5: good tool calling, multilingual incl. Hindi)
* downloads it from the app with live progress (one time, then it works with no internet)
* keeps it loaded so replies are quick, and exposes status for Settings, the readiness check and the Copilot badge
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import threading
import time
from pathlib import Path

import httpx

from . import db

def api() -> str:
    """Ollama's address (read each time so OLLAMA_URL in backend/.env or the environment always applies)."""
    b = (os.environ.get("OLLAMA_URL") or "http://127.0.0.1:11434/v1").strip().strip('"').rstrip("/")
    return b[:-3] if b.endswith("/v1") else b

# Ordered best → lightest. Sizes are Ollama's download sizes (q4).
CATALOG = [
    {"name": "qwen2.5:7b", "size_gb": 4.7, "min_ram_gb": 14, "label": "Qwen 2.5 · 7B", "note": "Best answers and tool use. Needs 16 GB RAM."},
    {"name": "qwen2.5:3b", "size_gb": 1.9, "min_ram_gb": 7, "label": "Qwen 2.5 · 3B", "note": "Good balance for 8 GB laptops."},
    {"name": "qwen2.5:1.5b", "size_gb": 1.0, "min_ram_gb": 0, "label": "Qwen 2.5 · 1.5B", "note": "Lightest. Simple guidance and logging."},
]


def ram_gb() -> float:
    try:
        if platform.system() == "Windows":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS(); m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.ullTotalPhys / 2**30, 1)
        if Path("/proc/meminfo").exists():
            kb = int(Path("/proc/meminfo").read_text().split("MemTotal:")[1].split()[0])
            return round(kb / 2**20, 1)
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3).stdout
        return round(int(out) / 2**30, 1)
    except Exception:
        return 8.0


def recommended() -> dict:
    r = ram_gb()
    return next(m for m in CATALOG if r >= m["min_ram_gb"])


def binary() -> str | None:
    p = shutil.which("ollama")
    if p:
        return p
    cands = []
    if platform.system() == "Windows":
        la = os.environ.get("LOCALAPPDATA", "")
        cands += [Path(la) / "Programs" / "Ollama" / "ollama.exe", Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Ollama" / "ollama.exe"]
    else:
        cands += [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama"), Path("/Applications/Ollama.app/Contents/Resources/ollama")]
    return next((str(c) for c in cands if c.exists()), None)


_up_cache: list = [False, 0.0]


def running(fresh: bool = False) -> bool:
    if not fresh and time.time() - _up_cache[1] < 5:
        return _up_cache[0]
    try:
        ok = httpx.get(api() + "/api/tags", timeout=1.2).status_code == 200
    except Exception:
        ok = False
    _up_cache[:] = [ok, time.time()]
    return ok


def models() -> list[dict]:
    try:
        r = httpx.get(api() + "/api/tags", timeout=3).json()
        return [{"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 2)} for m in r.get("models", [])]
    except Exception:
        return []


def start() -> dict:
    """Start `ollama serve` in the background if Ollama is installed and not already running."""
    if running(fresh=True):
        return {"ok": True, "already": True}
    exe = binary()
    if not exe:
        return {"ok": False, "error": "Ollama is not installed"}
    flags = 0
    if platform.system() == "Windows":
        flags = 0x08000000 | 0x00000200      # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    log = open(db.DATA_DIR / "ollama.log", "ab")
    subprocess.Popen([exe, "serve"], stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=flags,
                     start_new_session=platform.system() != "Windows")
    for _ in range(40):
        time.sleep(0.25)
        if running(fresh=True):
            return {"ok": True, "started": True}
    return {"ok": False, "error": "Ollama did not start. See backend data folder: ollama.log"}


def chosen_model() -> str | None:
    """The model Copilot will use: the configured one if present, else the best one already downloaded."""
    have = {m["name"] for m in models()}
    want = db.setting("ollama_model") or os.environ.get("OLLAMA_MODEL")
    if want and want in have:
        return want
    for m in CATALOG:
        if m["name"] in have:
            return m["name"]
    tools_ok = [n for n in have if n.split(":")[0] in ("qwen2.5", "qwen3", "llama3.1", "llama3.2", "mistral-nemo")]
    return tools_ok[0] if tools_ok else None


# ----------------------------------------------------------------------------- downloads (pull with progress)

_pull: dict = {"model": None, "status": "idle", "completed": 0, "total": 0, "error": None, "started": None}
_pull_lock = threading.Lock()


def _do_pull(name: str) -> None:
    try:
        with httpx.stream("POST", api() + "/api/pull", json={"model": name, "stream": True}, timeout=httpx.Timeout(30, read=600)) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.read()[:200]!r}")
            for line in r.iter_lines():
                if not line:
                    continue
                ev = json.loads(line)
                if ev.get("error"):
                    raise RuntimeError(ev["error"])
                _pull["status"] = ev.get("status", _pull["status"])
                if ev.get("total"):
                    _pull["total"], _pull["completed"] = ev["total"], ev.get("completed", 0)
        _pull.update(status="success", error=None)
        db.set_setting("ollama_model", name)
        warm(name)
    except Exception as e:
        msg = str(e)
        if "ConnectError" in type(e).__name__ or "connect" in msg.lower():
            msg = "No internet connection. The model downloads once; after that it works offline."
        _pull.update(status="error", error=msg[:300])


def pull(name: str) -> dict:
    if name not in {m["name"] for m in CATALOG}:
        raise ValueError("Choose one of the listed models")
    with _pull_lock:
        if _pull["status"] not in ("idle", "success", "error"):
            return progress()
        if not running(fresh=True):
            s = start()
            if not s["ok"]:
                raise ValueError(s["error"])
        _pull.update(model=name, status="starting", completed=0, total=0, error=None, started=time.time())
        threading.Thread(target=_do_pull, args=(name,), daemon=True).start()
    return progress()


def progress() -> dict:
    p = dict(_pull)
    p["percent"] = round(100 * p["completed"] / p["total"], 1) if p["total"] else None
    return p


def warm(name: str | None = None) -> None:
    """Load the model into memory (kept 30 min) so the first Copilot reply isn't slow."""
    name = name or chosen_model()
    if not name:
        return
    try:
        httpx.post(api() + "/api/generate", json={"model": name, "prompt": "", "keep_alive": "30m"}, timeout=120)
    except Exception:
        pass


def test(name: str | None = None) -> dict:
    name = name or chosen_model()
    if not name:
        return {"ok": False, "error": "No local model downloaded yet"}
    t0 = time.perf_counter()
    try:
        r = httpx.post(api() + "/api/chat", json={"model": name, "stream": False, "keep_alive": "30m", "options": {"temperature": 0, "num_ctx": 2048},
                                                "messages": [{"role": "user", "content": "In one short sentence: first step for a choking adult who can still cough?"}]},
                       timeout=180)
        r.raise_for_status()
        txt = r.json()["message"]["content"].strip()
        return {"ok": True, "model": name, "reply": txt[:400], "seconds": round(time.perf_counter() - t0, 1)}
    except Exception as e:
        return {"ok": False, "model": name, "error": str(e)[:300]}


def status() -> dict:
    up = running(fresh=True)
    have = models() if up else []
    rec = recommended()
    return {
        "installed": bool(binary()) or up, "running": up, "url": api(), "ram_gb": ram_gb(), "recommended": rec, "catalog": CATALOG,
        "models": have, "model": chosen_model() if up else None, "prefer_offline": prefer_offline(), "pull": progress(),
        "install_hint": "winget install Ollama.Ollama   (or download from ollama.com)",
    }


def prefer_offline() -> bool:
    return (db.setting("ai_prefer_offline") or "0") == "1"


def set_prefer_offline(v: bool) -> None:
    db.set_setting("ai_prefer_offline", "1" if v else "0")


def boot() -> None:
    """Called at FieldScribe start: bring Ollama up and warm the model, without delaying startup."""
    if os.environ.get("FIELDSCRIBE_OLLAMA", "1") == "0":
        return

    def go():
        if not running(fresh=True) and binary():
            start()
        if running(fresh=True):
            warm()
    threading.Thread(target=go, daemon=True).start()
