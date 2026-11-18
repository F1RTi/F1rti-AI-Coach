import gzip
import io
import json
from pathlib import Path

import pytest

from backend.demo import ingest, parse
from backend.secrets import Vault
from backend.worker import Engine

from .conftest import STEAM


def test_header_gzip_dedup(store):
    data = b"PBDEMS2\x00" + b"synthetic-header-only"
    k = ingest(store, io.BytesIO(data), "test.dem")
    assert ingest(store, io.BytesIO(gzip.compress(data)), "test.dem.gz") == k
    assert len(store.rows("SELECT id FROM demos")) == 1
    with pytest.raises(ValueError):
        ingest(store, io.BytesIO(b"invalid"), "bad.dem")
    assert not list(store.files.glob("*.part"))


def test_real_queue_and_reanalysis(store):
    fixture = Path(".work/upstream.dem")
    if not fixture.exists():
        pytest.skip("Run tests/fetch_fixture.ps1 for upstream fixture")
    with fixture.open("rb") as f:
        key = ingest(store, f, fixture.name)
    store.change({"steam_id": STEAM})
    Engine(store, Vault(store.root)).cycle()
    row = store.rows("SELECT * FROM demos")[0]
    assert row["status"] == "done", row["error"]
    summary = json.loads(row["summary"])
    assert (summary["map"], summary["rounds"]) == ("de_mirage", 10)
    assert summary["metrics"]["kills"] == 11 and summary["events"] > 4000
    assert len(store.rows("SELECT * FROM rounds")) == 10 and summary["weapons"]
    parse(store, key, "not-in-demo")
    assert len(store.rows("SELECT * FROM events")) == summary["events"]
    assert (
        json.loads(store.rows("SELECT summary FROM demos")[0]["summary"])["metrics"]
        == {}
    )


def test_restart_recovers(store):
    key = ingest(store, io.BytesIO(b"PBDEMS2\0x"), "test.dem")
    store.change({"paused": True})
    with store.connect() as db:
        db.execute("UPDATE demos SET status='running' WHERE id=?", (key,))
        db.execute(
            "INSERT INTO jobs(kind,state,at,message) VALUES('sync','running',0,'')"
        )
    engine = Engine(store, Vault(store.root))
    engine.start()
    engine.close()
    assert store.rows("SELECT status FROM demos")[0]["status"] == "queued"
    assert store.rows("SELECT state FROM jobs")[0]["state"] == "queued"
