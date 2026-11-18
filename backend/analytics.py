from collections import defaultdict
from statistics import mean, pstdev

from .db import dump, now

WINDOWS = (5, 10, 20, 50, 100)


def ratio(a, b, scale=1):
    return round(a / b * scale, 2) if b else None


def summarize(matches):
    maps = [m for game in matches for m in game["maps"]]
    out = {}

    def add(key, val, method, n):
        out[key] = dict(
            value=val,
            method=method,
            sample=n,
            available=val is not None,
            source="FACEIT",
            period=len(matches),
            updated=now(),
        )

    def paired(key, a, b, scale=1):
        pairs = [
            (m[a], m[b]) for m in maps if m.get(a) is not None and m.get(b) is not None
        ]
        add(
            key,
            ratio(sum(x for x, _ in pairs), sum(y for _, y in pairs), scale),
            f"Σ {a} / Σ {b}",
            len(pairs),
        )

    outcomes = [g["won"] for g in matches if g["won"] is not None]
    add(
        "winrate",
        ratio(sum(outcomes), len(outcomes), 100),
        "Победы / матчи с результатом, %",
        len(outcomes),
    )
    for key in (
        "kills",
        "deaths",
        "assists",
        "mvp",
        "entries",
        "opening_deaths",
        "trade_kills",
        "traded_deaths",
        "flash_assists",
        "utility_damage",
        "clutches",
    ):
        values = [m[key] for m in maps if m.get(key) is not None]
        add(
            key,
            sum(values) if values else None,
            "Сумма по доступным картам",
            len(values),
        )
    paired("kd", "kills", "deaths")
    paired("kr", "kills", "rounds")
    paired("hs", "headshots", "kills", 100)
    if out["hs"]["value"] is None:
        values = [m["hs_pct"] for m in maps if m.get("hs_pct") is not None]
        add(
            "hs",
            round(mean(values), 2) if values else None,
            "Средний Headshots % по картам",
            len(values),
        )
    paired("entry_success", "entry_wins", "entries", 100)
    paired("clutch_success", "clutch_wins", "clutches", 100)
    for key in ("adr", "kast"):
        pairs = [
            (m[key], m["rounds"])
            for m in maps
            if m.get(key) is not None and m.get("rounds")
        ]
        add(
            key,
            ratio(sum(x * r for x, r in pairs), sum(r for _, r in pairs)),
            "Среднее, взвешенное по раундам",
            len(pairs),
        )
    adrs = [m["adr"] for m in maps if m.get("adr") is not None]
    add(
        "variability",
        round(pstdev(adrs), 2) if len(adrs) >= 2 else None,
        "Стандартное отклонение ADR карт",
        len(adrs),
    )
    streak = 0
    for m in matches:
        if m["won"] is None or m["won"] != matches[0]["won"]:
            break
        streak += 1
    add(
        "streak",
        streak * (1 if matches[0]["won"] else -1) if streak else None,
        "Текущая серия (+ победы, − поражения)",
        streak,
    )
    return out


def compare(current, previous):
    return {
        k: round(m["value"] - previous[k]["value"], 2)
        if m["available"] and previous[k]["available"]
        else None
        for k, m in current.items()
    }


def goal(rows, at=None):
    at = at or now()
    current = rows[-1]["elo"] if rows else None

    def delta(days):
        baseline = next(
            (r for r in reversed(rows) if r["at"] <= at - days * 86400), None
        )
        return (
            current - baseline["elo"]
            if baseline and rows[-1]["at"] > at - days * 86400
            else None
        )

    return dict(
        current=current,
        target=3000,
        remaining=max(0, 3000 - current) if current is not None else None,
        peak=max((r["elo"] for r in rows), default=None),
        week=delta(7),
        month=delta(30),
        next=min(3000, (current // 100 + 1) * 100) if current is not None else None,
        history=rows,
    )


def sessions(matches, gap, ratings=()):
    groups = []
    for m in sorted(
        (m for m in matches if m["started"] and m["finished"]),
        key=lambda m: m["started"],
    ):
        if not groups or m["started"] - groups[-1][-1]["finished"] > gap * 60:
            groups.append([])
        groups[-1].append(m)
    result = []
    for group in reversed(groups):
        values = [(m["id"], summarize([m])["adr"]["value"]) for m in group]
        ranked = sorted((v for v in values if v[1] is not None), key=lambda v: v[1])
        split = len(group) // 2
        trend = (
            compare(summarize(group[split:]), summarize(group[:split])) if split else {}
        )
        observations = []
        low = [mid for mid, adr in ranked if adr < 65]
        if low:
            observations.append(
                f"Матчей с ADR ниже 65 · {len(low)} из {len(ranked)} с известным ADR."
            )
        for key in ("kd", "adr"):
            change = trend.get(key)
            if change is not None:
                observations.append(
                    f"{key.upper()} во второй части сессии · {change:+.2f} к первой части."
                )
        before = next(
            (r for r in reversed(ratings) if r["at"] <= group[0]["started"]), None
        )
        after = next((r for r in ratings if r["at"] >= group[-1]["finished"]), None)
        delta = None
        if before and after:
            other = [
                m
                for m in matches
                if m not in group and before["at"] < (m["finished"] or 0) <= after["at"]
            ]
            if not other:
                delta = after["elo"] - before["elo"]
        result.append(
            dict(
                id=group[0]["id"],
                started=group[0]["started"],
                finished=group[-1]["finished"],
                elo_delta=delta,
                matches=[m["id"] for m in group],
                metrics=summarize(group[::-1]),
                trend=values,
                observations=observations,
                best=ranked[-1][0] if ranked else None,
                worst=ranked[0][0] if ranked else None,
            )
        )
    return result


def analysis(store, window, games=None):
    games = store.matches() if games is None else games
    current = summarize(games[:window])
    previous = summarize(games[window : window * 2])
    by_map = defaultdict(list)
    for m in games[:window]:
        for row in m["maps"]:
            by_map[row["map"] or "Неизвестна"].append(dict(m, maps=[row]))
    return dict(
        metrics=current,
        previous=previous,
        delta=compare(current, previous),
        count=min(window, len(games)),
        maps={k: summarize(v) for k, v in by_map.items()},
    )


def snapshot(store):
    games = store.matches()
    with store.connect() as db:
        for window in WINDOWS:
            db.executemany(
                "INSERT OR REPLACE INTO metrics VALUES(?,?,?)",
                [
                    (window, k, dump(v | {"window": window}))
                    for k, v in summarize(games[:window]).items()
                ],
            )
