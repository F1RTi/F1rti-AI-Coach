import json
from pathlib import Path

from backend import analytics, coach
from backend.db import now
from backend.demo import summarize_round
from backend.faceit import synchronize
from backend.secrets import Vault
from backend.worker import Engine

from .conftest import fixture_client


def test_public_round_fixture():
    d = json.loads(Path("tests/fixtures/mirage_round.json").read_text(encoding="utf-8"))
    r = summarize_round(d["events"], d["roster"], "p7", 1)
    assert r["metrics"]["opening_kills"] == 1 and r["metrics"]["traded_deaths"] == 1
    assert r["winner"] == "T" and r["metrics"]["damage"] == 100


def test_training_evaluation_waits_for_future_games(store):
    synchronize(store, fixture_client())
    result = coach.refresh(store)
    coach.plan(store, "День")
    exercise = coach.training(store)["exercises"][0]
    with store.connect() as db:
        db.execute("INSERT INTO completions VALUES(?,?,?)", (exercise["id"], now(), 3))
    _, history = coach.advice(store)
    ev = coach.evaluations(store, history, store.matches())[0]
    assert not ev["ready"] and ev["sample"] == 0
    future = [
        dict(
            id=str(i),
            started=now() + 100,
            finished=now() + 300,
            won=1,
            maps=[{"map": "map", "adr": 70}],
        )
        for i in range(10)
    ]
    ev = coach.evaluations(store, history, future)[0]
    assert ev["ready"] and ev["current"] == 0 and ev["before"] == 100 and result


def test_session_rating_coverage():
    games = [
        dict(id="a", started=100, finished=200, won=1, maps=[]),
        dict(id="b", started=8000, finished=8100, won=1, maps=[]),
    ]
    ratings = [dict(at=50, elo=900), dict(at=220, elo=925)]
    groups = analytics.sessions(games, 10, ratings)
    assert groups[0]["elo_delta"] is None and groups[1]["elo_delta"] == 25
    ratings[-1]["at"] = 9000
    assert all(g["elo_delta"] is None for g in analytics.sessions(games, 10, ratings))


def test_watcher_stable_and_duplicate(store, tmp_path):
    w = tmp_path / "watch"
    w.mkdir()
    (w / "tiny.dem").write_bytes(b"PBDEMS2\x00header")
    engine = Engine(store, Vault(store.root))
    engine.watch(w)
    assert not store.rows("SELECT * FROM demos")
    engine.watch(w)
    engine.watch(w)
    assert len(store.rows("SELECT * FROM demos")) == 1
