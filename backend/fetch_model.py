"""Download a Whisper model once so the device can run fully offline afterwards.

    python fetch_model.py                   # small: fast on any laptop (~480 MB)
    python fetch_model.py large-v3-turbo    # most accurate, best for Indian accents (~1.6 GB, needs 8 GB RAM)
    python fetch_model.py base              # older laptops (~145 MB)

If several are downloaded, run.py uses the most accurate one. Override with
FIELDSCRIBE_ASR_MODEL in backend/.env.

Then start FieldScribe with FIELDSCRIBE_ASR_MODEL pointing at the printed folder
(run scripts do this automatically if ./models/<size> exists).
"""
import sys
from pathlib import Path

from faster_whisper import download_model

size = sys.argv[1] if len(sys.argv) > 1 else "small"
out = Path(__file__).resolve().parent / "models" / size
out.mkdir(parents=True, exist_ok=True)
path = download_model(size, output_dir=str(out))
print(f"Model ready at: {path}")
