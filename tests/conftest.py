import httpx
import pytest

from backend.db import Store, now
from backend.faceit import FaceitClient

STEAM = "76561197964020430"


def api_fixture(request):
    path = request.url.path.split("/data/v4/")[1]
    assert request.headers["authorization"] == "Bearer test-fixture"
    profile = {
        "player_id": "fixture-player",
        "nickname": "Test Player",
        "steam_id_64": STEAM,
        "games": {"cs2": {"faceit_elo": 1655}},
    }
    if path in ("players", "players/fixture-player"):
        return httpx.Response(200, json=profile)
    if path.endswith("/stats/cs2"):
        return httpx.Response(200, json={"lifetime": {"Matches": "6"}, "segments": []})
    if path.endswith("/history"):
        assert request.url.params["game"] == "cs2"
        return httpx.Response(
            200, json={"items": [{"match_id": "fixture-" + str(i)} for i in range(6)]}
        )
    if path.startswith("matches/"):
        mid = path.split("/")[1]
        idx = int(mid.split("-")[1])
        if path.endswith("/stats"):
            p = {
                "player_id": "fixture-player",
                "player_stats": {
                    "Kills": "12",
                    "Deaths": "15",
                    "Assists": "3",
                    "ADR": str(50 + idx),
                    "Headshots": "4",
                    "MVPs": "1",
                    "Headshots %": "33",
                },
            }
            return httpx.Response(
                200,
                json={
                    "rounds": [
                        {
                            "round_stats": {"Map": "de_mirage", "Rounds": "22"},
                            "teams": [{"players": [p]}],
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "match_id": mid,
                "started_at": now() - idx * 3000 - 2400,
                "finished_at": now() - idx * 3000,
                "status": "FINISHED",
                "teams": {"faction1": {"roster": [{"player_id": "fixture-player"}]}},
                "results": {"winner": "faction1" if idx % 2 else "faction2"},
            },
        )
    return httpx.Response(404)


def fixture_client(key="test-fixture"):
    return FaceitClient(
        key, transport=httpx.MockTransport(api_fixture), sleep=lambda n: None
    )


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "db")
