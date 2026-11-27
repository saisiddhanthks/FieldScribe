"""
ED / state hub that ambulances sync to.

PostgreSQL when FIELDSCRIBE_HUB_URL is set (e.g. postgresql://fieldscribe:pass@localhost:5432/fieldscribe_hub)
and psycopg is installed; otherwise a simulated hub inside the device database so the demo
always works. Clinical items are append-only (idempotent per device + outbox id), so
re-sending after a dropped connection never duplicates anything.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from . import db

try:
    import psycopg
    from psycopg.types.json import Jsonb
except Exception:  # pragma: no cover
    psycopg = None

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS hub_incidents (
  incident_id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload JSONB, device TEXT, received_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS hub_items (
  id BIGSERIAL PRIMARY KEY, device TEXT NOT NULL, outbox_id BIGINT NOT NULL, kind TEXT, ref_id TEXT,
  incident_id TEXT, payload JSONB, received_at TIMESTAMPTZ DEFAULT now(), UNIQUE (device, outbox_id)
);
CREATE INDEX IF NOT EXISTS ix_hub_items_inc ON hub_items(incident_id);
"""


class HubError(Exception):
    pass


def url() -> str | None:
    return os.environ.get("FIELDSCRIBE_HUB_URL") or None


def masked(u: str | None) -> str | None:
    return re.sub(r"//([^:@/]+):[^@]*@", r"//\1:***@", u) if u else None


def engine() -> str:
    return "postgresql" if url() and psycopg else "simulated"


class _PG:
    def __init__(self):
        try:
            self.c = psycopg.connect(url(), connect_timeout=4, autocommit=False)
            with self.c.cursor() as cur:
                cur.execute(PG_SCHEMA)
            self.c.commit()
        except Exception as e:
            raise HubError(str(e).splitlines()[0][:200])

    def version(self, iid):
        with self.c.cursor() as cur:
            cur.execute("SELECT version FROM hub_incidents WHERE incident_id=%s", (iid,))
            r = cur.fetchone()
        return r[0] if r else None

    def receive(self, device, item, local_v):
        payload = json.loads(item["payload"] or "{}")
        with self.c.cursor() as cur:
            cur.execute("INSERT INTO hub_items(device,outbox_id,kind,ref_id,incident_id,payload) VALUES(%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (device,outbox_id) DO NOTHING",
                        (device, item["id"], item["kind"], item["ref_id"], item["incident_id"], Jsonb(payload)))
            cur.execute("INSERT INTO hub_incidents(incident_id,version,payload,device) VALUES(%s,%s,%s,%s) "
                        "ON CONFLICT (incident_id) DO UPDATE SET version=GREATEST(hub_incidents.version, EXCLUDED.version), "
                        "payload=EXCLUDED.payload, received_at=now()",
                        (item["incident_id"], local_v, Jsonb(payload), device))

    def set_version(self, iid, v):
        with self.c.cursor() as cur:
            cur.execute("INSERT INTO hub_incidents(incident_id,version,payload) VALUES(%s,%s,%s) "
                        "ON CONFLICT (incident_id) DO UPDATE SET version=EXCLUDED.version",
                        (iid, v, Jsonb({"op": "hub_edit", "destination": "changed by ED"})))

    def counts(self):
        with self.c.cursor() as cur:
            cur.execute("SELECT (SELECT count(*) FROM hub_incidents), (SELECT count(*) FROM hub_items)")
            a, b = cur.fetchone()
        return {"incidents": a, "items": b}

    def commit(self):
        self.c.commit()

    def close(self):
        self.c.close()


class _Sim:
    """Simulated hub stored in the device DB (demo fallback)."""

    def __init__(self):
        self.ops = []

    def version(self, iid):
        r = db.q1("SELECT version FROM hub WHERE incident_id=?", (iid,))
        return r["version"] if r else None

    def receive(self, device, item, local_v):
        self.ops.append(("INSERT INTO hub(incident_id,version,payload,received_at) VALUES(?,?,?,?) "
                         "ON CONFLICT(incident_id) DO UPDATE SET version=MAX(version, excluded.version), payload=excluded.payload, received_at=excluded.received_at",
                         (item["incident_id"], local_v, item["payload"], datetime.now(timezone.utc).isoformat(timespec="seconds"))))

    def set_version(self, iid, v):
        self.ops.append(("INSERT INTO hub(incident_id,version,payload,received_at) VALUES(?,?,?,?) "
                         "ON CONFLICT(incident_id) DO UPDATE SET version=excluded.version",
                         (iid, v, json.dumps({"op": "hub_edit"}), datetime.now(timezone.utc).isoformat(timespec="seconds"))))

    def counts(self):
        return {"incidents": db.q1("SELECT COUNT(*) n FROM hub")["n"], "items": db.q1("SELECT COUNT(*) n FROM outbox WHERE status!='queued'")["n"]}

    def commit(self):
        with db.tx() as c:
            for sql, args in self.ops:
                c.execute(sql, args)
        self.ops = []

    def close(self):
        pass


def open_hub():
    return _PG() if engine() == "postgresql" else _Sim()


def status() -> dict:
    out = {"engine": engine(), "url": masked(url()), "psycopg_installed": psycopg is not None}
    try:
        h = open_hub()
        out.update(h.counts())
        h.close()
        out["ok"] = True
    except HubError as e:
        out.update({"ok": False, "error": str(e)})
    return out
