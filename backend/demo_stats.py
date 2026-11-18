"""Aggregate saved personal demo results without mixing sources or player identities."""

import json
from collections import Counter, defaultdict

from .analytics import ratio


def breakdown(store):
    account = store.rows("SELECT steam FROM players")
    player = store.settings()["steam_id"] or (account[0]["steam"] if account else "")
    sides = defaultdict(Counter)
    weapons = defaultdict(Counter)
    distances = defaultdict(Counter)
    count = 0
    for row in store.rows("SELECT summary FROM demos WHERE status='done'"):
        s = json.loads(row["summary"])
        if not player or s.get("player") != player:
            continue
        count += 1
        for source, target in (
            ("sides", sides),
            ("weapons", weapons),
            ("distances", distances),
        ):
            for key, stats in s[source].items():
                target[key].update(
                    {k: v for k, v in stats.items() if k != "winrate" and v is not None}
                )
    for v in sides.values():
        v["winrate"] = ratio(v["wins"], v["rounds"], 100)
        v["adr"] = ratio(v["damage"], v["rounds"])
    return dict(count=count, sides=sides, weapons=weapons, distances=distances)
