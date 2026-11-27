"""
PIN login, roles and sessions.

Roles: emt (capture, sign, amend, Copilot), ed (read, acknowledge handover), admin (everything,
incl. tamper drill and demo reset). PINs are stored as scrypt hashes; 5 wrong PINs lock the
user for 60 s. Sessions expire after 30 min idle or 12 h total. The signer of every record,
amendment and handover is taken from the session, never from the request body.
Set FIELDSCRIBE_AUTH=0 to switch login off (development only).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timezone

from . import db

IDLE_S, MAX_S = 30 * 60, 12 * 3600
LOCK_AFTER, LOCK_S = 5, 60
DEMO_USERS = [
    ("emt07", "EMT-07 R. Kumar", "emt", "1080"), ("emt12", "EMT-12 S. Nair", "emt", "1080"),
    ("emt03", "EMT-03 A. Gowda", "emt", "1080"), ("emt21", "EMT-21 P. Reddy", "emt", "1080"),
    ("emt15", "EMT-15 M. Iyer", "emt", "1080"), ("emt09", "EMT-09 F. Khan", "emt", "1080"),
    ("edrao", "Dr. A. Rao (ED)", "ed", "2020"), ("edmenon", "Dr. K. Menon (ED)", "ed", "2020"),
    ("admin", "Supervisor (admin)", "admin", "9090"),
]
ROLE_RIGHTS = {
    "emt": {"read", "capture", "sign", "amend", "copilot", "copilot_read", "sync"},
    "ed": {"read", "handover", "copilot_read"},
    "admin": {"read", "capture", "sign", "amend", "copilot", "copilot_read", "handover", "sync", "admin"},
}


def enabled() -> bool:
    return os.environ.get("FIELDSCRIBE_AUTH", "1") != "0"


def _hash(pin: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pin.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return salt.hex() + "$" + h.hex()


def _check(pin: str, stored: str) -> bool:
    salt, h = stored.split("$")
    return hmac.compare_digest(_hash(pin, bytes.fromhex(salt)).split("$")[1], h)


def ensure_users() -> None:
    if db.q1("SELECT id FROM users LIMIT 1"):
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.tx() as c:
        for uid, name, role, pin in DEMO_USERS:
            c.execute("INSERT INTO users(id,name,role,pin_hash,created_at) VALUES(?,?,?,?,?)", (uid, name, role, _hash(pin), now))


def users() -> list[dict]:
    ensure_users()
    return db.q("SELECT id,name,role FROM users WHERE active=1 ORDER BY CASE role WHEN 'emt' THEN 0 WHEN 'ed' THEN 1 ELSE 2 END, name")


def demo_pins_in_use() -> bool:
    """True while any active account still has its factory demo PIN."""
    ensure_users()
    return bool(db.q1("SELECT id FROM users WHERE active=1 AND COALESCE(pin_default,1)=1 LIMIT 1"))


_PIN_RX = re.compile(r"^\d{4,8}$")
_WEAK = {"0000", "1111", "1234", "4321", "123456", "000000", "111111", "12345678"}


def _pin_problem(pin: str) -> str | None:
    if not _PIN_RX.match(pin or ""):
        return "PIN must be 4 to 8 digits"
    if pin in _WEAK or len(set(pin)) == 1:
        return "That PIN is too easy to guess"
    if pin in {"1080", "2020", "9090"}:
        return "Choose a PIN that isn't one of the demo PINs"
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def change_pin(uid: str, old: str, new: str) -> dict:
    u = db.q1("SELECT * FROM users WHERE id=? AND active=1", (uid,))
    if not u:
        return {"ok": False, "error": "Unknown user"}
    if not _check(old or "", u["pin_hash"]):
        return {"ok": False, "error": "Current PIN is wrong"}
    err = _pin_problem(new)
    if err:
        return {"ok": False, "error": err}
    with db.tx() as c:
        c.execute("UPDATE users SET pin_hash=?, pin_default=0, pin_changed_at=? WHERE id=?", (_hash(new), _now(), uid))
    return {"ok": True}


def admin_list() -> list[dict]:
    ensure_users()
    rows = db.q("SELECT id,name,role,active,COALESCE(pin_default,1) pin_default,pin_changed_at,created_at,locked_until FROM users "
                "ORDER BY active DESC, CASE role WHEN 'emt' THEN 0 WHEN 'ed' THEN 1 ELSE 2 END, name")
    now = time.time()
    for r in rows:
        r["active"] = bool(r["active"]); r["pin_default"] = bool(r["pin_default"])
        lu = r.pop("locked_until") or 0
        r["locked"] = lu > now
    last = {s["user_id"]: s["t"] for s in db.q("SELECT user_id, MAX(last_seen) t FROM sessions GROUP BY user_id")}
    for r in rows:
        r["last_seen"] = last.get(r["id"])
        r["online"] = bool(r["last_seen"] and now - r["last_seen"] < IDLE_S)
    return rows


_ID_RX = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,23}$")


def admin_create(uid: str, name: str, role: str, pin: str) -> dict:
    uid = (uid or "").strip().lower()
    if not _ID_RX.match(uid):
        return {"ok": False, "error": "User ID: 2 to 24 lowercase letters, digits, dot, dash or underscore"}
    if role not in ROLE_RIGHTS:
        return {"ok": False, "error": "Role must be emt, ed or admin"}
    if not (name or "").strip():
        return {"ok": False, "error": "Name is required"}
    err = _pin_problem(pin)
    if err:
        return {"ok": False, "error": err}
    if db.q1("SELECT id FROM users WHERE id=?", (uid,)):
        return {"ok": False, "error": "That user ID already exists"}
    with db.tx() as c:
        c.execute("INSERT INTO users(id,name,role,pin_hash,created_at,pin_default,pin_changed_at) VALUES(?,?,?,?,?,0,?)",
                  (uid, name.strip()[:60], role, _hash(pin), _now(), _now()))
    return {"ok": True}


def admin_update(uid: str, by: str, active: bool | None = None, pin: str | None = None, name: str | None = None, role: str | None = None) -> dict:
    u = db.q1("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        return {"ok": False, "error": "Unknown user"}
    if uid == by and (active is False or (role and role != "admin")):
        return {"ok": False, "error": "You can't disable or demote your own account"}
    if active is False and u["role"] == "admin" and db.q1("SELECT COUNT(*) n FROM users WHERE role='admin' AND active=1")["n"] <= 1:
        return {"ok": False, "error": "At least one active supervisor is required"}
    sets, args = [], []
    if pin is not None:
        err = _pin_problem(pin)
        if err:
            return {"ok": False, "error": err}
        sets += ["pin_hash=?", "pin_default=0", "pin_changed_at=?", "failed=0", "locked_until=0"]; args += [_hash(pin), _now()]
    if active is not None:
        sets.append("active=?"); args.append(1 if active else 0)
    if name:
        sets.append("name=?"); args.append(name.strip()[:60])
    if role:
        if role not in ROLE_RIGHTS:
            return {"ok": False, "error": "Role must be emt, ed or admin"}
        sets.append("role=?"); args.append(role)
    if not sets:
        return {"ok": True}
    with db.tx() as c:
        c.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", (*args, uid))
        if active is False or pin is not None or role:
            c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))   # force sign-in again
    return {"ok": True}


def login(uid: str, pin: str) -> dict:
    ensure_users()
    u = db.q1("SELECT * FROM users WHERE id=? AND active=1", (uid,))
    if not u:
        return {"ok": False, "error": "Unknown user"}
    now = time.time()
    if u["locked_until"] and u["locked_until"] > now:
        return {"ok": False, "error": f"Too many wrong PINs. Try again in {int(u['locked_until'] - now) + 1} s", "locked": True}
    if not _check(pin or "", u["pin_hash"]):
        failed = u["failed"] + 1
        lock = now + LOCK_S if failed >= LOCK_AFTER else 0
        with db.tx() as c:
            c.execute("UPDATE users SET failed=?, locked_until=? WHERE id=?", (0 if lock else failed, lock, uid))
        left = LOCK_AFTER - failed
        return {"ok": False, "error": "Wrong PIN" + (f" ({left} tries left)" if left > 0 else ". Locked for 60 s"), "locked": bool(lock)}
    token = secrets.token_urlsafe(32)
    with db.tx() as c:
        c.execute("UPDATE users SET failed=0, locked_until=0 WHERE id=?", (uid,))
        c.execute("DELETE FROM sessions WHERE last_seen < ?", (now - IDLE_S,))
        c.execute("INSERT INTO sessions(token,user_id,created_at,last_seen) VALUES(?,?,?,?)", (token, uid, now, now))
    return {"ok": True, "token": token, "user": public(u)}


def public(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "role": u["role"], "rights": sorted(ROLE_RIGHTS.get(u["role"], set()))}


def session(token: str | None) -> dict | None:
    if not token:
        return None
    s = db.q1("SELECT * FROM sessions WHERE token=?", (token,))
    now = time.time()
    if not s or now - s["last_seen"] > IDLE_S or now - s["created_at"] > MAX_S:
        return None
    if now - s["last_seen"] > 20:
        with db.tx() as c:
            c.execute("UPDATE sessions SET last_seen=? WHERE token=?", (now, token))
    u = db.q1("SELECT * FROM users WHERE id=? AND active=1", (s["user_id"],))
    return public(u) if u else None


def logout(token: str | None) -> None:
    if token:
        with db.tx() as c:
            c.execute("DELETE FROM sessions WHERE token=?", (token,))


DEV_USER = {"id": "dev", "name": "Developer (auth off)", "role": "admin", "rights": sorted(ROLE_RIGHTS["admin"])}


# --------------------------------------------------------------------------- request context

from contextvars import ContextVar

CURRENT: ContextVar[dict | None] = ContextVar("fs_user", default=None)

PUBLIC = {("GET", "/api/health"), ("GET", "/api/auth/me"), ("GET", "/api/auth/users"), ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("GET", "/api/tls/ca.crt")}
RULES = [
    ("POST", r"^/api/settings/online$", "sync"), ("POST", r"^/api/sync/run$", "sync"),
    ("POST", r"^/api/asr(/warmup)?$", "capture"),
    ("POST", r"^/api/incidents$", "capture"), ("PATCH", r"^/api/incidents/[^/]+$", "capture"),
    ("POST", r"^/api/incidents/[^/]+/records$", "sign"), ("POST", r"^/api/incidents/[^/]+/handover$", "handover"),
    ("POST", r"^/api/incidents/[^/]+/hub-edit$", "admin"), ("POST", r"^/api/ledger/(tamper|restore)$", "admin"),
    ("POST", r"^/api/admin/", "admin"), ("GET", r"^/api/admin/", "admin"), ("PATCH", r"^/api/admin/", "admin"), ("POST", r"^/api/entries/[^/]+/(amend|void)$", "amend"),
    ("POST", r"^/api/incidents/[^/]+/(patient|mlc|refusal)$", "capture"),
    ("POST", r"^/api/mci", "capture"),
    ("POST", r"^/api/localai/(pull|prefer|start)$", "admin"),
    ("POST", r"^/api/localai/test$", "copilot_read"),
    ("POST", r"^/api/agent/confirm$", "copilot"), ("POST", r"^/api/agent/chat$", "copilot_read"),
]


def required_right(method: str, path: str) -> str | None:
    if (method, path) in PUBLIC or not path.startswith("/api/"):
        return None
    for m, rx, right in RULES:
        if m == method and re.search(rx, path):
            return right
    return "read"


def current() -> dict:
    return CURRENT.get() or DEV_USER


def can(right: str) -> bool:
    return right in current()["rights"]
