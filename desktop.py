import argparse
import ctypes
import hashlib
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from backend.db import Store


def autorun(enabled):
    import winreg

    from backend.worker import command

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                "F1rti AI Coach",
                0,
                winreg.REG_SZ,
                subprocess.list2cmdline(command("--tray")),
            )
        else:
            try:
                winreg.DeleteValue(key, "F1rti AI Coach")
            except FileNotFoundError:
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.getenv("LOCALAPPDATA", ".")) / "F1rti AI Coach" / "data",
    )
    parser.add_argument("--parse")
    parser.add_argument("--player", default="")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--tray", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    root = args.data.resolve()
    if args.parse:
        from backend.demo import parse

        store = Store(root)
        try:
            parse(store, args.parse, args.player)
        except BaseException as exc:
            with store.connect() as db:
                db.execute(
                    "UPDATE demos SET status='error',error=? WHERE id=?",
                    ("Ошибка чтения CS2 demo · " + str(exc)[:280], args.parse),
                )
            return 1
        return 0
    import uvicorn

    from backend.api import create
    from backend.reports import browser
    from backend.secrets import Vault
    from backend.worker import Engine

    root.mkdir(parents=True, exist_ok=True)
    landing = root / "instance.url.txt"

    def show(url):
        exe = browser()
        if exe:
            subprocess.Popen([exe, "--app=" + url])
        else:
            webbrowser.open(url)

    # OS releases the instance mutex on crash.
    mutex_name = (
        "Local\\F1rtiCoach-"
        + hashlib.sha256(str(root).lower().encode()).hexdigest()[:16]
    )
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, False, mutex_name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        if landing.exists() and not (args.headless or args.tray):
            existing = landing.read_text().strip()
            if existing.startswith("http://127.0.0.1:"):
                show(existing)
        return 0
    store = Store(root)
    vault = Vault(root)
    sock = socket.socket()
    sock.bind(("127.0.0.1", args.port))
    port = sock.getsockname()[1]
    host = f"127.0.0.1:{port}"
    token = secrets.token_urlsafe(32)
    url = "http://" + host + "/#" + token
    icon = None

    def notify(msg):
        if icon:
            try:
                icon.notify(msg, "F1rti AI Coach")
            except Exception:
                pass

    engine = Engine(store, vault, notify)
    static = Path(__file__).resolve().parent / "frontend" / "dist"
    api = create(store, vault, engine, token, host, static, autorun)
    server = uvicorn.Server(
        uvicorn.Config(
            api, host="127.0.0.1", port=port, log_config=None, access_log=False
        )
    )

    def shutdown(*_):
        server.should_exit = True
        if icon:
            icon.stop()

    if not args.headless:
        import pystray
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (64, 64), "#1c2023")
        draw = ImageDraw.Draw(img)
        draw.polygon(
            [
                (10, 50),
                (24, 13),
                (53, 13),
                (49, 23),
                (32, 23),
                (29, 30),
                (44, 30),
                (40, 40),
                (25, 40),
                (21, 50),
            ],
            fill="#ff6a28",
        )
        icon = pystray.Icon(
            "F1rti",
            img,
            "F1rti AI Coach",
            menu=pystray.Menu(
                pystray.MenuItem("Открыть аналитику", lambda: show(url), default=True),
                pystray.MenuItem("Выход", shutdown),
            ),
        )
        threading.Thread(target=icon.run, daemon=True).start()

    def ready():
        while not server.started and not server.should_exit:
            time.sleep(0.05)
        if server.started:
            landing.write_text(url, encoding="ascii")
            engine.start()
            if not args.headless and not args.tray:
                show(url)

    threading.Thread(target=ready, daemon=True).start()
    try:
        server.run(sockets=[sock])
    finally:
        engine.close()
        if icon:
            icon.stop()
        landing.unlink(missing_ok=True)
        sock.close()
        kernel.CloseHandle(ctypes.c_void_p(handle))
    return 0


if __name__ == "__main__":
    sys.exit(main())
