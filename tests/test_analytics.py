import httpx
import pytest

from backend import analytics, coach, reports
from backend.db import now
from backend.faceit import ServiceError, synchronize

from .conftest import fixture_client


def test_missing_and_pooled():
    def m(k, d, r, adr, w):
        return {"won": w, "maps": [dict(kills=k, deaths=d, rounds=r, adr=adr)]}

    a = analytics.summarize(
        [m(12, 0, 10, 60, 1), m(6, 9, 20, 90, 0), m(15, None, None, None, None)]
    )
    assert a["kd"]["value"] == 2
    assert a["adr"]["value"] == 80 and a["kr"]["value"] == 0.6
    assert a["winrate"]["value"] == 50 and a["hs"]["value"] is None
    assert a["kills"]["value"] == 33
    assert analytics.summarize([])["winrate"]["available"] is False
    delta = analytics.compare(a, analytics.summarize([m(10, 10, 20, 60, 0)]))
    assert delta["kd"] == 1 and delta["hs"] is None


def test_goal():
    stamp = 100 * 86400
    rows = [dict(at=stamp - 8 * 86400, elo=1800), dict(at=stamp, elo=1900)]
    g = analytics.goal(rows, stamp)
    assert (g["week"], g["month"], g["remaining"], g["next"]) == (100, None, 1100, 2000)
    assert analytics.goal([])["current"] is None


def test_evidence_plan_and_report(store):
    assert not coach.refresh(store)
    with pytest.raises(ValueError):
        coach.plan(store, "День")
    synchronize(store, fixture_client())
    current = coach.refresh(store)
    assert current[0]["sample"] == len(current[0]["evidence"]) == 6
    pid = coach.plan(store, "Неделя")
    assert coach.plan(store, "Неделя") == pid
    result = coach.training(store)
    assert len(result["exercises"]) == 7 and result["progress"] == 0
    ex = result["exercises"][0]["id"]
    with store.connect() as db:
        db.execute("INSERT INTO completions VALUES(?,?,?)", (ex, now(), 4))
    coach.plan(store, "Неделя", adapt=True)
    assert coach.training(store)["progress"] == 14.29
    key = reports.report(store, "Сессия")
    doc = reports.markup(store.rows("SELECT * FROM reports WHERE id=?", (key,))[0])
    assert "fixture-2" in doc and "52.5" in doc and "FACEIT" in doc


def test_ai_rejects_unobserved_evidence(store):
    synchronize(store, fixture_client())
    items = coach.refresh(store)

    def provider(ids):
        return coach.CompatibleProvider(
            "https://test.invalid",
            "test",
            "model",
            httpx.MockTransport(
                lambda r: httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": '{"ids":' + ids + "}"}}]},
                )
            ),
        )

    with pytest.raises(ServiceError):
        coach.refresh(store, provider('["invented"]'))
    assert coach.advice(store)[0][0]["id"] == items[0]["id"]
    import json

    assert coach.refresh(store, provider(json.dumps([i["id"] for i in items])))


def test_sessions_gap():
    games = [
        dict(id=str(n), started=start, finished=start + 20, won=1, maps=[])
        for n, start in enumerate((100, 150, 10000))
    ]
    assert [len(s["matches"]) for s in analytics.sessions(games, 5)] == [1, 2]
