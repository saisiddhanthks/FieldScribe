"""
Device database: SQLite in WAL mode, encrypted at rest with SQLCipher when available.

Encryption: if the `sqlcipher3` package is installed (pip install sqlcipher3-wheels), the
database file is AES-256 encrypted. The key comes from FIELDSCRIBE_DB_KEY (backend/.env);
one is generated on first start. An existing plain database is converted automatically.
Set FIELDSCRIBE_ENCRYPT=0 to force plain SQLite (e.g. for debugging).
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

try:
    import sqlcipher3 as _sqlcipher
except Exception:  # pragma: no cover
    _sqlcipher = None

DATA_DIR = Path(os.environ.get("FIELDSCRIBE_DATA", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("FIELDSCRIBE_DB", DATA_DIR / "fieldscribe.db"))
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
  id TEXT PRIMARY KEY,
  dispatch_id TEXT, vehicle TEXT, crew TEXT, status TEXT,
  complaint TEXT, triage TEXT, patient TEXT, workflow TEXT,
  lat REAL, lng REAL, place TEXT, destination TEXT, eta_min INTEGER,
  created_at TEXT, updated_at TEXT, version INTEGER DEFAULT 1,
  handover_by TEXT, handover_at TEXT
);
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY, incident_id TEXT, source TEXT, asr_text TEXT, final_text TEXT,
  extraction TEXT, capture_ms INTEGER, asr_meta TEXT, signer TEXT, created_at TEXT, ledger_seq INTEGER
);
CREATE TABLE IF NOT EXISTS entries (
  id TEXT PRIMARY KEY, incident_id TEXT, record_id TEXT, kind TEXT, name TEXT,
  payload TEXT, original TEXT, status TEXT, confidence REAL, edited INTEGER,
  flags TEXT, time TEXT, signer TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS vitals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT, record_id TEXT,
  name TEXT, value TEXT, unit TEXT, time TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
  seq INTEGER PRIMARY KEY, ts TEXT, incident_id TEXT, event_type TEXT,
  payload TEXT, payload_hash TEXT, prev_hash TEXT, hash TEXT,
  signature TEXT, signer TEXT, key_id TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, ref_id TEXT, incident_id TEXT,
  payload TEXT, status TEXT, attempts INTEGER DEFAULT 0, created_at TEXT,
  synced_at TEXT, bytes INTEGER, note TEXT
);
CREATE TABLE IF NOT EXISTS hub (
  incident_id TEXT PRIMARY KEY, version INTEGER, payload TEXT, received_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS route_cache (key TEXT PRIMARY KEY, payload TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, name TEXT, role TEXT, pin_hash TEXT, active INTEGER DEFAULT 1,
  failed INTEGER DEFAULT 0, locked_until REAL DEFAULT 0, created_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY, user_id TEXT, created_at REAL, last_seen REAL
);
CREATE TABLE IF NOT EXISTS access_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT, user_id TEXT, user_name TEXT, role TEXT, action TEXT, at TEXT
);
CREATE INDEX IF NOT EXISTS ix_access_inc ON access_log(incident_id);
CREATE TABLE IF NOT EXISTS mci_events (
  id TEXT PRIMARY KEY, name TEXT, place TEXT, lat REAL, lng REAL, started_at TEXT, started_by TEXT, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS tamper_backup (seq INTEGER PRIMARY KEY, payload TEXT);
CREATE INDEX IF NOT EXISTS ix_entries_inc ON entries(incident_id);
CREATE INDEX IF NOT EXISTS ix_vitals_inc ON vitals(incident_id);
CREATE INDEX IF NOT EXISTS ix_ledger_inc ON ledger(incident_id);
"""


MIGRATIONS = [
    ("incidents", "legal", "TEXT"), ("incidents", "mci_id", "TEXT"), ("incidents", "mci_tag", "TEXT"),
    ("users", "pin_default", "INTEGER DEFAULT 1"), ("users", "pin_changed_at", "TEXT"),
    ("entries", "amends", "TEXT"), ("entries", "superseded_by", "TEXT"), ("entries", "change_reason", "TEXT"),
    ("entries", "changed_by", "TEXT"), ("entries", "changed_at", "TEXT"),
]


def encryption_wanted() -> bool:
    return _sqlcipher is not None and os.environ.get("FIELDSCRIBE_ENCRYPT", "1") != "0"


def _db_key() -> str:
    k = os.environ.get("FIELDSCRIBE_DB_KEY")
    if k:
        return k
    k = secrets.token_hex(32)
    os.environ["FIELDSCRIBE_DB_KEY"] = k
    try:
        from .config import ENV_FILE
        import datetime
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ENV_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n# Device database encryption key (generated {datetime.date.today()}). Keep it secret: without it the data cannot be read.\n"
                    f"FIELDSCRIBE_DB_KEY={k}\n")
    except Exception:
        pass
    return k


def _is_plain(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except FileNotFoundError:
        return False


def _encrypt_existing(path: Path, key: str) -> None:
    """Convert a plain SQLite file into an SQLCipher-encrypted one in place."""
    tmp = path.with_suffix(".enc.tmp")
    if tmp.exists():
        tmp.unlink()
    plain = _sqlcipher.connect(str(path))
    plain.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    plain.execute(f"ATTACH DATABASE '{tmp.as_posix()}' AS enc KEY \"x'{key}'\"")
    plain.execute("SELECT sqlcipher_export('enc')")
    plain.execute("DETACH DATABASE enc")
    plain.close()
    for suffix in ("-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()
    os.replace(tmp, path)


def connect():
    global ENCRYPTED
    if encryption_wanted():
        key = _db_key()
        if _is_plain(DB_PATH):
            _encrypt_existing(DB_PATH, key)
        con = _sqlcipher.connect(str(DB_PATH), check_same_thread=False, isolation_level=None)
        con.execute(f"PRAGMA key = \"x'{key}'\"")
        con.row_factory = _sqlcipher.Row
        ENCRYPTED = True
    else:
        con = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
        con.row_factory = sqlite3.Row
        ENCRYPTED = False
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


ENCRYPTED = False
_con = None


def get():
    global _con
    if _con is None:
        _con = connect()
        _con.executescript(SCHEMA)
        for table, col, typ in MIGRATIONS:
            cols = {r[1] for r in _con.execute(f"PRAGMA table_info({table})").fetchall()}
            if col not in cols:
                _con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    return _con


def info() -> dict:
    get()
    return {"engine": "SQLCipher (AES-256)" if ENCRYPTED else "SQLite (not encrypted)", "encrypted": ENCRYPTED,
            "file": DB_PATH.name, "sqlcipher_installed": _sqlcipher is not None,
            "size_kb": round(DB_PATH.stat().st_size / 1024) if DB_PATH.exists() else 0}


@contextmanager
def tx():
    con = get()
    with _lock:
        con.execute("BEGIN IMMEDIATE")
        try:
            yield con
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise


def q(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in get().execute(sql, args).fetchall()]


def q1(sql: str, args: tuple = ()) -> dict | None:
    rows = q(sql, args)
    return rows[0] if rows else None


def setting(key: str, default: str | None = None) -> str | None:
    r = q1("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default


def set_setting(key: str, value: str) -> None:
    with tx() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def jload(s: str | None, default=None):
    if s is None:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def reset() -> None:
    """Drop everything (used by seed --reset and tests)."""
    global _con
    if _con is not None:
        _con.close()
        _con = None
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            p.unlink()
