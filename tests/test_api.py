import json

from fastapi.testclient import TestClient

from backend.api import create
from backend.db import Store
from backend.secrets import Vault
from backend.worker import Engine

from .conftest import fixture_client


def test_full_local_workflow(store, monkeypatch):
    monkeypatch.setattr("backend.worker.FaceitClient", fixture_client)
    vault = Vault(store.root)
    engine = Engine(store, vault)
    app = create(store, vault, engine, "fixture-token", "testserver", "frontend/dist")
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/state").status_code == 401
        client.headers["x-coach-token"] = "fixture-token"
        assert (
            client.get("/api/state", headers={"host": "external.invalid"}).status_code
            == 403
        )
        assert (
            client.post(
                "/api/pause", headers={"Origin": "https://external.invalid"}
            ).status_code
            == 403
        )
        assert client.get("/api/state").json()["goal"]["current"] is None
        assert client.post("/api/key/faceit", json={"key": "test-fixture"}).json()[
            "saved"
        ]
        engine.cycle()
        s = client.get("/api/state").json()
        assert s["goal"]["current"] == 1655 and len(s["matches"]) == 6
        assert "test-fixture" not in json.dumps(s)
        assert client.get("/api/match/fixture-0").json()["status"] == "FINISHED"
        assert (
            client.post("/api/demo?name=invalid.dem", content=b"invalid").status_code
            == 400
        )
        demo = client.post(
            "/api/demo?name=synthetic.dem", content=b"PBDEMS2\0test"
        ).json()["id"]
        assert client.post(
            "/api/demo/" + demo + "/link", json={"match_id": "fixture-0"}
        ).json()["saved"]
        assert client.get("/api/demo/" + demo).json()["match_id"] == "fixture-0"
        key = client.post(
            "/api/report", json={"kind": "Матч", "ref": "fixture-0"}
        ).json()["id"]
        assert "fixture-0" in client.get("/api/report/" + key + "/html").text
        assert (
            client.post(
                "/api/plan", json={"kind": "Перед сессией", "skill": "Aim"}
            ).status_code
            == 200
        )
        tasks = client.get("/api/state").json()["training"]["exercises"]
        assert not any(t["completed"] for t in tasks)
        assert (
            client.post(
                "/api/exercise/" + str(tasks[0]["id"]),
                json={"done": True, "difficulty": 4},
            ).status_code
            == 200
        )
        sid = s["sessions"][0]["id"]
        assert (
            client.post(
                "/api/diary/" + sid, json={"focus": 4, "note": "test"}
            ).status_code
            == 200
        )
        assert Store(store.root).matches()
        assert client.post("/api/reset", json={"confirm": "УДАЛИТЬ"}).status_code == 400
        client.post("/api/pause")
        assert client.post("/api/reset", json={"confirm": "УДАЛИТЬ"}).status_code == 200
        assert not store.matches() and not vault.file("faceit").exists()
