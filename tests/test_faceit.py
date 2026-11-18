import httpx
import pytest

from backend.faceit import FaceitClient, ServiceError, synchronize

from .conftest import api_fixture


def test_sync_idempotent(store):
    log = []

    def transport(r):
        log.append(r.url.path)
        return api_fixture(r)

    client = FaceitClient(
        "test-fixture", httpx.MockTransport(transport), lambda _: None
    )
    assert synchronize(store, client) == 6
    log.clear()
    assert synchronize(store, client) == 0
    assert len(store.matches()) == 6
    assert not any("/matches/" in p for p in log)
    assert store.rows("SELECT elo FROM ratings")[0]["elo"] == 1655
    assert store.matches()[0]["maps"][0]["kills"] == 12


@pytest.mark.parametrize(
    "status,attempts", [(401, 1), (403, 1), (404, 1), (429, 4), (503, 4)]
)
def test_errors(status, attempts):
    calls = []

    def transport(r):
        calls.append(r)
        return httpx.Response(status, headers={"Retry-After": "2"})

    sleeps = []
    with pytest.raises(ServiceError) as exc:
        FaceitClient("unlogged", httpx.MockTransport(transport), sleeps.append).get(
            "players"
        )
    assert (
        exc.value.status == status
        and len(calls) == attempts
        and len(sleeps) == attempts - 1
    )
    assert "unlogged" not in str(exc.value)


def test_page_boundary():
    offsets = []

    def get(r):
        offset = int(r.url.params["offset"])
        offsets.append(offset)
        return httpx.Response(
            200,
            json={
                "items": [
                    {"match_id": str(i)} for i in range(offset, min(offset + 100, 103))
                ]
            },
        )

    assert (
        len(list(FaceitClient("x", httpx.MockTransport(get)).history("test", 0, 500)))
        == 103
    )
    assert offsets == [0, 100]


def test_partial_stats_are_retried(store):
    missing = True

    def get(r):
        if missing and r.url.path.endswith("/fixture-2/stats"):
            return httpx.Response(404)
        return api_fixture(r)

    cli = FaceitClient("test-fixture", httpx.MockTransport(get), lambda _: None)
    synchronize(store, cli)
    assert sum(m["complete"] for m in store.matches()) == 5
    missing = False
    assert synchronize(store, cli) == 1
    assert sum(m["complete"] for m in store.matches()) == 6
