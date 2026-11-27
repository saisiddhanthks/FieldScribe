"""
FieldScribe desktop app (Windows, macOS, Linux).

Double-click the FieldScribe shortcut: this starts the on-device backend with no console window, shows a small
start-up screen, then opens FieldScribe in its own app window (Microsoft Edge or Chrome in app mode, which
every Windows 10/11 laptop has). Closing the window stops FieldScribe. If FieldScribe is already running, it
just opens another window.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 8000))
URL = f"http://127.0.0.1:{PORT}"
WIN = platform.system() == "Windows"
STATE = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "FieldScribe"
STATE.mkdir(parents=True, exist_ok=True)
LOG = STATE / "fieldscribe.log"
NO_WINDOW = 0x08000000 if WIN else 0


def up() -> bool:
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def python_exe() -> str:
    """The console-less interpreter's sibling python.exe in the same venv (so the backend has no window either)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def start_backend() -> subprocess.Popen:
    log = open(LOG, "ab")
    log.write(f"\n==== start {time.ctime()} ====\n".encode())
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    return subprocess.Popen([python_exe(), str(ROOT / "run.py"), "--no-browser"], cwd=str(ROOT), stdout=log, stderr=log,
                            stdin=subprocess.DEVNULL, env=env, creationflags=NO_WINDOW)


def app_browser() -> str | None:
    if WIN:
        pf = [os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", r"C:\Program Files"),
              os.environ.get("LOCALAPPDATA", "")]
        for base in pf:
            for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe", r"BraveSoftware\Brave-Browser\Application\brave.exe"):
                p = Path(base) / rel
                if p.exists():
                    return str(p)
        return None
    if platform.system() == "Darwin":
        for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"):
            if Path(p).exists():
                return p
        return None
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("microsoft-edge")


def open_window() -> subprocess.Popen | None:
    b = app_browser()
    if not b:
        webbrowser.open(URL)
        return None
    return subprocess.Popen([b, f"--app={URL}", f"--user-data-dir={STATE / 'window'}", "--window-size=1440,900",
                             "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def splash_and_wait(backend: subprocess.Popen) -> bool:
    """Small start-up window while the backend loads (first start can take ~20 s while models load)."""
    def poll() -> bool:
        for _ in range(300):
            if up():
                return True
            if backend.poll() is not None:
                return False
            time.sleep(0.5)
        return False

    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception:            # no display / no Tk: wait without a splash
        return poll()
    ok = {"v": False}
    root.overrideredirect(True)
    root.configure(bg="#000000")
    w, h = 420, 170
    root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}")
    root.attributes("-topmost", True)
    tk.Label(root, text="FieldScribe", fg="#e8eef2", bg="#000000", font=("Segoe UI Semibold", 22)).pack(pady=(26, 2))
    msg = tk.Label(root, text="Starting the on-device record…", fg="#8a979f", bg="#000000", font=("Segoe UI", 11))
    msg.pack()
    bar = tk.Canvas(root, width=300, height=4, bg="#182027", highlightthickness=0)
    bar.pack(pady=18)
    seg = bar.create_rectangle(0, 0, 70, 4, fill="#3ee07f", width=0)
    steps = ["Starting the on-device record…", "Opening the encrypted database…", "Loading speech and language models…", "Almost ready…"]
    t0 = time.time()

    def tick():
        x = (time.time() * 220) % 370 - 70
        bar.coords(seg, x, 0, x + 70, 4)
        msg.config(text=steps[min(int((time.time() - t0) / 5), len(steps) - 1)])
        if up():
            ok["v"] = True
            root.destroy()
            return
        if backend.poll() is not None or time.time() - t0 > 150:
            msg.config(text=f"FieldScribe could not start. See {LOG}", fg="#ff4b4b")
            root.after(6000, root.destroy)
            return
        root.after(60, tick)

    root.after(60, tick)
    root.mainloop()
    return ok["v"]


def main() -> None:
    if up():                                   # already running: just open a window
        open_window()
        return
    backend = start_backend()
    if not splash_and_wait(backend):
        if backend.poll() is None:
            backend.terminate()
        if WIN:
            os.startfile(str(LOG))             # show the log so the problem is visible
        return
    win = open_window()
    try:
        if win is not None:
            t0 = time.time()
            win.wait()
            if time.time() - t0 < 4:           # the browser handed the window to an already-open instance
                while up():                    # keep serving until that window is gone or the backend stops
                    time.sleep(5)
                    if not _app_window_alive():
                        break
        else:
            _keepalive_window()
    finally:
        if backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(8)
            except Exception:
                backend.kill()


def _app_window_alive() -> bool:
    if not WIN:
        return True
    try:
        ps = ("Get-CimInstance Win32_Process -Filter \"name='msedge.exe' or name='chrome.exe' or name='brave.exe'\" "
              "| Select-Object -ExpandProperty CommandLine")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=15,
                             creationflags=NO_WINDOW).stdout
        return str(STATE / "window").lower() in out.lower()
    except Exception:
        return True


def _keepalive_window() -> None:
    """No app-capable browser: FieldScribe opened in the default browser; this little window keeps it running."""
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception:
        while up():
            time.sleep(10)
        return
    root.title("FieldScribe")
    root.configure(bg="#000000")
    root.geometry("360x130")
    tk.Label(root, text=f"FieldScribe is running at {URL}", fg="#e8eef2", bg="#000000", font=("Segoe UI", 11)).pack(pady=(24, 8))
    tk.Button(root, text="Open again", command=lambda: webbrowser.open(URL)).pack()
    tk.Label(root, text="Close this window to stop FieldScribe.", fg="#8a979f", bg="#000000", font=("Segoe UI", 9)).pack(pady=8)
    root.mainloop()


if __name__ == "__main__":
    threading.excepthook = lambda a: None
    main()
