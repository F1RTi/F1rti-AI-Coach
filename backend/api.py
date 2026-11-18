import hmac
import json
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import analytics, coach, demo, reports
from .db import DEFAULTS, dump, now


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sync_minutes: int = Field(ge=5, le=1440)
    session_gap: int = Field(ge=10, le=720)
    minutes: int = Field(ge=5, le=180)
    watch: str = Field(max_length=500)
    steam_id: str = Field(pattern=r"^(|[0-9]{17})$")
    paused: bool
    notifications: bool
    ai_base: str = Field(max_length=300)
    model: str = Field(min_length=1, max_length=120)
    autostart: bool


class Secret(BaseModel):
    key: str = Field(max_length=4096)


class Plan(BaseModel):
    kind: str
    skill: str = ""


class DemoLink(BaseModel):
    match_id: str


class Completion(BaseModel):
    done: bool
    difficulty: int = Field(ge=1, le=5, default=3)


class Diary(BaseModel):
    wellbeing: int | None = Field(None, ge=1, le=5)
    focus: int | None = Field(None, ge=1, le=5)
    fatigue: int | None = Field(None, ge=1, le=5)
    stress: int | None = Field(None, ge=1, le=5)
    rating: int | None = Field(None, ge=1, le=5)
    note: str = Field(default="", max_length=3000)


class Report(BaseModel):
    kind: Literal["Матч", "Сессия", "Неделя", "Месяц"]
    ref: str = ""


class Reset(BaseModel):
    confirm: Literal["УДАЛИТЬ"]


def create(store, vault, engine, token, host, static, autorun=lambda enabled: None):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def local(request, call_next):
        if request.headers.get("host") != host:
            return Response(status_code=403)
        if request.url.path.startswith("/api/"):
            if not hmac.compare_digest(
                request.headers.get("x-coach-token", "").encode(), token.encode()
            ):
                return Response(status_code=401)
            origin = request.headers.get("origin")
            if origin and origin != "http://" + host:
                return Response(status_code=403)
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            }
        )
        return response

    @app.exception_handler(ValueError)
    async def invalid(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    def required(sql, args):
        rows = store.rows(sql, args)
        if not rows:
            raise HTTPException(404, "Запись не найдена")
        return rows[0]

    @app.get("/api/state")
    def state(window: int = 20, days: int = 0):
        if window not in analytics.WINDOWS or days not in (0, 7, 30, 90):
            raise ValueError("Неизвестный период")
        s = store.settings()
        current, history = coach.advice(store)
        matches = store.matches()
        ratings = store.rows("SELECT * FROM ratings ORDER BY at")
        groups = analytics.sessions(matches, s["session_gap"], ratings)
        filtered = [
            m
            for m in matches
            if not days or (m["finished"] or 0) >= now() - days * 86400
        ]
        notes = {
            r["session_id"]: json.loads(r["data"])
            for r in store.rows("SELECT * FROM diary")
        }
        for g in groups:
            g["diary"] = notes.get(g["id"], {})
        return dict(
            options={k: s[k] for k in DEFAULTS},
            keys={k: vault.file(k).exists() for k in ("faceit", "ai")},
            goal=analytics.goal(ratings),
            analytics=analytics.analysis(store, window, filtered),
            matches=matches,
            sessions=groups,
            insights=current,
            history=history,
            evaluations=coach.evaluations(store, history, matches),
            training=coach.training(store),
            ranking=s.get("ranking"),
            demos=store.rows(
                "SELECT id,name,status,progress,error,updated,version,match_id FROM demos ORDER BY updated DESC"
            ),
            reports=store.rows(
                "SELECT id,title,at FROM reports ORDER BY at DESC LIMIT 300"
            ),
            jobs=store.rows("SELECT * FROM jobs ORDER BY id DESC LIMIT 12"),
            root=str(store.root),
        )

    @app.post("/api/settings")
    def options(body: Options):
        data = body.model_dump()
        u = urlsplit(body.ai_base)
        if (
            not u.hostname
            or u.username
            or u.password
            or u.query
            or u.fragment
            or not (
                u.scheme == "https"
                or u.scheme == "http"
                and u.hostname in ("localhost", "127.0.0.1", "::1")
            )
        ):
            raise ValueError("Укажите HTTPS-адрес AI или локальный HTTP-адрес")
        if body.watch and not Path(body.watch).is_dir():
            raise ValueError("Папка наблюдения не найдена")
        old = store.settings()
        if body.autostart != old["autostart"]:
            autorun(body.autostart)
        # Credentials belong to one provider. Remove before changing the destination.
        if old["ai_base"] != body.ai_base:
            vault.save("ai", "")
        store.change(data)
        if old["steam_id"] != body.steam_id:
            with store.connect() as db:
                db.execute(
                    "UPDATE demos SET status='queued',progress=0 WHERE status IN ('done','error')"
                )
            coach.refresh(store)
        engine.wake.set()
        return {"saved": True}

    @app.post("/api/key/{service}")
    def key(service: Literal["faceit", "ai"], body: Secret):
        secret = body.key.strip()
        if service == "ai" and secret:
            secret = dump({"base": store.settings()["ai_base"], "key": secret})
        vault.save(service, secret)
        if service == "faceit" and body.key.strip():
            engine.enqueue("sync")
        return {"saved": True}

    @app.post("/api/job/{kind}")
    def job(kind: Literal["sync", "ai"]):
        if kind == "sync" and not vault.file("faceit").exists():
            raise ValueError("Введите ключ FACEIT в настройках")
        engine.enqueue(kind)
        return {"queued": True}

    @app.post("/api/pause")
    def pause():
        store.change({"paused": not store.settings()["paused"]})
        engine.wake.set()
        return {"paused": store.settings()["paused"]}

    @app.get("/api/match/{mid}")
    def match(mid: str):
        r = required("SELECT detail FROM matches WHERE id=?", (mid,))
        return json.loads(r["detail"])

    @app.get("/api/lifetime")
    def lifetime():
        r = store.rows("SELECT raw FROM players LIMIT 1")
        return json.loads(r[0]["raw"]) if r else {}

    @app.get("/api/demo-stats")
    def demo_stats():
        from .demo_stats import breakdown

        return breakdown(store)

    @app.post("/api/demo")
    async def upload(request: Request, name: str):
        size = 0
        with tempfile.TemporaryFile(dir=store.root) as stream:
            async for block in request.stream():
                size += len(block)
                if size > demo.MAX_BYTES:
                    raise HTTPException(413, "Лимит файла — 2 ГиБ")
                stream.write(block)
            stream.seek(0)
            from starlette.concurrency import run_in_threadpool

            try:
                key = await run_in_threadpool(demo.ingest, store, stream, name)
            except (OSError, EOFError):
                raise ValueError("Не удалось прочитать демозапись или архив") from None
        engine.wake.set()
        return {"id": key}

    @app.post("/api/demo/{key}/retry")
    def retry(key: str):
        with store.connect() as db:
            if not db.execute(
                "UPDATE demos SET status='queued',progress=0,error=NULL WHERE id=? AND status!='running'",
                (key,),
            ).rowcount:
                raise ValueError("Файл не найден или уже анализируется")
        engine.wake.set()
        return {"queued": True}

    @app.get("/api/demo/{key}")
    def detail(key: str):
        r = required("SELECT name,summary,match_id FROM demos WHERE id=?", (key,))
        return dict(
            name=r["name"],
            match_id=r["match_id"],
            summary=json.loads(r["summary"] or "{}"),
            rounds=[
                json.loads(r["data"])
                for r in store.rows(
                    "SELECT data FROM rounds WHERE demo=? ORDER BY number", (key,)
                )
            ],
        )

    @app.get("/api/demo/{key}/round/{number}")
    def timeline(key: str, number: int):
        return [
            json.loads(r["data"])
            for r in store.rows(
                "SELECT data FROM events WHERE demo=? AND round=? ORDER BY tick",
                (key, number),
            )
        ]

    @app.post("/api/demo/{key}/link")
    def link(key: str, body: DemoLink):
        if body.match_id:
            required("SELECT id FROM matches WHERE id=?", (body.match_id,))
        required("SELECT id FROM demos WHERE id=?", (key,))
        with store.connect() as db:
            db.execute(
                "UPDATE demos SET match_id=? WHERE id=?", (body.match_id or None, key)
            )
        return {"saved": True}

    @app.post("/api/plan")
    def make(body: Plan):
        if (
            body.kind not in coach.KINDS
            or body.skill
            and body.skill not in coach.SKILLS
        ):
            raise ValueError("Неизвестный план или навык")
        return {"id": coach.plan(store, body.kind, body.skill)}

    @app.post("/api/exercise/{key}")
    def complete(key: int, body: Completion):
        required("SELECT id FROM exercises WHERE id=?", (key,))
        with store.connect() as db:
            if body.done:
                db.execute(
                    "INSERT OR REPLACE INTO completions VALUES(?,?,?)",
                    (key, now(), body.difficulty),
                )
            else:
                db.execute("DELETE FROM completions WHERE exercise=?", (key,))
        return {"done": body.done}

    @app.post("/api/diary/{key}")
    def diary(key: str, body: Diary):
        required("SELECT id FROM matches WHERE id=?", (key,))
        with store.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO diary VALUES(?,?)",
                (key, dump(body.model_dump())),
            )
        return {"saved": True}

    @app.post("/api/report")
    def new_report(body: Report):
        return {"id": reports.report(store, body.kind, body.ref)}

    @app.get("/api/report/{key}/{fmt}")
    def export(key: str, fmt: Literal["html", "pdf"]):
        row = required("SELECT * FROM reports WHERE id=?", (key,))
        if fmt == "pdf":
            return Response(reports.pdf(row), media_type="application/pdf")
        return Response(reports.markup(row), media_type="text/html")

    @app.post("/api/backup")
    def backup():
        return {"path": str(store.backup())}

    @app.post("/api/reset")
    def reset(body: Reset):
        if not store.settings()["paused"]:
            raise ValueError("Сначала приостановите анализ")
        if not engine.active.acquire(blocking=False):
            raise ValueError("Дождитесь остановки текущей задачи")
        try:
            autorun(False)
            with store.connect() as db:
                for table in (
                    "completions",
                    "exercises",
                    "plans",
                    "insights",
                    "diary",
                    "metrics",
                    "reports",
                    "jobs",
                    "watched",
                    "matches",
                    "ratings",
                    "players",
                    "demos",
                ):
                    db.execute("DELETE FROM " + table)
                db.execute(
                    "UPDATE settings SET data=?", (dump(DEFAULTS | {"paused": True}),)
                )
            for path in store.files.glob("*.dem"):
                if len(path.stem) == 64:
                    path.unlink(missing_ok=True)
            for service in ("ai", "faceit"):
                vault.save(service, "")
            engine.stable.clear()
        finally:
            engine.active.release()
        return {"deleted": True}

    app.mount("/", StaticFiles(directory=static, html=True), name="ui")
    return app
