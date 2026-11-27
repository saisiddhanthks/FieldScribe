"""
FieldScribe Copilot: a tool-calling agent with a provider fallback chain.

    gemini  -> Google Gemini API (free tier, function calling)
    groq    -> Groq OpenAI-compatible API (free tier, Llama / gpt-oss)
    openai  -> OpenAI API (paid, optional)
    ollama  -> local model via Ollama's OpenAI-compatible endpoint (fully offline)
    offline -> deterministic protocol engine (no model at all; always available)

Keys are read from environment variables (loaded from backend/.env). They are
never returned by any endpoint.
"""
from __future__ import annotations

import json
import os
import re
import time

import httpx

from .. import services
from ..nlp.ner import extract
from . import protocols as P
from . import tools as T

SYSTEM = """You are FieldScribe Copilot, decision support for Indian 108 ambulance crews (EMTs) on scene and en route.
You can call tools that read the live patient record and log care into a signed, audit-chained record.

How to respond:
- Be brief and practical. The EMT is busy with a patient. Lead with immediate life threats. Use short numbered steps.
- When the EMT describes an incident or symptoms, ALWAYS call find_protocols first and base guidance on the returned cards.
- Medications: only mention drugs listed in a returned protocol card, phrased as "per your 108 protocol / medical direction".
  Never invent a dose. Call check_medication before recommending a specific dose for this patient.
- If there are red flags (no breathing, no pulse, airway compromise, shock, GCS falling), say so first and advise ALS backup.
- Logging: when the EMT says something HAS BEEN DONE (given, administered, applied, started, done, diya, lagaya) or reports vitals,
  call log_care with their words. Never log your own suggestions or anything not yet done.
- log_care signs safe items at once. If it returns needs_confirmation, say what was logged, then name the held item and its critical flag
  and ask the EMT to confirm. Only after an explicit confirmation call confirm_flagged_care with the pending_id. The EMT may also press
  the on-screen confirm button instead.
- Never claim something was logged unless log_care returned logged=true. Mention the block number when it was logged.
- If no incident is selected and the EMT reports a new call, call open_incident.
- Reply in the EMT's language mix (English, Hinglish, Kannada words are fine). No markdown tables; plain text with numbered lines.
- You support but never replace the crew's clinical judgement or local protocol."""


def _env(k: str, d: str | None = None) -> str | None:
    v = os.environ.get(k)
    if v is not None:
        v = v.strip().strip('"').strip("'").strip()
    return v if v not in (None, "") else d


def provider_config() -> list[dict]:
    order = [p.strip() for p in (_env("FIELDSCRIBE_AGENT_ORDER", "gemini,groq,openai,ollama,offline") or "").split(",") if p.strip()]
    cfg = {
        "gemini": {"kind": "gemini", "label": "Google Gemini", "key": _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY"),
                   "model": _env("GEMINI_MODEL", "gemini-3.8-flash"), "fallback_model": _env("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite"),
                   "cloud": True},
        "groq": {"kind": "openai", "label": "Groq", "key": _env("GROQ_API_KEY"), "base": "https://api.groq.com/openai/v1",
                 "model": _env("GROQ_MODEL", "llama-3.3-70b-versatile"), "cloud": True},
        "openai": {"kind": "openai", "label": "OpenAI", "key": _env("OPENAI_API_KEY"), "base": _env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                   "model": _env("OPENAI_MODEL", "gpt-4o-mini"), "cloud": True},
        "ollama": {"kind": "ollama", "label": "Local AI (Ollama)", "key": "ollama", "base": _env("OLLAMA_URL", "http://127.0.0.1:11434/v1"),
                   "model": _env("OLLAMA_MODEL", "qwen2.5"), "cloud": False, "probe": True},
        "offline": {"kind": "offline", "label": "Offline protocol engine", "key": "-", "model": "rules", "cloud": False},
    }
    from .. import localai
    if localai.prefer_offline() and "ollama" in order:     # Settings: "use the local AI even when online"
        order = ["ollama"] + [o for o in order if o != "ollama"]
    out = []
    for name in order:
        c = cfg.get(name)
        if not c:
            continue
        c = dict(c, name=name)
        c["configured"] = bool(c["key"])
        if name == "ollama":
            m = localai.chosen_model() if localai.running() else None
            c["configured"], c["model"] = bool(m), (m or c["model"])
        out.append(c)
    if not any(c["name"] == "offline" for c in out):
        out.append(dict(cfg["offline"], name="offline", configured=True))
    return out


def status() -> dict:
    provs = []
    for c in provider_config():
        item = {"name": c["name"], "label": c["label"], "model": c["model"], "configured": c["configured"], "cloud": c["cloud"]}
        provs.append(item)
    active = next((p for p in provs if p["configured"]), None)
    return {"providers": provs, "active": active, "online": services.is_online()}


_ollama_cache: dict = {}


def _ollama_up(base: str) -> bool:
    now = time.time()
    if base in _ollama_cache and now - _ollama_cache[base][1] < 20:
        return _ollama_cache[base][0]
    try:
        ok = httpx.get(base.replace("/v1", "") + "/api/tags", timeout=1.2).status_code == 200
    except Exception:
        ok = False
    _ollama_cache[base] = (ok, now)
    return ok


# ----------------------------------------------------------------------------- public entry

def chat(messages: list[dict], incident_id: str | None = None, signer: str | None = None, prefer: str | None = None,
         can_write: bool = True) -> dict:
    """messages: [{role: 'user'|'assistant', content: str}] (latest last)."""
    t0 = time.perf_counter()
    errors = []
    chain = provider_config()
    if prefer:
        chain = sorted(chain, key=lambda c: c["name"] != prefer)
    online = services.is_online()
    for c in chain:
        if not c["configured"]:
            continue
        if c["cloud"] and not online:
            errors.append({"provider": c["name"], "error": "device offline"})
            continue
        ctx = {"cloud": c["cloud"], "incident_id": incident_id, "signer": signer, "provider": c["name"], "trace": [], "can_write": can_write}
        try:
            if c["kind"] == "gemini":
                reply = _run_gemini(c, messages, ctx)
            elif c["kind"] == "openai":
                reply = _run_openai(c, messages, ctx)
            elif c["kind"] == "ollama":
                reply = _run_ollama(c, messages, ctx)
            else:
                reply = _run_offline(messages, ctx)
            return _pack(reply, c, ctx, errors, t0)
        except Exception as e:
            errors.append({"provider": c["name"], "error": _clean_err(e)})
            if ctx.get("logged"):
                # a write already happened: do not re-run the turn on another provider (avoid double logging)
                return _pack("Care was logged (see below) but the assistant stopped early: " + _clean_err(e), c, ctx, errors, t0)
            continue
    ctx = {"cloud": False, "incident_id": incident_id, "signer": signer, "provider": "offline", "trace": [], "can_write": can_write}
    return _pack(_run_offline(messages, ctx), dict(provider_config()[-1]), ctx, errors, t0)


def confirm_pending(pending: dict, signer: str | None) -> dict:
    ctx = {"cloud": False, "incident_id": pending.get("incident_id"), "signer": signer, "provider": "confirm", "trace": []}
    res = T.run("confirm_flagged_care", {"pending_id": pending.get("id", "")}, ctx)
    msg = (f"Confirmed by EMT and logged in block #{res['block']}: " + ", ".join(e["name"] for e in res["entries"]) + ".") if res.get("logged") \
        else f"Not logged: {res.get('reason') or res.get('error')}"
    return {"reply": msg, "provider": {"name": "confirm", "label": "EMT confirmation", "model": "-", "cloud": False},
            "tool_calls": ctx["trace"], "logged": ctx.get("logged", []), "pending": None, "protocols": [], "incident_id": pending.get("incident_id"),
            "fallbacks": [], "latency_ms": 0}


def _pack(reply, c, ctx, errors, t0):
    return {"reply": reply, "provider": {"name": c["name"], "label": c["label"], "model": c["model"], "cloud": c["cloud"]},
            "tool_calls": ctx.get("trace", []), "logged": ctx.get("logged", []), "pending": ctx.get("pending"),
            "protocols": [{k: p[k] for k in ("id", "title", "priority", "steps", "red_flags", "do_not", "meds", "log_hints")} for p in ctx.get("protocols", [])],
            "incident_id": ctx.get("incident_id"), "opened": ctx.get("opened"),
            "fallbacks": errors, "latency_ms": round((time.perf_counter() - t0) * 1000)}


def _clean_err(e: Exception) -> str:
    s = str(e)
    s = re.sub(r"(key=|Bearer\s+)[A-Za-z0-9_\-\.]+", r"\1***", s)
    return s[:300]


def _context_note(ctx) -> str:
    if ctx.get("incident_id"):
        inc = services.get_incident(ctx["incident_id"])
        if inc:
            return f"[Selected incident: {inc['id']} · {inc.get('complaint') or 'assessment pending'} · status {inc['status']}]"
    return "[No incident selected]"


MAX_STEPS = 8


# ----------------------------------------------------------------------------- Gemini

def _gem_schema(s, upper=False):
    if isinstance(s, dict):
        out = {}
        for k, v in s.items():
            if k == "type" and isinstance(v, str):
                out[k] = v.upper() if upper else v
            else:
                out[k] = _gem_schema(v, upper)
        return out
    if isinstance(s, list):
        return [_gem_schema(x, upper) for x in s]
    return s


def _run_gemini(c, messages, ctx):
    contents = []
    for m in messages[-16:]:
        contents.append({"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]})
    contents[-1]["parts"][0]["text"] = _context_note(ctx) + "\n" + contents[-1]["parts"][0]["text"]
    model = c["model"]
    upper = False
    tried_fallback = False
    with httpx.Client(timeout=httpx.Timeout(28, connect=8)) as h:
        for step in range(MAX_STEPS):
            body = {"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents,
                    "tools": [{"functionDeclarations": [{"name": s["name"], "description": s["description"],
                                                         **({"parameters": _gem_schema(s["parameters"], upper)} if s["parameters"].get("properties") else {})}
                                                        for s in T.SPECS]}],
                    "generationConfig": {"temperature": 0.2}}
            if model.startswith("gemini-3"):
                # fast replies at the roadside: keep the model's internal reasoning short
                body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
            try:
                r = h.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                           headers={"x-goog-api-key": c["key"], "Content-Type": "application/json"}, json=body)
            except httpx.TimeoutException:
                if not tried_fallback and c.get("fallback_model") and model != c["fallback_model"]:
                    model, tried_fallback = c["fallback_model"], True
                    continue
                raise RuntimeError(f"Gemini timed out ({model})")
            if r.status_code == 400 and "thinking" in r.text.lower() and "thinkingConfig" in body["generationConfig"]:
                model = c.get("fallback_model") or model
                tried_fallback = True
                continue
            if r.status_code in (404, 429, 500, 503) and not tried_fallback and c.get("fallback_model") and model != c["fallback_model"]:
                model, tried_fallback = c["fallback_model"], True
                continue
            if r.status_code == 400 and not upper and "type" in r.text.lower():
                upper = True
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
            cand = (data.get("candidates") or [{}])[0]
            content = cand.get("content") or {}
            parts = content.get("parts") or []
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not calls:
                text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                if not text:
                    raise RuntimeError(f"Gemini returned no text (finishReason={cand.get('finishReason')})")
                c["model"] = model
                return text
            contents.append({"role": "model", "parts": parts})  # keep thought signatures intact
            responses = []
            for call in calls:
                res = T.run(call["name"], call.get("args") or {}, ctx)
                responses.append({"functionResponse": {"name": call["name"], "response": {"result": res}}})
            contents.append({"role": "user", "parts": responses})
    return "I ran out of steps working on that. Here is what I did so far: " + "; ".join(t["summary"] for t in ctx["trace"])


# ----------------------------------------------------------------------------- OpenAI-compatible (Groq / OpenAI / Ollama)

def _run_openai(c, messages, ctx):
    msgs = [{"role": "system", "content": SYSTEM}]
    for m in messages[-16:]:
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs[-1]["content"] = _context_note(ctx) + "\n" + msgs[-1]["content"]
    tools = [{"type": "function", "function": {"name": s["name"], "description": s["description"], "parameters": s["parameters"]}} for s in T.SPECS]
    with httpx.Client(timeout=60 if not c["cloud"] else 45) as h:
        for step in range(MAX_STEPS):
            r = h.post(c["base"].rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {c['key']}"},
                       json={"model": c["model"], "messages": msgs, "tools": tools, "tool_choice": "auto", "temperature": 0.2})
            if r.status_code >= 400:
                raise RuntimeError(f"{c['label']} HTTP {r.status_code}: {r.text[:200]}")
            msg = r.json()["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            if not calls:
                text = (msg.get("content") or "").strip()
                if not text:
                    raise RuntimeError(f"{c['label']} returned an empty reply")
                return text
            msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for call in calls:
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                res = T.run(call["function"]["name"], args, ctx)
                msgs.append({"role": "tool", "tool_call_id": call.get("id", call["function"]["name"]), "content": json.dumps(res, default=str)})
    return "I ran out of steps working on that. Done so far: " + "; ".join(t["summary"] for t in ctx["trace"])


# ----------------------------------------------------------------------------- Ollama native (local, no internet)

def _run_ollama(c, messages, ctx):
    """Ollama's own /api/chat: lets us set the context window (the default 2-4k tokens would silently cut the
    protocol tools and system prompt) and keep the model loaded between turns."""
    from .. import localai
    msgs = [{"role": "system", "content": SYSTEM}]
    for m in messages[-12:]:
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs[-1]["content"] = _context_note(ctx) + "\n" + msgs[-1]["content"]
    tools = [{"type": "function", "function": {"name": s["name"], "description": s["description"], "parameters": s["parameters"]}} for s in T.SPECS]
    opts = {"temperature": 0.2, "num_ctx": int(_env("OLLAMA_NUM_CTX", "8192"))}
    with httpx.Client(timeout=httpx.Timeout(10, read=float(_env("OLLAMA_TIMEOUT", "240")))) as h:
        for step in range(MAX_STEPS):
            r = h.post(localai.api() + "/api/chat", json={"model": c["model"], "messages": msgs, "tools": tools, "stream": False,
                                                        "keep_alive": "30m", "options": opts})
            if r.status_code >= 400:
                raise RuntimeError(f"Local AI HTTP {r.status_code}: {r.text[:200]}")
            msg = r.json().get("message") or {}
            calls = msg.get("tool_calls") or []
            if not calls:
                text = (msg.get("content") or "").strip()
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
                if not text:
                    raise RuntimeError("Local AI returned an empty reply")
                return text
            msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for call in calls:
                fn = call.get("function") or {}
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                res = T.run(fn.get("name", ""), args, ctx)
                msgs.append({"role": "tool", "tool_name": fn.get("name", ""), "content": json.dumps(res, default=str)})
    return "I ran out of steps working on that. Done so far: " + "; ".join(t["summary"] for t in ctx["trace"])


# ----------------------------------------------------------------------------- offline engine

_DONE_RX = re.compile(r"\b(gave|given|give[n]? him|administered|applied|started|inserted|put on|done|did|diya|de diya|lagaya|lagayi|chadhaya|"
                      r"kiya|kodu|placed|secured|bp|pulse|spo2|sats?|grbs|gcs|rr)\b")
_Q_RX = re.compile(r"\b(what|which|how much|has|have|did we|received|summary|summarise|summarize|status)\b")


def _run_offline(messages, ctx):
    text = messages[-1]["content"].strip()
    t = text.lower()
    iid = ctx.get("incident_id")
    out = []
    if re.search(r"\b(verify|audit|tamper|ledger|chain)\b", t):
        v = T.run("verify_audit_chain", {}, ctx)
        return f"Audit chain {'verified' if v['valid'] else 'BROKEN at block #' + str(v['first_bad_seq'])} · {v['blocks']} blocks checked ({v['algorithm']})."
    if re.search(r"\b(handover|atmist|hand over|summary for ed)\b", t) and iid:
        return "Handover (ATMIST):\n" + T.run("draft_handover", {"incident_id": iid}, ctx)["handover"]
    ex = extract(text)
    did_something = _DONE_RX.search(t) and (ex["entities"] or ex["vitals"])
    cards = P.match(text)
    if not iid and (cards or did_something):
        opened = T.run("open_incident", {"complaint": cards[0]["title"] if cards else "Reported via Copilot",
                                          "triage": cards[0]["priority"] if cards else None}, ctx)
        iid = ctx["incident_id"]
        out.append(f"Opened incident {opened['dispatch_id']}.")
    if did_something and iid:
        res = T.run("log_care", {"incident_id": iid, "statement": text}, ctx)
        if res.get("logged"):
            items = [f"{e['name']}" + (f" {e['dose']:g} {e.get('unit', '')}" if isinstance(e.get('dose'), (int, float)) else (f" {e['rate']}" if e.get('rate') else ""))
                     + (" (withheld)" if e["status"] == "withheld" else "") for e in res["entries"]]
            items += [f"{v['name'].upper()} {v['value']}" for v in res["vitals"]]
            out.append(f"Logged in block #{res['block']}: " + ", ".join(items) + ".")
            for w in res.get("warnings", [])[:3]:
                out.append(f"Check: {w}")
        if res.get("needs_confirmation"):
            out.append(f"Held, not logged: {', '.join(res['held_items'])} - critical flag:\n" + "\n".join(f"- {m}" for m in res["critical_flags"]) +
                       "\nConfirm you have checked this and I will log it.")
        if not res.get("logged") and not res.get("needs_confirmation"):
            out.append(res.get("reason", "Nothing logged."))
    if cards:
        T.run("find_protocols", {"description": text}, ctx)
        top = cards[0]
        lines = [f"{top['title']} - priority {top['priority']}:"]
        lines += [f"{i}. {s}" for i, s in enumerate(top["steps"], 1)]
        if top["do_not"]:
            lines.append("Do not: " + "; ".join(top["do_not"]) + ".")
        if top["red_flags"]:
            lines.append("Red flags: " + "; ".join(top["red_flags"]) + ".")
        if top["meds"]:
            lines.append("Per your 108 protocol / medical direction: " + "; ".join(f"{m['drug']} {m['dose']} ({m['note']})" for m in top["meds"]) + ".")
        lines.append("Tell me what you have done and I will log it.")
        out.append("\n".join(lines))
    elif iid and _Q_RX.search(t) and not did_something:
        inc = T.run("get_incident", {"incident_id": iid}, ctx)
        care = inc.get("care_logged", [])
        if care:
            out.append("So far: " + "; ".join(f"{c['name']}" + (f" {float(c['dose']):g} {c.get('unit', '')}" if c.get("dose") is not None else (f" {c['rate']}" if c.get("rate") else "")) +
                                              (f" {c['route']}" if c.get("route") else "") + (f" at {c['time']}" if c.get("time") else "") +
                                              (" (withheld)" if c["status"] == "withheld" else "") for c in care) + ".")
        else:
            out.append("Nothing logged yet for this incident.")
        if inc["patient"].get("allergies"):
            out.append("Allergy: " + ", ".join(inc["patient"]["allergies"]) + ".")
        if inc.get("flags"):
            out.append("Flags: " + ", ".join(f.split(":")[1].replace("_", " ").lower() for f in inc["flags"]) + ".")
    if not out:
        out.append("Describe the patient (what happened, symptoms, vitals) for first-aid steps, or tell me what you have given and I will log it. "
                   "You can also ask for a handover summary or an audit check.")
    return "\n\n".join(out)
