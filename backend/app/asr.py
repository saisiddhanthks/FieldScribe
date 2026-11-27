"""
Offline speech recognition with faster-whisper (CTranslate2, int8 on CPU).

The model is downloaded once (or copied onto the device) and then runs with no
network. A clinical vocabulary prompt biases decoding toward drug names and
Indian brands, which measurably helps on mis-heard terms like "ecosprin".
"""
from __future__ import annotations

import os
import tempfile
import threading
import time

from .nlp import lexicon as L

MODEL_NAME = os.environ.get("FIELDSCRIBE_ASR_MODEL", "small")     # tiny | base | small | medium | path
COMPUTE = os.environ.get("FIELDSCRIBE_ASR_COMPUTE", "int8")
DEVICE = os.environ.get("FIELDSCRIBE_ASR_DEVICE", "cpu")

_model = None
_lock = threading.Lock()
_error: str | None = None

try:
    import faster_whisper  # noqa: F401
    AVAILABLE = True
except Exception:  # pragma: no cover
    AVAILABLE = False

PROMPT = ("Ambulance EMT handover. Medications: " + ", ".join(list(L.DRUGS)[:28]) +
          ". Brands: Ecosprin, Dolo, Crocin, Avil, Emeset, Asthalin, Voveran, Efcorlin, Calmpose. "
          "Units mg, mcg, mL, litres per minute. Routes IV, IM, oral, sublingual, nebulised. GCS, SpO2, BP, GRBS.")

# Code-mixed prompts: written the way crews actually speak, with English drug names and numbers kept in Latin
# letters so Whisper copies that style instead of spelling "aspirin" in Devanagari or Kannada.
PROMPTS = {
    "en": PROMPT,
    "hi": "मरीज़ को सीने में दर्द, 58 साल का आदमी, aspirin 300 mg मुँह से दिया, BP 150/90, SpO2 94. "
          "साँस लेने में दिक्कत, salbutamol nebulisation 5 mg दिया. ondansetron 4 mg IV, dextrose 25% 100 mL.",
    "kn": "ರೋಗಿಗೆ ಎದೆ ನೋವು, 60 ವರ್ಷದ ಗಂಡಸು, aspirin 300 mg ಬಾಯಲ್ಲಿ ಕೊಟ್ಟಿದ್ದೀನಿ, BP 140/90, SpO2 95. "
          "ಉಸಿರಾಟದ ತೊಂದರೆ, salbutamol nebulisation 5 mg ಕೊಟ್ಟಿದ್ದೀನಿ. ondansetron 4 mg IV, dextrose 25% 100 mL.",
}
LANGS = {"en": "English", "hi": "Hindi + English", "kn": "Kannada + English", "auto": "Detect automatically"}


def status() -> dict:
    return {"available": AVAILABLE, "loaded": _model is not None, "model": MODEL_NAME, "compute_type": COMPUTE,
            "device": DEVICE, "error": _error, "engine": "faster-whisper (CTranslate2)" if AVAILABLE else None}


def _load():
    global _model, _error
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            try:
                _model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE)
                _error = None
            except Exception as e:  # pragma: no cover
                _error = str(e)
                raise
    return _model


def decode_audio(path: str, sr: int = 16000):
    """Decode any browser recording (webm/opus, ogg, wav, mp4) to 16 kHz mono float32 with PyAV.
    Done here instead of inside faster-whisper so it works with every PyAV version
    (PyAV 19 removed an argument that faster-whisper's own decoder passes)."""
    import av
    import numpy as np
    chunks = []
    with av.open(path, mode="r") as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sr)
        for frame in container.decode(stream):
            for out in resampler.resample(frame) or []:
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None) or []:  # flush
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return (np.concatenate(chunks).astype(np.float32) / 32768.0)


def transcribe(data: bytes, suffix: str = ".webm", language: str | None = "en") -> dict:
    if not AVAILABLE:
        raise RuntimeError("faster-whisper is not installed. Run: pip install faster-whisper  (see README > Offline ASR)")
    model = _load()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        path = f.name
    try:
        t0 = time.perf_counter()
        audio = decode_audio(path)
        if audio.size < 1600:  # < 0.1 s
            return {"text": "", "segments": [], "language": language, "language_probability": 0, "audio_seconds": round(audio.size / 16000, 2),
                    "elapsed_seconds": 0, "rtf": None, "model": MODEL_NAME, "compute_type": COMPUTE}
        segments, info = model.transcribe(audio, language=language, vad_filter=True, beam_size=5,
                                          initial_prompt=PROMPTS.get(language or "en", PROMPT), condition_on_previous_text=False)
        segs = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                 "avg_logprob": round(s.avg_logprob, 3), "no_speech_prob": round(s.no_speech_prob, 3)} for s in segments]
        elapsed = time.perf_counter() - t0
        text = " ".join(s["text"] for s in segs).strip()
        dur = getattr(info, "duration", 0) or 0
        return {"text": text, "segments": segs, "language": info.language, "language_probability": round(info.language_probability, 3),
                "audio_seconds": round(dur, 2), "elapsed_seconds": round(elapsed, 2),
                "rtf": round(elapsed / dur, 3) if dur else None, "model": MODEL_NAME, "compute_type": COMPUTE}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def wer(ref: str, hyp: str) -> dict:
    import re
    r = re.findall(r"[a-z0-9.]+", ref.lower())
    h = re.findall(r"[a-z0-9.]+", hyp.lower())
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (r[i - 1] != h[j - 1]))
    # backtrace for S/D/I counts
    i, j, S, D, I = len(r), len(h), 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (r[i - 1] != h[j - 1]):
            S += r[i - 1] != h[j - 1]
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            D += 1
            i -= 1
        else:
            I += 1
            j -= 1
    n = max(len(r), 1)
    return {"wer": round(d[len(r)][len(h)] / n, 4), "substitutions": S, "deletions": D, "insertions": I, "ref_words": len(r)}
