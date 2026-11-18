"""Local SQLite repository. Schema migrations run in a single transaction."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DEFAULTS = dict(
    sync_minutes=30,
    session_gap=90,
    minutes=25,
    watch="",
    steam_id="",
    paused=False,
    notifications=True,
    ai_base="https://api.openai.com/v1",
    model="gpt-4o-mini",
    autostart=False,
)

SCHEMA = """
CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
CREATE TABLE players (id TEXT PRIMARY KEY, nickname TEXT, steam TEXT, raw TEXT);
CREATE TABLE ratings (at INTEGER PRIMARY KEY, elo INTEGER NOT NULL);
CREATE TABLE matches (id TEXT PRIMARY KEY, started INTEGER, finished INTEGER, won INTEGER,
    detail TEXT NOT NULL, complete INTEGER DEFAULT 0);
CREATE INDEX match_history ON matches(finished DESC);
CREATE TABLE stats (match_id TEXT REFERENCES matches ON DELETE CASCADE, map_no INTEGER,
    map TEXT, data TEXT NOT NULL, PRIMARY KEY(match_id,map_no));
CREATE TABLE demos (id TEXT PRIMARY KEY, name TEXT, status TEXT, progress INTEGER,
    error TEXT, updated INTEGER, summary TEXT, version TEXT);
CREATE TABLE rounds (demo TEXT REFERENCES demos ON DELETE CASCADE, number INTEGER,
    data TEXT, PRIMARY KEY(demo,number));
CREATE TABLE events (demo TEXT, round INTEGER, tick INTEGER, kind TEXT, data TEXT,
    FOREIGN KEY(demo,round) REFERENCES rounds(demo,number) ON DELETE CASCADE);
CREATE INDEX event_lookup ON events(demo,round,tick);
CREATE TABLE metrics (period INTEGER, name TEXT, data TEXT, PRIMARY KEY(period,name));
CREATE TABLE insights (id TEXT PRIMARY KEY, at INTEGER, data TEXT);
CREATE TABLE plans (id INTEGER PRIMARY KEY, day TEXT, kind TEXT, data TEXT, UNIQUE(day,kind));
CREATE TABLE exercises (id INTEGER PRIMARY KEY AUTOINCREMENT, plan INTEGER REFERENCES plans ON DELETE CASCADE,
    day TEXT, skill TEXT, instruction TEXT, minutes INTEGER);
CREATE TABLE completions (exercise INTEGER PRIMARY KEY REFERENCES exercises ON DELETE CASCADE,
    at INTEGER, difficulty INTEGER);
CREATE TABLE diary (session_id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE reports (id TEXT PRIMARY KEY, title TEXT, at INTEGER, data TEXT);
CREATE TABLE jobs (id INTEGER PRIMARY KEY, kind TEXT, state TEXT, at INTEGER, message TEXT);
CREATE TABLE watched (path TEXT PRIMARY KEY, signature TEXT);
"""


def now():
    return int(time.time())


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.files = self.root / "demos"
        self.files.mkdir(exist_ok=True)
        self.path = self.root / "coach.sqlite"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
                db.execute("INSERT INTO settings VALUES(1,?)", (dump(DEFAULTS),))
                db.execute("PRAGMA user_version=1")
            elif version > 2:
                raise RuntimeError("Неизвестная версия базы данных")
            if version < 2:
                db.execute(
                    "ALTER TABLE demos ADD COLUMN match_id TEXT REFERENCES matches(id) ON DELETE SET NULL"
                )
                db.execute("PRAGMA user_version=2")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def settings(self):
        return DEFAULTS | json.loads(self.rows("SELECT data FROM settings")[0]["data"])

    def change(self, changes):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            settings = json.loads(db.execute("SELECT data FROM settings").fetchone()[0])
            db.execute("UPDATE settings SET data=?", (dump(settings | changes),))

    def matches(self):
        rows = self.rows(
            "SELECT id,started,finished,won,complete FROM matches ORDER BY finished DESC,id"
        )
        by_id = {m["id"]: m for m in rows}
        for m in rows:
            m["maps"] = []
        for r in self.rows("SELECT * FROM stats ORDER BY map_no"):
            by_id[r["match_id"]]["maps"].append(
                {"map": r["map"], **json.loads(r["data"])}
            )
        return rows

    def backup(self):
        from uuid import uuid4

        path = self.root / ("backup-" + str(now()) + "-" + uuid4().hex[:6] + ".sqlite")
        with self.connect() as db:
            target = sqlite3.connect(path)
            try:
                db.backup(target)
            finally:
                target.close()
        return path
