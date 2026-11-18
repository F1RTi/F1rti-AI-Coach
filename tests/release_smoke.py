"""Extract the final installer and use only its interpreter and libraries to serve, import and reopen."""

import gzip
import os
import subprocess
import tempfile
import time
from pathlib import Path

import httpx


def main():
    work = Path(".work").resolve()
    base = Path(tempfile.mkdtemp(dir=work, prefix="release-test-"))
    app = base / "app"
    data = base / "data"
    subprocess.run(
        [
            str(Path("release/F1rti-AI-Coach-Setup.exe").resolve()),
            "--test-install",
            str(app),
        ],
        check=True,
    )
    assert len(list((app / "shortcut-test").rglob("*.lnk"))) == 2
    proc = None

    def launch(mode):
        landing = data / "instance.url.txt"
        landing.unlink(missing_ok=True)
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME")
        }
        p = subprocess.Popen(
            [
                str(app / "pythonw.exe"),
                str(app / "desktop.py"),
                mode,
                "--data",
                str(data),
            ],
            cwd=base,
            env=env,
        )
        for _ in range(200):
            if p.poll() is not None:
                raise RuntimeError("Standalone desktop exited")
            if landing.is_file() and "#" in landing.read_text():
                base_url, token = landing.read_text().split("#")
                return p, httpx.Client(
                    base_url=base_url + "api/",
                    headers={"x-coach-token": token},
                    timeout=60,
                    trust_env=False,
                )
            time.sleep(0.1)
        p.terminate()
        raise RuntimeError("Standalone startup timeout")

    try:
        proc, client = launch("--tray")
        state = client.get("state").raise_for_status().json()
        assert not state["matches"] and state["goal"]["current"] is None
        assert client.post(
            "settings", json=state["options"] | {"steam_id": "76561197964020430"}
        ).is_success
        with open(".work/upstream.dem", "rb") as f:
            payload = gzip.compress(f.read(), compresslevel=1)
        key = (
            client.post("demo", params={"name": "public-test.dem.gz"}, content=payload)
            .raise_for_status()
            .json()["id"]
        )
        for _ in range(180):
            d = client.get("state").raise_for_status().json()["demos"][0]
            if d["status"] == "done":
                break
            assert d["status"] != "error", d["error"]
            time.sleep(0.5)
        assert d["status"] == "done"
        summary = client.get("demo/" + key).json()["summary"]
        assert summary["rounds"] == 10 and summary["metrics"]["kills"] == 11
        plan = (
            client.post("plan", json={"kind": "День", "skill": "Aim"})
            .raise_for_status()
            .json()["id"]
        )
        client.close()
        proc.terminate()
        proc.wait(20)
        proc, client = launch("--headless")
        after = client.get("state").raise_for_status().json()
        assert (
            after["demos"][0]["id"] == key
            and after["training"]["exercises"][0]["plan"] == plan
        )
        client.close()
        print(
            "Independent installer, tray startup, real gzip analysis, persistence OK.",
            base,
        )
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(20)


if __name__ == "__main__":
    main()
