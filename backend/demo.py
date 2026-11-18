import bisect
import gzip
import hashlib
import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from .db import dump, now

VERSION = "demo-1.2"
MAX_BYTES = 2 * 1024**3
EVENTS = {
    "round_start",
    "round_freeze_end",
    "round_end",
    "round_announce_match_start",
    "player_death",
    "player_hurt",
    "player_blind",
    "weapon_fire",
    "grenade_thrown",
    "flashbang_detonate",
    "smokegrenade_detonate",
    "hegrenade_detonate",
    "inferno_startburn",
    "inferno_expire",
    "smokegrenade_expired",
    "bomb_planted",
    "bomb_defused",
    "bomb_exploded",
    "bomb_beginplant",
    "bomb_begindefuse",
    "item_equip",
}
UTILITY = {"hegrenade", "inferno", "molotov", "incgrenade"}
SIDES = {2: "T", 3: "CT"}


def ingest(store, stream, name):
    name = Path(name).name
    if not name.lower().endswith((".dem", ".dem.gz")):
        raise ValueError("Выберите .dem или .dem.gz")
    digest = hashlib.sha256()
    path = None
    source = gzip.GzipFile(fileobj=stream) if name.lower().endswith(".gz") else stream
    try:
        with tempfile.NamedTemporaryFile(
            dir=store.files, suffix=".part", delete=False
        ) as out:
            path = Path(out.name)
            size = 0
            while block := source.read(1024**2):
                if not size and block[:8] != b"PBDEMS2\0":
                    raise ValueError("Файл не содержит заголовок Source 2")
                size += len(block)
                if size > MAX_BYTES:
                    raise ValueError("Лимит одной демозаписи — 2 ГиБ")
                digest.update(block)
                out.write(block)
        if not size:
            raise ValueError("Пустой файл")
        key = digest.hexdigest()
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            target = store.files / (key + ".dem")
            if not target.exists():
                path.replace(target)
            db.execute(
                "INSERT OR IGNORE INTO demos(id,name,status,progress,error,updated,summary,version) VALUES(?,?,'queued',0,NULL,?,NULL,?)",
                (key, name, now(), VERSION),
            )
        return key
    finally:
        if source is not stream:
            source.close()
        if path:
            path.unlink(missing_ok=True)


def records(frame):
    # Converting via pandas JSON also normalizes nulls and NumPy scalars.
    for col in frame.columns:
        if col == "steamid" or col.endswith("_steamid"):
            frame[col] = frame[col].astype("string")
    return json.loads(frame.to_json(orient="records", double_precision=6))


def enemy(e):
    a, b = e.get("attacker_team_num"), e.get("user_team_num")
    return a in SIDES and b in SIDES and a != b


def point(row, prefix=""):
    values = [row.get(prefix + a) for a in "XYZ"]
    return values if None not in values else None


def positioning(events, frames, player):
    observations = []
    for death in (
        e
        for e in events
        if e["kind"] == "player_death" and e.get("user_steamid") == player and enemy(e)
    ):
        tick = death["tick"]
        pos = point(death, "user_")
        state = frames.get(tick, [])
        if not pos:
            continue
        friends = [
            point(p)
            for p in state
            if p["steamid"] != player
            and p.get("team_num") == death["user_team_num"]
            and (p.get("health") or 0) > 0
            and point(p)
        ]
        if friends:
            nearest = round(min(math.dist(pos, p) for p in friends))
            if nearest >= 900:
                observations.append(
                    dict(
                        tick=tick,
                        label=f"Ближайший живой союзник в {nearest} ед. Возможна изолированная дуэль.",
                    )
                )
                old = next(
                    (
                        p
                        for p in frames.get(max(0, tick - 256), [])
                        if p["steamid"] == player
                    ),
                    {},
                )
                before = point(old)
                if before and math.dist(before, pos) >= 500:
                    observations.append(
                        dict(
                            tick=tick,
                            label="Смещение от 500 ед. за 256 тиков до смерти вдали от союзников. Проверьте поддержку выхода.",
                        )
                    )
        opponent = death.get("attacker_steamid")
        contacts = [
            e
            for e in events
            if e["kind"] == "player_hurt"
            and 48 < tick - e["tick"] <= 384
            and {player, opponent} == {e.get("user_steamid"), e.get("attacker_steamid")}
        ]
        for contact in contacts:
            prev = point(
                contact,
                "user_" if contact.get("user_steamid") == player else "attacker_",
            )
            if prev and math.dist(pos, prev) < 220:
                observations.append(
                    dict(
                        tick=tick,
                        label="Повторный контакт с тем же соперником рядом с предыдущей позицией. Проверьте повторный пик.",
                    )
                )
                break
        bomb = next(
            (e for e in events if e["kind"] == "bomb_planted" and e["tick"] < tick),
            None,
        )
        if bomb and death["user_team_num"] == 3:
            old = next(
                (p for p in frames.get(bomb["tick"], []) if p["steamid"] == player), {}
            )
            initial = point(old)
            if initial and math.dist(initial, pos) > 1200:
                observations.append(
                    dict(
                        tick=tick,
                        label="Смерть CT после перемещения более 1200 ед. от позиции в момент установки. Проверьте маршрут ротации.",
                    )
                )
    return observations


def summarize_round(events, roster, player, number):
    kills = [e for e in events if e["kind"] == "player_death" and enemy(e)]
    victims = [e for e in kills if e.get("user_steamid") == player]
    frags = [e for e in kills if e.get("attacker_steamid") == player]
    hurts = [
        e
        for e in events
        if e["kind"] == "player_hurt"
        and enemy(e)
        and e.get("attacker_steamid") == player
    ]
    assists = [e for e in kills if e.get("assister_steamid") == player]
    me = next((p for p in roster if p.get("steamid") == player), {})
    team = me.get("team_num")
    winner = next((e.get("winner") for e in events if e["kind"] == "round_end"), None)
    first = kills[0] if kills else {}
    metrics = Counter()
    facts = []

    def fact(e, label):
        facts.append(dict(tick=e["tick"], round=number, label=label))

    def is_trade(older, newer):
        return (
            0 <= newer["tick"] - older["tick"] <= 320
            and older.get("attacker_steamid") == newer.get("user_steamid")
            and older.get("user_team_num") == newer.get("attacker_team_num")
        )

    metrics.update(
        kills=len(frags),
        deaths=len(victims),
        assists=len(assists),
        opening_deaths=int(first.get("user_steamid") == player) if player else 0,
        opening_kills=int(first.get("attacker_steamid") == player) if player else 0,
        damage=sum(e.get("dmg_health") or 0 for e in hurts),
        utility_damage=sum(
            e.get("dmg_health") or 0 for e in hurts if e.get("weapon") in UTILITY
        ),
        flash_assists=sum(bool(e.get("assistedflash")) for e in assists),
    )
    alive = {p["steamid"]: p["team_num"] for p in roster if p.get("team_num") in SIDES}
    if player and first.get("user_steamid") == player:
        fact(first, "Первая смерть раунда")
    clutch = False
    for e in (e for e in events if e["kind"] == "player_death"):
        victim = e.get("user_steamid")
        if victim == player and player in alive:
            counts = Counter(alive.values())
            if counts[team] > counts[5 - team]:
                fact(e, "Смерть при численном преимуществе")
                metrics["advantage_deaths"] += 1
        alive.pop(victim, None)
        if (
            player in alive
            and team in SIDES
            and list(alive.values()).count(team) == 1
            and 5 - team in alive.values()
        ):
            clutch = True
    if me and winner in SIDES:
        metrics.update(clutches=int(clutch), clutch_wins=int(clutch and winner == team))
    for i, e in enumerate(kills):
        if e in victims:
            if any(is_trade(e, n) for n in kills[i + 1 :]):
                metrics["traded_deaths"] += 1
            else:
                fact(e, "Смерть без ответного убийства за 320 тиков")
        if e in frags and any(is_trade(o, e) for o in kills[:i]):
            metrics["trade_kills"] += 1
            fact(e, "Размен союзника")
    if me and winner in SIDES:
        metrics["kast_round"] = int(
            bool(frags or assists or player in alive or metrics["traded_deaths"])
        )
    duels = []
    for e in frags + victims:
        target = e["user_steamid"] if e in frags else e["attacker_steamid"]
        hits = [
            h for h in hurts if h["user_steamid"] == target and h["tick"] <= e["tick"]
        ]
        coords = [
            e.get(f"{who}_{axis}") for who in ("user", "attacker") for axis in "XYZ"
        ]
        distance = (
            round(math.dist(coords[:3], coords[3:])) if None not in coords else None
        )
        duels.append(
            dict(
                tick=e["tick"],
                weapon=e.get("weapon"),
                won=e in frags,
                distance=distance,
                hits=len(hits),
                first_hit_ticks=e["tick"] - hits[0]["tick"] if hits else None,
            )
        )
    return dict(
        number=number,
        start=events[0]["tick"],
        end=events[-1]["tick"],
        side=SIDES.get(team),
        winner=SIDES.get(winner),
        roster=roster,
        metrics=dict(metrics) if me else {},
        facts=facts if me else [],
        duels=duels if me else [],
    )


def parse(store, key, player):
    # Imported inside the isolated worker so the desktop starts without loading native analytics libraries.
    os.environ.setdefault("RAYON_NUM_THREADS", "2")
    os.environ.setdefault("POLARS_MAX_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    from demoparser2 import DemoParser

    parser = DemoParser(str(store.files / (key + ".dem")))

    def progress(n):
        with store.connect() as db:
            db.execute("UPDATE demos SET progress=? WHERE id=?", (n, key))

    header = parser.parse_header()
    supported = set(parser.list_game_events())
    progress(10)
    wanted = sorted(supported & EVENTS)
    if not {"round_start", "round_end"}.issubset(wanted):
        raise ValueError("В демозаписи нет полных границ раундов")
    raw = parser.parse_events(
        wanted, player=["team_num", "X", "Y", "Z"], other=["total_rounds_played"]
    )
    events = sorted(
        (row | {"kind": kind} for kind, frame in raw for row in records(frame)),
        key=lambda row: row["tick"],
    )
    progress(55)
    starts = sorted({e["tick"] for e in events if e["kind"] == "round_start"})
    groups = defaultdict(list)
    for e in events:
        ix = bisect.bisect_right(starts, e["tick"]) - 1
        if ix >= 0:
            groups[ix].append(e)
    complete = []
    for group in groups.values():
        end = next((e for e in group if e["kind"] == "round_end"), None)
        if end and end.get("winner") in SIDES:
            complete.append([e for e in group if e["tick"] <= end["tick"]])
    if not complete:
        raise ValueError("Не найдено завершённых раундов")
    # Following a restart, keep the last sequence of official round numbers.
    live = []
    for group in complete:
        end = next(e for e in group if e["kind"] == "round_end")
        number = int(end["total_rounds_played"]) + 1
        if live and number <= live[-1][0]:
            live = []
        live.append((number, group))
    ticks = [
        next(
            (e["tick"] for e in group if e["kind"] == "round_freeze_end"),
            group[0]["tick"],
        )
        for _, group in live
    ]
    rosters = defaultdict(list)
    samples = set(ticks)
    for _, group in live:
        for e in group:
            if (
                player
                and e["kind"] == "player_death"
                and e.get("user_steamid") == player
            ):
                samples.update([e["tick"], max(0, e["tick"] - 256)])
            elif e["kind"] == "bomb_planted":
                samples.add(e["tick"])
    for row in records(
        parser.parse_ticks(
            ["team_num", "health", "current_equip_value", "balance", "X", "Y", "Z"],
            ticks=sorted(samples),
        )
    ):
        rosters[row["tick"]].append(row)
    players = {
        p["steamid"]: p["name"]
        for roster in rosters.values()
        for p in roster
        if p.get("steamid")
    }
    selected = player if player in players else ""
    totals, weapons, sides, zones = (
        Counter(),
        defaultdict(Counter),
        defaultdict(Counter),
        Counter(),
    )
    facts, grenades, distances = [], [], defaultdict(Counter)
    utility = defaultdict(Counter)
    progress(80)
    with store.connect() as db:
        db.execute("DELETE FROM rounds WHERE demo=?", (key,))
        for (num, group), tick in zip(live, ticks):
            rnd = summarize_round(group, rosters[tick], selected, num)
            rnd["hypotheses"] = (
                positioning(group, rosters, selected) if selected else []
            )
            totals.update(rnd["metrics"])
            if rnd["side"]:
                sides[rnd["side"]].update(
                    rounds=1, wins=int(rnd["side"] == rnd["winner"]), **rnd["metrics"]
                )
            facts.extend(rnd["facts"])
            for d in rnd["duels"]:
                if d["distance"] is not None:
                    bucket = (
                        "<500"
                        if d["distance"] < 500
                        else "500–1500"
                        if d["distance"] < 1500
                        else "1500+"
                    )
                    distances[bucket].update(duels=1, kills=int(d["won"]))
            for e in group:
                weapon = (e.get("weapon") or "").removeprefix("weapon_")
                if selected:
                    if (
                        weapon
                        and e["kind"] == "weapon_fire"
                        and e.get("user_steamid") == selected
                    ):
                        weapons[weapon]["shots"] += 1
                    if weapon and e.get("attacker_steamid") == selected and enemy(e):
                        if e["kind"] == "player_death":
                            weapons[weapon]["kills"] += 1
                        elif e["kind"] == "player_hurt":
                            weapons[weapon]["hits"] += 1
                            weapons[weapon]["damage"] += e.get("dmg_health") or 0
                    if (
                        e["kind"] == "player_hurt"
                        and enemy(e)
                        and e.get("attacker_steamid") == selected
                        and e.get("weapon") in UTILITY
                    ):
                        utility[e["weapon"]]["damage"] += e.get("dmg_health") or 0
                    if (
                        e["kind"] == "player_blind"
                        and enemy(e)
                        and e.get("attacker_steamid") == selected
                    ):
                        utility["flashbang"]["blinds"] += 1
                        if e.get("blind_duration") is not None:
                            utility["flashbang"]["blind_seconds"] += round(
                                e["blind_duration"], 2
                            )
                    if (
                        e["kind"] == "player_death"
                        and enemy(e)
                        and e.get("assister_steamid") == selected
                        and e.get("assistedflash")
                    ):
                        utility["flashbang"]["assists"] += 1
                if not selected or e.get("user_steamid") != selected:
                    continue
                if (
                    e["kind"] == "player_death"
                    and e.get("user_X") is not None
                    and e.get("user_Y") is not None
                ):
                    zones[
                        f"{int(e['user_X'] // 256) * 256}, {int(e['user_Y'] // 256) * 256}"
                    ] += 1
                if (
                    e["kind"] in ("grenade_thrown", "weapon_fire")
                    and weapon in UTILITY | {"flashbang", "smokegrenade"}
                    or e["kind"].endswith("_detonate")
                    or e["kind"] == "inferno_startburn"
                ):
                    grenades.append(
                        dict(
                            round=num,
                            tick=e["tick"],
                            event=e["kind"],
                            weapon=e.get("weapon"),
                            position=[e.get("x"), e.get("y"), e.get("z")]
                            if e["kind"].endswith("_detonate")
                            or e["kind"] == "inferno_startburn"
                            else [e.get("user_" + a) for a in "XYZ"],
                        )
                    )
            db.execute("INSERT INTO rounds VALUES(?,?,?)", (key, num, dump(rnd)))
            db.executemany(
                "INSERT INTO events VALUES(?,?,?,?,?)",
                [(key, num, e["tick"], e["kind"], dump(e)) for e in group],
            )
        summary = dict(
            map=header.get("map_name"),
            player=selected,
            players=players,
            rounds=len(live),
            events=sum(len(g) for _, g in live),
            supported=wanted,
            metrics=dict(totals) if selected else {},
            weapons=weapons,
            sides=sides,
            facts=facts,
            grenades=grenades,
            utility=utility,
            distances=distances,
            repeated_zones={k: v for k, v in zones.items() if v >= 2},
            version=VERSION,
        )
        if selected:
            played = sum(s["rounds"] for s in sides.values())
            for key_name, num, den in (
                ("kast", totals["kast_round"], played),
                (
                    "entry_success",
                    totals["opening_kills"],
                    totals["opening_kills"] + totals["opening_deaths"],
                ),
                ("clutch_success", totals["clutch_wins"], totals["clutches"]),
            ):
                summary["metrics"][key_name] = (
                    round(100 * num / den, 2) if den else None
                )
            for m in sides.values():
                m["winrate"] = round(100 * m["wins"] / m["rounds"], 2)
        summary["metric_records"] = {
            k: dict(
                value=v,
                period=len(live),
                source="CS2 demo",
                updated=now(),
                available=v is not None,
                method={
                    "kast": "100 × раунды K/A/S/T / сыгранные раунды",
                    "entry_success": "100 × первые убийства / первые дуэли",
                    "clutch_success": "100 × выигранные клатчи / попытки",
                    "damage": "Сумма dmg_health по соперникам",
                    "utility_damage": "Сумма урона HE и огнём по соперникам",
                }.get(k, "Подсчёт событий по SteamID в завершённых раундах"),
            )
            for k, v in summary["metrics"].items()
        }
        db.execute(
            "UPDATE demos SET summary=?,status='done',progress=100,error=NULL,updated=?,version=? WHERE id=?",
            (dump(summary), now(), VERSION, key),
        )
