"""Load backend/.env (KEY=VALUE lines) into the environment without overriding real env vars."""
import os
from pathlib import Path

ENV_FILE = Path(os.environ.get("FIELDSCRIBE_ENV", Path(__file__).resolve().parent.parent / ".env"))


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v
