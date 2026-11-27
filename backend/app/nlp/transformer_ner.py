"""DistilBERT token-classification inference (optional). Loaded lazily if a trained
model exists at backend/models/ner-distilbert (or FIELDSCRIBE_NER_MODEL)."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

MODEL_DIR = Path(os.environ.get("FIELDSCRIBE_NER_MODEL", Path(__file__).resolve().parents[2] / "models" / "ner-distilbert"))
MODE = os.environ.get("FIELDSCRIBE_NER_MODE", "hybrid")  # hybrid | rules

_lock = threading.Lock()
_state: dict = {"model": None, "tok": None, "error": None, "load_s": None}


def _deps() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def available() -> bool:
    return MODE == "hybrid" and (MODEL_DIR / "config.json").exists() and _deps()


def status() -> dict:
    meta = {}
    mf = MODEL_DIR / "metrics.json"
    if mf.exists():
        try:
            meta = json.loads(mf.read_text())
        except Exception:
            pass
    return {"enabled": MODE == "hybrid", "trained": (MODEL_DIR / "config.json").exists(), "deps": _deps(),
            "available": available(), "loaded": _state["model"] is not None, "path": str(MODEL_DIR),
            "base": meta.get("base"), "metrics": meta.get("test_span_metrics"), "train_sentences": meta.get("train_sentences"),
            "epochs": meta.get("epochs"), "load_seconds": _state["load_s"], "error": _state["error"]}


def _load():
    with _lock:
        if _state["model"] is None and _state["error"] is None:
            t0 = time.time()
            try:
                import torch
                from transformers import AutoModelForTokenClassification, AutoTokenizer
                torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
                _state["tok"] = AutoTokenizer.from_pretrained(MODEL_DIR)
                m = AutoModelForTokenClassification.from_pretrained(MODEL_DIR)
                m.eval()
                _state["model"] = m
                _state["load_s"] = round(time.time() - t0, 2)
            except Exception as e:  # pragma: no cover
                _state["error"] = str(e)
    return _state["model"], _state["tok"]


def predict(text: str) -> list[dict]:
    """Return spans [{start, end, label, score}] over `text` (already normalised)."""
    if not available() or not text.strip():
        return []
    model, tok = _load()
    if model is None:
        return []
    import torch
    enc = tok(text, return_offsets_mapping=True, truncation=True, max_length=256, return_tensors="pt")
    offs = enc.pop("offset_mapping")[0].tolist()
    with torch.no_grad():
        probs = torch.softmax(model(**enc).logits[0], -1)
    conf, ids = probs.max(-1)
    id2label = model.config.id2label
    spans, cur = [], None
    for (s, e), i, p in zip(offs, ids.tolist(), conf.tolist()):
        if s == e:
            continue
        lab = id2label[i] if isinstance(next(iter(id2label)), int) else id2label[str(i)]
        if lab == "O":
            if cur:
                spans.append(cur); cur = None
            continue
        typ = lab[2:]
        # continue a span across sub-word pieces even if the model wrote B- mid-word
        contiguous = cur is not None and cur["label"] == typ and s <= cur["end"] + 1
        if contiguous and (lab.startswith("I-") or s == cur["end"]):
            cur["end"] = e
            cur["ps"].append(p)
        else:
            if cur:
                spans.append(cur)
            cur = {"start": s, "end": e, "label": typ, "ps": [p]}
    if cur:
        spans.append(cur)
    for sp in spans:
        sp["score"] = round(sum(sp["ps"]) / len(sp["ps"]), 3)
        sp["text"] = text[sp["start"]:sp["end"]]
        del sp["ps"]
    return spans
