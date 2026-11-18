import json
import subprocess
import sys
import threading
from pathlib import Path

from . import coach, demo, reports
from .analytics import sessions, snapshot
from .db import now
from .faceit import FaceitClient, ServiceError, synchronize


def command(*args):
    return [
        sys.executable,
        *(
            []
            if getattr(sys, "frozen", False)
            else [str(Path(__file__).resolve().parents[1] / "desktop.py")]
        ),
        *args,
    ]


class Engine:
    def __init__(self, store, vault, notify=lambda message: None):
        self.store, self.vault, self.notify = store, vault, notify
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.stable = {}
        self.next_watch = 0
        self.active = threading.Lock()

    def start(self):
        with self.store.connect() as db:
            db.execute(
                "UPDATE demos SET status='queued',progress=0 WHERE status='running'"
            )
            db.execute("UPDATE jobs SET state='queued' WHERE state='running'")
            db.execute(
                "UPDATE demos SET status='queued',progress=0 WHERE status='done' AND version!=?",
                (demo.VERSION,),
            )
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def enqueue(self, kind):
        if kind == "sync" and self.store.settings().get("retry_at", 0) > now():
            raise ValueError(
                "Действует интервал ожидания FACEIT. Синхронизация повторится автоматически."
            )
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id FROM jobs WHERE kind=? AND state IN ('queued','running')",
                (kind,),
            ).fetchone()
            if not existing:
                db.execute(
                    "INSERT INTO jobs(kind,state,at,message) VALUES(?,'queued',?,'')",
                    (kind, now()),
                )
        self.wake.set()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(3)

    def check(self):
        if self.stop.is_set() or self.store.settings()["paused"]:
            raise InterruptedError

    def watch(self, path):
        if not path:
            return
        directory = Path(path)
        if not directory.is_dir():
            return
        for p in directory.iterdir():
            self.check()
            if not p.is_file() or not p.name.lower().endswith((".dem", ".dem.gz")):
                continue
            st = p.stat()
            sig = f"{st.st_size}:{st.st_mtime_ns}"
            if self.stable.get(p) != sig:
                self.stable[p] = sig
                continue
            if self.store.rows(
                "SELECT 1 FROM watched WHERE path=? AND signature=?", (str(p), sig)
            ):
                continue
            try:
                with p.open("rb") as stream:
                    demo.ingest(self.store, stream, p.name)
            except (ValueError, EOFError, OSError) as exc:
                self.log("watch", "error", p.name + " · " + str(exc)[:180])
            with self.store.connect() as db:
                db.execute("INSERT OR REPLACE INTO watched VALUES(?,?)", (str(p), sig))

    def log(self, kind, state, message):
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO jobs(kind,state,at,message) VALUES(?,?,?,?)",
                (kind, state, now(), message),
            )

    def derived(self):
        snapshot(self.store)
        coach.refresh(self.store)
        coach.update_daily(self.store)
        games = self.store.matches()
        cache = {
            r["id"]: r["data"] for r in self.store.rows("SELECT id,data FROM reports")
        }
        for g in games:
            previous = cache.get("Матч-" + g["id"])
            if previous is None or not json.loads(previous).get("complete"):
                reports.report(self.store, "Матч", g["id"], games=[g])
        for group in sessions(games, self.store.settings()["session_gap"]):
            previous = json.loads(cache.get("Сессия-" + group["id"], "{}"))
            if set(previous.get("matches", [])) != set(
                group["matches"]
            ) or not previous.get("complete"):
                reports.report(self.store, "Сессия", games=games, group=group)
        for kind in ("Неделя", "Месяц"):
            try:
                reports.report(self.store, kind, games=games)
            except ValueError:
                pass

    def work_demo(self, row):
        key = row["id"]
        settings = self.store.settings()
        accounts = self.store.rows("SELECT steam FROM players")
        player = settings["steam_id"] or (accounts[0]["steam"] if accounts else "")
        with self.store.connect() as db:
            db.execute(
                "UPDATE demos SET status='running',progress=1,error=NULL WHERE id=?",
                (key,),
            )
        proc = subprocess.Popen(
            command(
                "--parse", key, "--data", str(self.store.root), "--player", player or ""
            ),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        while proc.poll() is None:
            if self.stop.wait(0.7) or self.store.settings()["paused"]:
                proc.terminate()
                proc.wait()
                with self.store.connect() as db:
                    db.execute(
                        "UPDATE demos SET status='queued',progress=0 WHERE id=? AND status='running'",
                        (key,),
                    )
                return
        if proc.returncode:
            with self.store.connect() as db:
                db.execute(
                    "UPDATE demos SET status='error',error=coalesce(error,'Парсер завершился с ошибкой') WHERE id=?",
                    (key,),
                )
        else:
            if self.store.settings()["steam_id"] != settings["steam_id"]:
                with self.store.connect() as db:
                    db.execute(
                        "UPDATE demos SET status='queued',progress=0 WHERE id=?", (key,)
                    )
                return
            self.derived()
            if settings["notifications"]:
                self.notify("Готов разбор " + row["name"])

    def job(self, row):
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET state='running' WHERE id=?", (row["id"],))
        state, msg = "done", ""
        try:
            if row["kind"] == "sync":
                key = self.vault.read("faceit")
                if not key:
                    raise ValueError("Введите ключ FACEIT в настройках")
                client = FaceitClient(key)
                try:
                    count = synchronize(self.store, client, self.check)
                finally:
                    client.http.close()
                accounts = self.store.rows("SELECT steam FROM players")
                player = self.store.settings()["steam_id"] or (
                    accounts[0]["steam"] if accounts else ""
                )
                if player:
                    with self.store.connect() as db:
                        for item in db.execute(
                            "SELECT id,summary FROM demos WHERE status='done'"
                        ).fetchall():
                            summary = json.loads(item["summary"])
                            if (
                                player in summary["players"]
                                and summary["player"] != player
                            ):
                                db.execute(
                                    "UPDATE demos SET status='queued',progress=0 WHERE id=?",
                                    (item["id"],),
                                )
                self.derived()
                msg = f"Обновлено матчей · {count}"
            elif row["kind"] == "ai":
                s = self.store.settings()
                key = self.vault.read("ai")
                provider = None
                if key:
                    credential = json.loads(key)
                    if credential["base"] != s["ai_base"]:
                        raise ValueError("Введите ключ для выбранного адреса AI")
                    provider = coach.CompatibleProvider(
                        s["ai_base"], credential["key"], s["model"]
                    )
                coach.refresh(self.store, provider)
                coach.update_daily(self.store)
                msg = "Приоритеты обновлены"
            if self.store.settings()["notifications"]:
                self.notify(msg)
        except InterruptedError:
            state, msg = "queued", "Пауза"
        except (ServiceError, ValueError) as e:
            state, msg = "error", str(e)[:240]
            if isinstance(e, ServiceError) and e.retry_after and row["kind"] == "sync":
                self.store.change({"retry_at": now() + int(e.retry_after) + 1})
        except Exception as e:
            state, msg = "error", "Ошибка обработки · " + type(e).__name__
        with self.store.connect() as db:
            db.execute(
                "UPDATE jobs SET state=?,message=?,at=? WHERE id=?",
                (state, msg, now(), row["id"]),
            )

    def cycle(self):
        s = self.store.settings()
        if s["paused"]:
            return
        if now() >= self.next_watch:
            self.next_watch = now() + 15
            self.watch(s["watch"])
        if self.vault.file("faceit").exists():
            last = (
                self.store.rows("SELECT max(at) AS stamp FROM jobs WHERE kind='sync'")[
                    0
                ]["stamp"]
                or 0
            )
            if now() - last >= s["sync_minutes"] * 60 and now() >= s.get("retry_at", 0):
                self.enqueue("sync")
        jobs = self.store.rows(
            "SELECT * FROM jobs WHERE state='queued' ORDER BY id LIMIT 1"
        )
        if jobs:
            self.job(jobs[0])
        self.check()
        pending = self.store.rows(
            "SELECT * FROM demos WHERE status='queued' ORDER BY updated LIMIT 1"
        )
        if pending:
            self.work_demo(pending[0])

    def loop(self):
        while not self.stop.is_set():
            try:
                with self.active:
                    self.cycle()
            except InterruptedError:
                pass
            except Exception as exc:
                self.log(
                    "worker", "error", "Ошибка фоновой задачи · " + type(exc).__name__
                )
            self.wake.wait(2)
            self.wake.clear()
