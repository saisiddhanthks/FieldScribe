"""
Tamper-evident audit ledger.

Each event is appended as a block:
    payload_hash = SHA-256(canonical_json(payload))
    hash         = SHA-256(canonical_json({seq, ts, incident_id, event_type, payload_hash, prev_hash}))
    signature    = Ed25519_sign(device_key, hash)
Changing any historical payload breaks its payload_hash; changing any header
breaks the chain link of every later block; forging a block requires the
device's private key. `verify()` replays the whole chain.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

from . import db

GENESIS = "0" * 64
KEY_DIR = Path(os.environ.get("FIELDSCRIBE_KEYS", db.DATA_DIR / "keys"))


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _load_key() -> Ed25519PrivateKey:
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    p = KEY_DIR / "device_ed25519.pem"
    if p.exists():
        return serialization.load_pem_private_key(p.read_bytes(), password=None)
    k = Ed25519PrivateKey.generate()
    p.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass
    return k


_KEY: Ed25519PrivateKey | None = None


def key() -> Ed25519PrivateKey:
    global _KEY
    if _KEY is None:
        _KEY = _load_key()
    return _KEY


def public_key_b64() -> str:
    raw = key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def key_id() -> str:
    return sha256(base64.b64decode(public_key_b64()))[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def header(seq, ts, incident_id, event_type, payload_hash, prev_hash) -> dict:
    return {"seq": seq, "ts": ts, "incident_id": incident_id, "event_type": event_type,
            "payload_hash": payload_hash, "prev_hash": prev_hash}


def append(event_type: str, incident_id: str | None, payload: dict, signer: str, ts: str | None = None, con=None) -> dict:
    def _do(c):
        last = c.execute("SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
        seq = (last["seq"] + 1) if last else 1
        prev = last["hash"] if last else GENESIS
        t = ts or now_iso()
        ph = sha256(canonical(payload))
        h = sha256(canonical(header(seq, t, incident_id, event_type, ph, prev)))
        sig = base64.b64encode(key().sign(bytes.fromhex(h))).decode()
        c.execute("INSERT INTO ledger(seq,ts,incident_id,event_type,payload,payload_hash,prev_hash,hash,signature,signer,key_id)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (seq, t, incident_id, event_type, canonical(payload).decode(), ph, prev, h, sig, signer, key_id()))
        return {"seq": seq, "hash": h, "prev_hash": prev, "ts": t, "signature": sig}
    if con is not None:
        return _do(con)
    with db.tx() as c:
        return _do(c)


def verify(incident_id: str | None = None) -> dict:
    rows = db.q("SELECT * FROM ledger ORDER BY seq")
    pub: Ed25519PublicKey = key().public_key()
    prev = GENESIS
    problems = []
    checked = 0
    for r in rows:
        checked += 1
        ph = sha256(r["payload"].encode())
        issues = []
        if ph != r["payload_hash"]:
            issues.append("payload modified (payload hash mismatch)")
        if r["prev_hash"] != prev:
            issues.append("chain link broken (prev_hash mismatch)")
        h = sha256(canonical(header(r["seq"], r["ts"], r["incident_id"], r["event_type"], r["payload_hash"], r["prev_hash"])))
        if h != r["hash"]:
            issues.append("block header modified (hash mismatch)")
        try:
            pub.verify(base64.b64decode(r["signature"]), bytes.fromhex(r["hash"]))
        except (InvalidSignature, ValueError):
            issues.append("signature invalid")
        if issues:
            problems.append({"seq": r["seq"], "event_type": r["event_type"], "incident_id": r["incident_id"], "issues": issues})
        prev = r["hash"]
    scoped = [p for p in problems if incident_id is None or p["incident_id"] == incident_id]
    return {
        "valid": not problems,
        "scope_valid": not scoped,
        "blocks": checked,
        "head": rows[-1]["hash"] if rows else GENESIS,
        "problems": problems,
        "first_bad_seq": problems[0]["seq"] if problems else None,
        "key_id": key_id(),
        "algorithm": "SHA-256 hash chain + Ed25519 signatures",
        "verified_at": now_iso(),
    }


def tamper(seq: int | None = None) -> dict:
    """Demo only: silently edit a historical payload the way an insider might."""
    with db.tx() as c:
        row = c.execute("SELECT * FROM ledger WHERE event_type='RECORD_SIGNED' ORDER BY seq " + ("" if seq else "DESC") + " LIMIT 1"
                        if seq is None else "SELECT * FROM ledger WHERE seq=?", () if seq is None else (seq,)).fetchone()
        if not row:
            return {"ok": False, "error": "no block to tamper"}
        c.execute("INSERT OR IGNORE INTO tamper_backup(seq,payload) VALUES(?,?)", (row["seq"], row["payload"]))
        payload = json.loads(row["payload"])
        changed = "payload"
        for item in payload.get("entries", []):
            f = item.get("fields") or item
            if isinstance(f, dict) and f.get("dose") not in (None, ""):
                f["dose"] = float(f["dose"]) * 10
                changed = f"{item.get('name', 'entry')} dose x10"
                break
        else:
            payload["tampered"] = True
        c.execute("UPDATE ledger SET payload=? WHERE seq=?", (canonical(payload).decode(), row["seq"]))
    return {"ok": True, "seq": row["seq"], "change": changed}


def restore() -> dict:
    with db.tx() as c:
        rows = c.execute("SELECT * FROM tamper_backup").fetchall()
        for r in rows:
            c.execute("UPDATE ledger SET payload=? WHERE seq=?", (r["payload"], r["seq"]))
        c.execute("DELETE FROM tamper_backup")
    return {"ok": True, "restored": len(rows)}
