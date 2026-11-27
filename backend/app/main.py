"""FieldScribe API - offline-first edge server for EMS documentation."""
from __future__ import annotations

import os
import platform
import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import load_env

load_env()

from . import asr, audit, auth, db, evaluation, fhir, pdf, services  # noqa: E402
from .agent import agent as copilot, protocols as protocol_cards  # noqa: E402
from .nlp import lexicon as L
from .nlp.ner import extract

app = FastAPI(title="FieldScribe API", version="2.1.0",
              description="Offline voice-to-structured clinical record generator for first responders.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=2048)


@app.middleware("http")
async def _auth_mw(request, call_next):
    right = auth.required_right(request.method, request.url.path)
    if right is None or not auth.enabled():
        tok = auth.CURRENT.set(None if auth.enabled() else auth.DEV_USER)
        try:
            return await call_next(request)
        finally:
            auth.CURRENT.reset(tok)
    token = request.cookies.get("fs_token")
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        token = h[7:].strip()
    user = auth.session(token)
    if not user:
        return JSONResponse({"detail": "Login required", "code": "AUTH"}, status_code=401)
    if right not in user["rights"]:
        return JSONResponse({"detail": f"Your role ({user['role']}) cannot do this", "code": "ROLE"}, status_code=403)
    tok = auth.CURRENT.set(user)
    try:
        return await call_next(request)
    finally:
        auth.CURRENT.reset(tok)
START = time.time()


_STARTED = False


@app.on_event("startup")
def _startup():
    global _STARTED
    if _STARTED:          # tablet mode serves HTTP and HTTPS from one process: start-up work runs once
        return
    _STARTED = True
    db.get()
    auth.ensure_users()
    audit.key()
    from .nlp import transformer_ner
    if transformer_ner.available():
        import threading
        threading.Thread(target=transformer_ner._load, daemon=True).start()  # warm DistilBERT in the background
    from . import localai
    localai.boot()                       # start Ollama + warm the local model in the background
    if os.environ.get("FIELDSCRIBE_AUTOSEED", "1") == "1" and not db.q1("SELECT id FROM incidents LIMIT 1"):
        from .seed import seed
        seed()


# ------------------------------------------------------------------ models

class ExtractIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    incident_id: str | None = None


class IncidentIn(BaseModel):
    vehicle: str | None = None
    crew: str | None = None
    complaint: str | None = None
    place: str | None = None
    lat: float | None = None
    lng: float | None = None
    destination: str | None = None
    eta_min: int | None = None
    triage: str | None = None
    dispatch_id: str | None = None


class IncidentPatch(BaseModel):
    status: str | None = None
    destination: str | None = None
    eta_min: int | None = None
    triage: str | None = None
    complaint: str | None = None
    workflow: dict | None = None
    actor: str | None = None


class RecordIn(BaseModel):
    source: str = "text"
    asr_text: str | None = None
    final_text: str
    capture_ms: int | None = None
    signer: str | None = None
    entries: list[dict] = []
    vitals: list[dict] = []
    patient: dict = {}
    workflow: dict = {}
    alerts: list[dict] = []
    stats: dict | None = None
    asr_meta: dict | None = None


class HandoverIn(BaseModel):
    received_by: str | None = None


class OnlineIn(BaseModel):
    online: bool


class WerIn(BaseModel):
    reference: str
    hypothesis: str


# ------------------------------------------------------------------ system

class LoginIn(BaseModel):
    user_id: str
    pin: str = Field(..., max_length=12)


@app.get("/api/auth/users")
def auth_users():
    return {"enabled": auth.enabled(), "users": auth.users(), "demo_pins": auth.enabled() and auth.demo_pins_in_use()}


class PinIn(BaseModel):
    old: str = Field(..., max_length=12)
    new: str = Field(..., max_length=12)


@app.post("/api/auth/pin")
def auth_pin(body: PinIn):
    if not auth.enabled():
        raise HTTPException(400, "Login is switched off")
    r = auth.change_pin(auth.current()["id"], body.old, body.new)
    if not r["ok"]:
        raise HTTPException(400, r["error"])
    return r


class UserIn(BaseModel):
    id: str = Field(..., max_length=24)
    name: str = Field(..., max_length=60)
    role: str
    pin: str = Field(..., max_length=12)


class UserPatch(BaseModel):
    active: bool | None = None
    pin: str | None = Field(None, max_length=12)
    name: str | None = Field(None, max_length=60)
    role: str | None = None


@app.get("/api/admin/users")
def admin_users():
    return auth.admin_list()


@app.post("/api/admin/users")
def admin_user_create(body: UserIn):
    r = auth.admin_create(body.id, body.name, body.role, body.pin)
    if not r["ok"]:
        raise HTTPException(400, r["error"])
    return r


@app.patch("/api/admin/users/{uid}")
def admin_user_update(uid: str, body: UserPatch):
    r = auth.admin_update(uid, auth.current()["id"], body.active, body.pin, body.name, body.role)
    if not r["ok"]:
        raise HTTPException(400, r["error"])
    return r


class PullIn(BaseModel):
    model: str


class PreferIn(BaseModel):
    on: bool


@app.get("/api/localai")
def localai_status():
    from . import localai
    return localai.status()


@app.post("/api/localai/start")
def localai_start():
    from . import localai
    return localai.start()


@app.post("/api/localai/pull")
def localai_pull(body: PullIn):
    from . import localai
    try:
        return localai.pull(body.model)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/localai/progress")
def localai_progress():
    from . import localai
    return localai.progress()


@app.post("/api/localai/test")
def localai_test():
    from . import localai
    return localai.test()


@app.post("/api/localai/prefer")
def localai_prefer(body: PreferIn):
    from . import localai
    localai.set_prefer_offline(body.on)
    return {"prefer_offline": localai.prefer_offline()}


@app.get("/api/health/checks")
def health_checks():
    from . import health as H
    return H.checks(DIST)


@app.post("/api/auth/login")
def auth_login(body: LoginIn):
    r = auth.login(body.user_id, body.pin)
    if not r["ok"]:
        return JSONResponse({"detail": r["error"], "locked": r.get("locked", False)}, status_code=401)
    resp = JSONResponse({"user": r["user"], "token": r["token"]})
    resp.set_cookie("fs_token", r["token"], httponly=True, samesite="strict", max_age=auth.MAX_S)
    return resp


@app.get("/api/auth/me")
def auth_me(request: Request):
    """Public: tells the app whether this browser is signed in (user is null if not)."""
    if not auth.enabled():
        return {"user": auth.DEV_USER, "enabled": False}
    tok = request.cookies.get("fs_token") or request.headers.get("authorization", "")[7:]
    return {"user": auth.session(tok), "enabled": True}


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    auth.logout(request.cookies.get("fs_token") or request.headers.get("authorization", "")[7:])
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("fs_token")
    return resp


@app.get("/api/health")
def health():
    return {"ok": True, "uptime_s": round(time.time() - START)}


def _tn_status():
    from .nlp import transformer_ner
    return transformer_ner.status()


@app.get("/api/system")
def system():
    return {
        "version": app.version, "python": platform.python_version(), "platform": platform.platform(),
        "asr": asr.status(), "transformer_ner": _tn_status(), "ner": {"engine": "fieldscribe-hybrid-ner 2.2", "drugs": len(L.DRUGS), "procedures": len(L.PROCEDURES),
                                     "aliases": sum(len(d["aliases"]) for d in L.DRUGS.values())},
        "device_key": {"key_id": audit.key_id(), "public_key": audit.public_key_b64(), "algorithm": "Ed25519"},
        "online": services.is_online(), "db": str(db.DB_PATH.name),
        "counts": {t: db.q1(f"SELECT COUNT(*) n FROM {t}")["n"] for t in ("incidents", "records", "entries", "vitals", "ledger", "outbox")},
        "database": db.info(), "hub": __import__("app.hub", fromlist=["status"]).status(),
        "privacy": "All processing on-device. No PHI leaves the device except via explicit sync to the configured ED hub.",
    }


@app.post("/api/settings/online")
def set_online(body: OnlineIn):
    db.set_setting("online", "1" if body.online else "0")
    out = {"online": body.online}
    if body.online:
        out["sync"] = services.run_sync()
    return out


# ------------------------------------------------------------------ NLP / ASR

@app.post("/api/extract")
def api_extract(body: ExtractIn):
    t0 = time.perf_counter()
    r = extract(body.text, services.history_for(body.incident_id))
    r["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return r


@app.post("/api/asr")
async def api_asr(file: UploadFile = File(...), language: str = Form("en")):
    if not asr.AVAILABLE:
        raise HTTPException(503, "Offline ASR engine not installed. pip install faster-whisper, then restart.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty audio")
    suffix = Path(file.filename or "a.webm").suffix or ".webm"
    try:
        if language not in asr.LANGS:
            language = "en"
        r = asr.transcribe(data, suffix, None if language == "auto" else language)
        if r.get("text"):
            from .nlp import indic
            mix = indic.to_english(r["text"])
            r["code_mixed"] = {"mixed": mix["mixed"], "language": mix.get("language"), "english": mix["text"] if mix["mixed"] else None}
        return r
    except Exception as e:
        raise HTTPException(500, f"ASR failed: {e}")


@app.post("/api/asr/warmup")
def asr_warmup():
    if not asr.AVAILABLE:
        raise HTTPException(503, "faster-whisper not installed")
    t0 = time.perf_counter()
    asr._load()
    return {"loaded": True, "seconds": round(time.perf_counter() - t0, 2), **asr.status()}


@app.post("/api/wer")
def api_wer(body: WerIn):
    return asr.wer(body.reference, body.hypothesis)


# ------------------------------------------------------------------ incidents

@app.get("/api/incidents")
def incidents(status: str | None = None):
    return services.list_incidents(status)


@app.post("/api/incidents")
def new_incident(body: IncidentIn):
    return services.create_incident(body.model_dump(exclude_none=True))


@app.get("/api/incidents/{iid}")
def incident(iid: str):
    inc = services.get_incident(iid)
    if not inc:
        raise HTTPException(404, "incident not found")
    inc["integrity"] = audit.verify(iid)
    from . import clock, completeness
    inc["completeness"] = completeness.check(inc)
    inc["clock"] = clock.timers(inc)
    from . import field
    inc["mlc_suggest"] = field.mlc_suggest(inc)
    field.log_access(iid, auth.CURRENT.get(), "viewed")
    return inc


# ------------------------------------------------------------------ field: hospital choice, MLC, ABHA, refusal, access, MCI

class PatientIn(BaseModel):
    abha: str | None = Field(None, max_length=40)
    name: str | None = Field(None, max_length=120)
    relative_name: str | None = Field(None, max_length=120)
    relative_phone: str | None = Field(None, max_length=20)
    address: str | None = Field(None, max_length=120)
    age: int | None = Field(None, ge=0, le=120)
    sex: str | None = None


class MlcIn(BaseModel):
    is_mlc: bool
    category: str | None = None
    police_station: str | None = None
    informed: bool = False
    informed_at: str | None = None
    officer: str | None = None
    gd_number: str | None = None
    brought_by: str | None = None
    belongings: str | None = None
    reason: str | None = None


class RefusalIn(BaseModel):
    what: str = "both"
    reason: str | None = None
    risks_explained: bool = False
    capacity: str | None = None
    signed_by: str | None = None
    relation: str | None = None
    witness: str | None = None
    advice_given: str | None = None
    signature: str = Field("", max_length=420000)


class MciIn(BaseModel):
    name: str | None = None
    place: str | None = None
    lat: float | None = None
    lng: float | None = None


class CasualtyIn(BaseModel):
    triage: str
    note: str | None = None
    start: dict | None = None


class RetriageIn(BaseModel):
    triage: str


def _actor() -> str:
    return auth.current()["name"]


def _field_call(fn, *a):
    from . import field  # noqa: F401
    try:
        return fn(*a)
    except KeyError:
        raise HTTPException(404, "not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/incidents/{iid}/destinations")
def incident_destinations(iid: str):
    from . import field
    return _field_call(field.destinations, iid)


@app.post("/api/incidents/{iid}/patient")
def incident_patient(iid: str, body: PatientIn):
    from . import field
    return _field_call(field.update_patient, iid, body.model_dump(exclude_unset=True), _actor())


@app.post("/api/incidents/{iid}/mlc")
def incident_mlc(iid: str, body: MlcIn):
    from . import field
    if not db.q1("SELECT id FROM incidents WHERE id=?", (iid,)):
        raise HTTPException(404, "not found")
    return _field_call(field.set_mlc, iid, body.model_dump(), _actor())


@app.post("/api/incidents/{iid}/refusal")
def incident_refusal(iid: str, body: RefusalIn):
    from . import field
    if not db.q1("SELECT id FROM incidents WHERE id=?", (iid,)):
        raise HTTPException(404, "not found")
    return _field_call(field.set_refusal, iid, body.model_dump(), _actor())


@app.get("/api/incidents/{iid}/access")
def incident_access(iid: str):
    from . import field
    return field.access(iid)


@app.get("/api/mci")
def mci_get():
    from . import field
    return {"active": field.mci_active()}


@app.post("/api/mci")
def mci_post(body: MciIn):
    from . import field
    return _field_call(field.mci_start, body.name or "", body.place or "", _actor(), body.lat, body.lng)


@app.post("/api/mci/{eid}/casualty")
def mci_casualty(eid: str, body: CasualtyIn):
    from . import field
    return _field_call(field.mci_add, eid, body.triage, body.note or "", _actor(), body.start)


@app.post("/api/mci/retriage/{iid}")
def mci_retriage(iid: str, body: RetriageIn):
    from . import field
    return _field_call(field.mci_retriage, iid, body.triage, _actor())


@app.post("/api/mci/{eid}/close")
def mci_close(eid: str):
    from . import field
    return _field_call(field.mci_close, eid, _actor())


@app.patch("/api/incidents/{iid}")
def patch_incident(iid: str, body: IncidentPatch):
    try:
        return services.update_incident(iid, body.model_dump(exclude_none=True, exclude={"actor"}), body.actor or "EMT")
    except KeyError:
        raise HTTPException(404, "incident not found")


@app.post("/api/incidents/{iid}/records")
def sign(iid: str, body: RecordIn):
    try:
        d = body.model_dump()
        d["signer"] = auth.current()["name"] if auth.enabled() else (d.get("signer") or None)
        return services.sign_record(iid, d)
    except KeyError:
        raise HTTPException(404, "incident not found")


@app.post("/api/incidents/{iid}/handover")
def do_handover(iid: str, body: HandoverIn):
    try:
        return services.handover(iid, auth.current()["name"] if auth.enabled() else body.received_by)
    except KeyError:
        raise HTTPException(404, "incident not found")


def _bundle_parts(iid: str):
    inc = services.get_incident(iid)
    if not inc:
        raise HTTPException(404, "incident not found")
    return inc, inc["entries"], inc["vitals"]


class AmendIn(BaseModel):
    fields: dict = {}
    reason: str


class VoidIn(BaseModel):
    reason: str


@app.post("/api/entries/{eid}/amend")
def amend(eid: str, body: AmendIn):
    try:
        return services.amend_entry(eid, body.fields, body.reason, auth.current()["name"])
    except KeyError:
        raise HTTPException(404, "entry not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/entries/{eid}/void")
def void(eid: str, body: VoidIn):
    try:
        return services.void_entry(eid, body.reason, auth.current()["name"])
    except KeyError:
        raise HTTPException(404, "entry not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/incidents/{iid}/completeness")
def completeness_ep(iid: str):
    from . import completeness
    r = completeness.for_incident(iid)
    if r is None:
        raise HTTPException(404, "incident not found")
    return r


@app.get("/api/incidents/{iid}/clock")
def clock_ep(iid: str):
    from . import clock
    inc = services.get_incident(iid)
    if not inc:
        raise HTTPException(404, "incident not found")
    return {"timers": clock.timers(inc)}


@app.get("/api/clock")
def clock_all():
    from . import clock
    return {"timers": clock.all_active()}


@app.get("/api/incidents/{iid}/fhir")
def fhir_bundle(iid: str):
    inc, ents, vit = _bundle_parts(iid)
    __import__("app.field", fromlist=["log_access"]).log_access(iid, auth.CURRENT.get(), "exported FHIR")
    return JSONResponse(fhir.bundle(inc, ents, vit, audit.verify()["head"]), media_type="application/fhir+json")


@app.get("/api/incidents/{iid}/fhir-lite")
def fhir_lite(iid: str):
    inc, ents, _ = _bundle_parts(iid)
    return fhir.lite(inc, ents)


@app.get("/api/incidents/{iid}/pdf")
def handover_pdf(iid: str):
    inc, ents, vit = _bundle_parts(iid)
    __import__("app.field", fromlist=["log_access"]).log_access(iid, auth.CURRENT.get(), "downloaded PDF")
    data = pdf.render(inc, ents, vit, inc.get("alerts", []), audit.verify())
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="FieldScribe_{inc["dispatch_id"]}.pdf"'})


@app.post("/api/incidents/{iid}/hub-edit")
def hub_edit(iid: str):
    try:
        return services.simulate_hub_edit(iid)
    except KeyError:
        raise HTTPException(404, "incident not found")


# ------------------------------------------------------------------ ledger

@app.get("/api/ledger")
def ledger(incident_id: str | None = None, limit: int = 200):
    rows = db.q("SELECT seq,ts,incident_id,event_type,payload,payload_hash,prev_hash,hash,signature,signer,key_id FROM ledger "
                + ("WHERE incident_id=? " if incident_id else "") + "ORDER BY seq DESC LIMIT ?",
                (incident_id, limit) if incident_id else (limit,))
    for r in rows:
        r["payload"] = db.jload(r["payload"], {})
    return rows


@app.get("/api/ledger/verify")
def ledger_verify(incident_id: str | None = None):
    return audit.verify(incident_id)


@app.post("/api/ledger/tamper")
def ledger_tamper(seq: int | None = None):
    return {"tamper": audit.tamper(seq), "verify": audit.verify()}


@app.post("/api/ledger/restore")
def ledger_restore():
    return {"restore": audit.restore(), "verify": audit.verify()}


# ------------------------------------------------------------------ sync / analytics / eval / lexicon

@app.get("/api/sync")
def sync():
    return services.sync_state()


@app.post("/api/sync/run")
def sync_run():
    return services.run_sync()


@app.get("/api/analytics")
def analytics():
    return services.analytics()


@lru_cache(maxsize=1)
def _eval_cached():
    t0 = time.perf_counter()
    r = evaluation.run(30)
    r["stress"] = evaluation.stress()
    r["runtime_s"] = round(time.perf_counter() - t0, 2)
    return r


@app.get("/api/eval/codemix")
def eval_codemix():
    return {"development": evaluation.codemix(), "heldout": evaluation.codemix(heldout=True)}


@app.get("/api/eval")
def eval_run(refresh: bool = False):
    if refresh:
        _eval_cached.cache_clear()
    return _eval_cached()


@lru_cache(maxsize=1)
def _compare_cached():
    t0 = time.perf_counter()
    r = evaluation.compare(400)
    r["runtime_s"] = round(time.perf_counter() - t0, 2)
    return r


@app.get("/api/eval/compare")
def eval_compare(refresh: bool = False):
    if refresh:
        _compare_cached.cache_clear()
    return _compare_cached()


@app.get("/api/ner/status")
def ner_status():
    from .nlp import transformer_ner
    return transformer_ner.status()


@app.get("/api/eval/dataset")
def eval_dataset(limit: int = 60):
    return evaluation.build(30)[:limit]


@app.get("/api/lexicon")
def lexicon():
    return {
        "drugs": [{"name": k, **{kk: vv for kk, vv in v.items()}} for k, v in L.DRUGS.items()],
        "procedures": [{"name": k, **v} for k, v in L.PROCEDURES.items()],
        "routes": L.ROUTES, "units": L.UNITS, "devices": L.DEVICES, "ambiguous": L.AMBIGUOUS, "code_mix": L.CODE_MIX,
    }


@app.get("/api/routes")
def routes():
    """Road route, distance, drive time and live position for every unit heading to a hospital."""
    from datetime import datetime, timezone
    from . import routing
    hosp = {h["name"]: h for h in services.HOSPITALS}
    online = services.is_online()
    out = []
    for inc in services.list_incidents():
        h = hosp.get(inc.get("destination") or "")
        if inc["status"] == "handed_over" or not h or inc.get("lat") is None:
            continue
        r = routing.route((inc["lat"], inc["lng"]), (h["lat"], h["lng"]), online)
        eta_s = r["duration_s"]
        pos, remaining, progress = [inc["lat"], inc["lng"]], eta_s, 0.0
        if inc["status"] == "transporting":
            started = datetime.fromisoformat(inc["updated_at"])
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            progress = min(0.97, max(0.0, elapsed / eta_s)) if eta_s else 0.97
            pos = routing.along(r["coords"], progress)
            remaining = max(0, round(eta_s * (1 - progress)))
        out.append({"incident_id": inc["id"], "vehicle": inc["vehicle"], "status": inc["status"], "triage": inc.get("triage"),
                    "complaint": inc.get("complaint"), "destination": h["name"], "source": r["source"], "cached": r.get("cached"),
                    "coords": r["coords"], "distance_m": r["distance_m"], "duration_s": eta_s, "remaining_s": remaining,
                    "progress": round(progress, 3), "position": pos, "scene": [inc["lat"], inc["lng"]]})
    return {"online": online, "routes": out}


@app.get("/api/map/status")
def map_status():
    from . import routing
    return routing.map_status()


@app.get("/api/map/data")
def map_data():
    from . import routing
    if not routing.MAP_FILE.exists():
        raise HTTPException(404, "Offline map not downloaded. Run: python fetch_map.py")
    return FileResponse(routing.MAP_FILE, media_type="application/json", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/reference")
def reference():
    return {"hospitals": services.HOSPITALS, "crew": services.CREW}


@app.post("/api/admin/reseed")
def reseed():
    from .seed import seed
    seed(reset=True)
    _eval_cached.cache_clear()
    _compare_cached.cache_clear()
    return {"ok": True}


# ------------------------------------------------------------------ Copilot agent

class ChatIn(BaseModel):
    messages: list[dict] = Field(..., min_length=1)
    incident_id: str | None = None
    signer: str | None = None
    prefer: str | None = None


class ConfirmIn(BaseModel):
    pending: dict
    signer: str | None = None


@app.get("/api/agent/status")
def agent_status():
    return copilot.status()


@app.post("/api/agent/chat")
def agent_chat(body: ChatIn):
    msgs = [{"role": m.get("role", "user"), "content": str(m.get("content", ""))[:4000]} for m in body.messages if m.get("content")]
    if not msgs or msgs[-1]["role"] != "user":
        raise HTTPException(400, "last message must be from the user")
    u = auth.current()
    return copilot.chat(msgs, body.incident_id, u["name"] if auth.enabled() else body.signer, body.prefer, can_write=auth.can("copilot"))


@app.post("/api/agent/confirm")
def agent_confirm(body: ConfirmIn):
    if not body.pending.get("id"):
        raise HTTPException(400, "invalid pending item")
    return copilot.confirm_pending(body.pending, auth.current()["name"] if auth.enabled() else body.signer)


@app.get("/api/agent/protocols")
def agent_protocols():
    return protocol_cards.PROTOCOLS


# ------------------------------------------------------------------ static SPA

DIST = Path(os.environ.get("FIELDSCRIBE_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))

_PHONE_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#000"><title>Set up this phone · FieldScribe</title>
<style>
:root{color-scheme:dark}body{margin:0;background:#000;color:#e8eef2;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:560px;margin:0 auto;padding:28px 20px 48px}h1{font-size:28px;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:#8a979f;margin:0 0 24px}ol{list-style:none;padding:0;margin:0;counter-reset:s}
li{counter-increment:s;border:1px solid #232c33;border-radius:12px;padding:16px 16px 16px 56px;margin:0 0 12px;position:relative;background:#0a0e11}
li:before{content:counter(s);position:absolute;left:16px;top:14px;width:28px;height:28px;border-radius:50%;background:#182027;color:#3ee07f;
display:flex;align-items:center;justify-content:center;font-weight:700}
h2{font-size:18px;margin:0 0 6px}p{margin:6px 0;color:#b9c4cb}.btn{display:inline-block;margin-top:10px;padding:12px 18px;border-radius:10px;
background:#3ee07f;color:#000;font-weight:700;text-decoration:none}.btn.sec{background:#182027;color:#e8eef2;border:1px solid #2c363e}
code{font:13px ui-monospace,Consolas,monospace;background:#182027;padding:2px 6px;border-radius:6px;color:#e8eef2}
.os{display:none}.note{font-size:13px;color:#8a979f;margin-top:18px}.fp{font:12px ui-monospace,Consolas,monospace;color:#8a979f}
</style></head><body><main>
<h1>Set up this phone</h1><p class="sub">Two minutes, once per phone. Afterwards this phone can dictate, and FieldScribe sits on its home screen like an app. Records stay on the ambulance laptop.</p>
<ol>
<li><h2>Download the laptop's certificate</h2><p>It lets this phone recognise the ambulance laptop and open a secure connection to it.</p>
<a class="btn" href="/api/tls/ca.crt" download="FieldScribe-laptop.crt">Download certificate</a>
<p class="fp">Fingerprint starts with __FP__</p></li>
<li><h2>Trust it</h2>
<div class="os" data-os="android"><p><b>Android:</b> Settings → Security &amp; privacy → More security settings → Encryption &amp; credentials → <b>Install a certificate</b> → <b>CA certificate</b> → Install anyway → pick <code>FieldScribe-laptop.crt</code> from Downloads.</p><p>The menu names vary a little by phone. Search Settings for “certificate”.</p></div>
<div class="os" data-os="ios"><p><b>iPhone:</b> tap <b>Allow</b> when Safari asks. Then Settings → <b>Profile Downloaded</b> → Install. Then Settings → General → About → <b>Certificate Trust Settings</b> → switch on <b>FieldScribe device CA</b>.</p></div>
<div class="os" data-os="other"><p>Open the downloaded file and choose to trust it for websites. On Android and iPhone, the steps show automatically on this page.</p></div></li>
<li><h2>Open FieldScribe securely</h2><p>Sign in with your PIN. Then add it to the home screen: Chrome menu ⋮ → <b>Add to Home screen</b> (Android) or Share → <b>Add to Home Screen</b> (iPhone).</p>
__LINKS__</li>
</ol>
<p class="note">Use this only on the ambulance's own Wi-Fi or hotspot. The phone talks only to this laptop; nothing goes to the internet.</p>
</main><script>
var ua=navigator.userAgent,os=/android/i.test(ua)?'android':/iphone|ipad|ipod/i.test(ua)?'ios':'other';
document.querySelector('.os[data-os="'+os+'"]').style.display='block';
</script></body></html>"""


@app.get("/phone", include_in_schema=False)
def phone_setup(request: Request):
    from fastapi.responses import HTMLResponse
    from . import tls
    host = (request.url.hostname or "").strip("[]")
    ips = tls.lan_ips()
    if host and host not in ("localhost", "127.0.0.1") and host not in ips:
        ips = [host] + ips
    links = "".join(f'<a class="btn{" sec" if i else ""}" href="https://{ip}:{tls.HTTPS_PORT}/">Open FieldScribe{"" if not i else " via " + ip}</a> '
                    for i, ip in enumerate(ips or ["127.0.0.1"]))
    html = _PHONE_HTML.replace("__LINKS__", links).replace("__FP__", tls.fingerprint())
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/tls/ca.crt", include_in_schema=False)
def tls_ca():
    from . import tls
    return Response(tls.ca_der(), media_type="application/x-x509-ca-cert",
                    headers={"Content-Disposition": 'attachment; filename="FieldScribe-laptop.crt"', "Cache-Control": "no-store"})


@app.get("/api/tls/status")
def tls_status(request: Request):
    from . import tls
    info = tls.ensure() if os.environ.get("FIELDSCRIBE_HTTPS_ON") == "1" else {"ips": tls.lan_ips(), "https_urls": [], "fingerprint": tls.fingerprint()}
    ip = info["ips"][0] if info["ips"] else None
    setup = f"http://{ip}:{os.environ.get('PORT', '8000')}/phone" if ip else None
    return {"tablet_mode": os.environ.get("FIELDSCRIBE_HTTPS_ON") == "1", "https_urls": info["https_urls"], "ips": info["ips"],
            "setup_url": setup, "qr_svg": tls.qr_svg(setup) if setup and os.environ.get("FIELDSCRIBE_HTTPS_ON") == "1" else None,
            "fingerprint": info["fingerprint"]}


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST.resolve() in f.parents:
            if f.name == "sw.js":   # the service worker must always be re-checked so updates arrive
                return FileResponse(f, media_type="application/javascript", headers={"Cache-Control": "no-cache"})
            if f.suffix == ".webmanifest":
                return FileResponse(f, media_type="application/manifest+json")
            return FileResponse(f)
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
