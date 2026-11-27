"""One-command launcher: python run.py  ->  http://127.0.0.1:8000"""
import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

# use a pre-downloaded offline model if present
for size in ("large-v3-turbo", "distil-large-v3", "medium", "small", "base", "tiny"):
    p = BACKEND / "models" / size
    if p.exists() and any(p.iterdir()) and "FIELDSCRIBE_ASR_MODEL" not in os.environ:
        os.environ["FIELDSCRIBE_ASR_MODEL"] = str(p)
        break

if not (ROOT / "frontend" / "dist" / "index.html").exists():
    print("! frontend/dist not found. Build it: cd frontend && npm install && npm run build")

import uvicorn  # noqa: E402

port = int(os.environ.get("PORT", 8000))
host = os.environ.get("HOST", "127.0.0.1")
url = f"http://127.0.0.1:{port}"
print(f"\n  FieldScribe running at {url}\n  API docs at {url}/docs\n  Ctrl+C to stop\n")
if host == "0.0.0.0":
    # TABLET MODE: plain HTTP for this laptop and the phone set-up page, HTTPS (8443) for phones and tablets,
    # because phones only allow the microphone and "Add to Home screen" on secure pages.
    from app import tls
    t = tls.ensure()
    os.environ["FIELDSCRIBE_HTTPS_ON"] = "1"
    setup = [f"http://{i}:{port}/phone" for i in t["ips"]]
    print("  TABLET / PHONE MODE")
    print("  On each phone or tablet (same Wi-Fi or this laptop's hotspot), open or scan:")
    for u in setup or ["http://<this laptop's Wi-Fi IP address>:%d/phone" % port]:
        print(f"      {u}")
    if setup:
        try:
            import qrcode
            q = qrcode.QRCode(border=1)
            q.add_data(setup[0])
            q.print_ascii(invert=True)
        except Exception:
            pass
    print(f"  Secure address for phones: {', '.join(t['https_urls']) or 'https://<ip>:8443'}")
    print(f"  Certificate fingerprint starts with {t['fingerprint']}")
    print("  (If Windows asks about the firewall, allow Private networks only.)\n")
    if "--no-browser" not in sys.argv:
        threading.Timer(2.0, lambda: webbrowser.open(url + "/settings#prefs")).start()

    import asyncio
    from app.main import app as asgi

    async def _both():
        http = uvicorn.Server(uvicorn.Config(asgi, host=host, port=port, log_level="warning"))
        https = uvicorn.Server(uvicorn.Config(asgi, host=host, port=tls.HTTPS_PORT, log_level="warning",
                                              ssl_keyfile=t["key"], ssl_certfile=t["cert"]))
        await asyncio.gather(http.serve(), https.serve())
    asyncio.run(_both())
else:
    if "--no-browser" not in sys.argv:
        threading.Timer(2.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=host, port=port, log_level="warning")
