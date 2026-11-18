import math
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx

from .db import dump, now


class ServiceError(Exception):
    def __init__(self, message, status=0, retry_after=0):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class FaceitClient:
    def __init__(self, key, transport=None, sleep=time.sleep):
        self.http = httpx.Client(
            base_url="https://open.faceit.com/data/v4/",
            headers={"Authorization": "Bearer " + key},
            timeout=20,
            transport=transport,
        )
        self.sleep = sleep

    def get(self, path, **params):
        messages = {
            401: "Проверьте ключ FACEIT",
            403: "FACEIT отказал в доступе",
            404: "Данные ещё недоступны",
            429: "Достигнут лимит запросов FACEIT",
        }
        for attempt in range(4):
            try:
                response = self.http.get(path, params=params)
            except httpx.RequestError:
                if attempt == 3:
                    raise ServiceError("Ошибка сети при подключении к FACEIT") from None
                self.sleep(2**attempt + random.random())
                continue
            code = response.status_code
            if code == 200:
                return response.json()
            if code == 429 or code >= 500:
                delay = response.headers.get("Retry-After", "0")
                try:
                    seconds = float(delay)
                except ValueError:
                    try:
                        seconds = (
                            parsedate_to_datetime(delay) - datetime.now(timezone.utc)
                        ).total_seconds()
                    except (TypeError, ValueError):
                        seconds = 0
                if seconds <= 90 and attempt < 3:
                    self.sleep(max(seconds, 2**attempt) + random.random())
                    continue
                raise ServiceError(
                    messages.get(code, "Ошибка сервиса FACEIT") + f" (HTTP {code})",
                    code,
                    max(0, seconds),
                )
            raise ServiceError(
                messages.get(code, "Ошибка сервиса FACEIT") + f" (HTTP {code})", code
            )

    def history(self, player, lower, upper):
        offset = 0
        while True:
            page = self.get(
                f"players/{player}/history",
                game="cs2",
                offset=offset,
                limit=100,
                **{"from": lower, "to": upper},
            ).get("items", [])
            yield from page
            if len(page) < 100:
                break
            if offset == 1000:
                end = min(m["started_at"] for m in page)
                if end >= upper:
                    raise ServiceError("FACEIT вернул повторяющуюся страницу")
                upper, offset = end, 0
            else:
                offset += len(page)


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


FIELDS = {
    "kills": "Kills",
    "deaths": "Deaths",
    "assists": "Assists",
    "adr": "ADR",
    "headshots": "Headshots",
    "hs_pct": "Headshots %",
    "mvp": "MVPs",
    "entries": "Entry Count",
    "entry_wins": "Entry Wins",
    "flash_assists": "Flash Assists",
    "utility_damage": "Utility Damage",
    "opening_deaths": "First Deaths",
    "trade_kills": "Trade Kills",
    "traded_deaths": "Traded Deaths",
    "clutches": "Clutch Attempts",
    "clutch_wins": "Clutch Wins",
    "kast": "KAST",
}


def maps_for(payload, player):
    result = []
    for index, rnd in enumerate(payload.get("rounds", [])):
        info = rnd.get("round_stats", {})
        for team in rnd.get("teams", []):
            for p in team.get("players", []):
                if p.get("player_id") == player:
                    raw = p.get("player_stats", {})
                    stats = {k: number(raw.get(label)) for k, label in FIELDS.items()}
                    stats["rounds"] = number(info.get("Rounds"))
                    result.append((index, info.get("Map"), stats))
    return result


def synchronize(store, client, check=lambda: None):
    saved = store.rows("SELECT id FROM players")
    profile = (
        client.get("players/" + quote(saved[0]["id"], safe=""))
        if saved
        else client.get("players", nickname="F1rti")
    )
    player = profile["player_id"]
    pid = quote(player, safe="")
    elo = profile.get("games", {}).get("cs2", {}).get("faceit_elo")
    lifetime = client.get(f"players/{pid}/stats/cs2")
    with store.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO players VALUES(?,?,?,?)",
            (player, profile["nickname"], profile.get("steam_id_64"), dump(lifetime)),
        )
        if isinstance(elo, int):
            db.execute("INSERT OR REPLACE INTO ratings VALUES(?,?)", (now(), elo))
    # A failed first import must resume all the way back, even after partial commits.
    lower = store.settings().get("history_cursor", 0)
    upper = now()
    pending = {r["id"] for r in store.rows("SELECT id FROM matches WHERE complete=0")}
    known = {r["id"] for r in store.rows("SELECT id FROM matches WHERE complete=1")}
    seen = set()
    count = 0

    def save(mid, history):
        nonlocal count
        check()
        path = "matches/" + quote(mid, safe="")
        detail = client.get(path)
        if detail.get("status") != "FINISHED":
            return
        try:
            maps = maps_for(client.get(path + "/stats"), player)
        except ServiceError as exc:
            if exc.status != 404:
                raise
            maps = []
        winner = detail.get("results", {}).get("winner")
        team = next(
            (
                name
                for name, t in detail.get("teams", {}).items()
                if any(p.get("player_id") == player for p in t.get("roster", []))
            ),
            None,
        )
        start = detail.get("started_at") or history.get("started_at")
        end = detail.get("finished_at") or history.get("finished_at")
        with store.connect() as db:
            db.execute(
                """INSERT INTO matches VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                       started=excluded.started,finished=excluded.finished,won=excluded.won,
                       detail=excluded.detail,complete=excluded.complete""",
                (
                    mid,
                    start,
                    end,
                    int(winner == team) if team and winner else None,
                    dump(detail),
                    int(bool(maps)),
                ),
            )
            db.execute("DELETE FROM stats WHERE match_id=?", (mid,))
            db.executemany(
                "INSERT INTO stats VALUES(?,?,?,?)",
                [(mid, i, name, dump(s)) for i, name, s in maps],
            )
        count += 1
        client.sleep(0.12)

    for item in client.history(pid, max(0, lower - 86400), upper):
        mid = item["match_id"]
        if mid not in known and mid not in seen:
            save(mid, item)
        seen.add(mid)
    for mid in sorted(pending - seen):
        save(mid, {})
    store.change({"history_cursor": upper})
    return count
