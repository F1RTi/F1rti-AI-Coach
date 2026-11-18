import hashlib
import json
from datetime import date, timedelta
from typing import Protocol

import httpx

from .analytics import ratio, summarize
from .db import dump, now
from .faceit import ServiceError

# All user-facing claims and exercises are tied to measurable, local observations.
RULES = {
    "opening": (
        "Первые дуэли",
        "Peeking",
        "Разберите первые дуэли в записи. Для каждого выхода запишите угол и присутствие напарника.",
        "Снизить долю первых смертей среди первых дуэлей.",
    ),
    "trade": (
        "Смерти без размена",
        "Teamplay",
        "Откройте отмеченные смерти. Найдите позицию напарника и предложите совместный выход.",
        "Снизить долю смертей без ответного убийства за 320 тиков.",
    ),
    "damage": (
        "Матчи с низким ADR",
        "Demo review",
        "Сравните два раунда с низким уроном с двумя результативными. Запишите одно изменение в выборе дуэли.",
        "Снизить долю карт с ADR ниже 65.",
    ),
    "swing": (
        "Разброс результативности",
        "Decision-making",
        "Сопоставьте экономику, сторону и выбранную дуэль в лучшей и худшей по ADR карте.",
        "Снизить стандартное отклонение ADR при сохранении среднего урона.",
    ),
    "strength": (
        "Стабильный вклад уроном",
        "Positioning",
        "Разберите две результативные позиции и запишите условия, при которых их удалось занять.",
        "Сохранить долю карт с ADR от 80.",
    ),
}


def insight(rule, numerator, denominator, evidence, label, source, score):
    name, skill, exercise, criterion = RULES[rule]
    key = hashlib.sha256(
        dump([rule, evidence, numerator, denominator]).encode()
    ).hexdigest()[:20]
    return dict(
        id=key,
        rule=rule,
        title=name,
        skill=skill,
        exercise=exercise,
        criterion=criterion,
        count=numerator,
        sample=denominator,
        evidence=evidence,
        label=label,
        source=source,
        confidence="средняя" if denominator >= 10 else "низкая",
        score=round(score, 2),
        minutes=20,
        reassess="После следующих 10 матчей или сопоставимых демозаписей",
        impact={
            "opening": "Возможность чаще сохранять состав команды после первого контакта.",
            "trade": "Возможность чаще восстанавливать численное равенство.",
            "strength": "Повторение результативных игровых решений.",
        }.get(rule, "Возможность стабильнее вносить урон."),
        hypothesis=True,
    )


def candidates(store):
    games = store.matches()[:20]
    maps = [(m["id"], v) for m in games for v in m["maps"] if v.get("adr") is not None]
    result = []
    if len(maps) >= 5:
        for rule, cond in (
            ("damage", lambda x: x < 65),
            ("strength", lambda x: x >= 80),
        ):
            hits = [
                dict(match=k, map=v["map"], adr=v["adr"])
                for k, v in maps
                if cond(v["adr"])
            ]
            if len(hits) >= 3:
                label = "Карт с ADR ниже 65" if rule == "damage" else "Карт с ADR от 80"
                result.append(
                    insight(
                        rule,
                        len(hits),
                        len(maps),
                        hits,
                        label,
                        "FACEIT",
                        len(hits) / len(maps),
                    )
                )
        spread = summarize(games)["variability"]["value"]
        if spread is not None and spread >= 20:
            result.append(
                insight(
                    "swing",
                    len(maps),
                    len(maps),
                    [dict(match=k, adr=v["adr"]) for k, v in maps],
                    f"Стандартное отклонение ADR · {spread}",
                    "FACEIT",
                    0.55,
                )
            )
    episodes, opening, total_deaths, total_entries = [], [], 0, 0
    accounts = store.rows("SELECT steam FROM players LIMIT 1")
    target = store.settings()["steam_id"] or (accounts[0]["steam"] if accounts else "")
    for d in store.rows(
        "SELECT id,summary FROM demos WHERE status='done' ORDER BY updated DESC LIMIT 20"
    ):
        s = json.loads(d["summary"])
        if not target or s["player"] != target:
            continue
        m = s["metrics"]
        total_deaths += m.get("deaths", 0)
        total_entries += m.get("opening_deaths", 0) + m.get("opening_kills", 0)
        opening.extend(
            dict(demo=d["id"], **e)
            for e in s["facts"]
            if e["label"] == "Первая смерть раунда"
        )
        episodes.extend(
            dict(demo=d["id"], **e) for e in s["facts"] if "без ответного" in e["label"]
        )
    for rule, hits, total, label in [
        ("trade", episodes, total_deaths, "Смерти без ответного убийства за 320 тиков"),
        ("opening", opening, total_entries, "Проигранные первые дуэли"),
    ]:
        if total >= 5 and len(hits) >= 3 and len(hits) / total >= 0.5:
            result.append(
                insight(
                    rule, len(hits), total, hits, label, "CS2 demo", len(hits) / total
                )
            )
    return sorted(result, key=lambda x: (x["rule"] == "strength", -x["score"]))


class AIProvider(Protocol):
    def prioritize(self, insights: list) -> list: ...


class CompatibleProvider:
    def __init__(self, base, key, model, transport=None):
        self.base, self.key, self.model, self.transport = base, key, model, transport

    def prioritize(self, insights):
        if not insights:
            return []
        # Model selects evidence-backed training priorities. Novel factual claims cannot enter the UI.
        compact = [
            {
                k: i[k]
                for k in ("id", "title", "count", "sample", "source", "label", "impact")
            }
            for i in insights
        ]
        with httpx.Client(timeout=35, transport=self.transport) as client:
            r = client.post(
                self.base.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + self.key},
                json={
                    "model": self.model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты тренер CS2. Отсортируй данные направления по тренировочному приоритету и достаточности доказательств. Верни JSON с единственным полем ids, списком всех исходных id.",
                        },
                        {"role": "user", "content": dump(compact)},
                    ],
                },
            )
        if r.status_code != 200:
            raise ServiceError(f"AI-провайдер вернул HTTP {r.status_code}")
        try:
            result = json.loads(r.json()["choices"][0]["message"]["content"])
            ids = result["ids"]
            by_id = {i["id"]: i for i in insights}
            if (
                set(result) != {"ids"}
                or not isinstance(ids, list)
                or len(ids) != len(by_id)
                or set(ids) != set(by_id)
            ):
                raise ValueError
            return [by_id[key] for key in ids]
        except (KeyError, IndexError, ValueError, TypeError):
            raise ServiceError(
                "Ответ AI не прошёл проверку ссылок на доказательства"
            ) from None


def refresh(store, provider=None):
    items = candidates(store)
    if provider:
        items = provider.prioritize(items)
    with store.connect() as db:
        for i in items:
            db.execute(
                "INSERT OR IGNORE INTO insights VALUES(?,?,?)",
                (i["id"], now(), dump(i)),
            )
    store.change(
        {
            "priorities": [i["id"] for i in items],
            "ranking": "AI" if provider else "Локальные правила",
        }
    )
    return items


def advice(store):
    history = [
        json.loads(r["data"]) | {"at": r["at"]}
        for r in store.rows("SELECT * FROM insights ORDER BY at DESC,rowid DESC")
    ]
    lookup = {i["id"]: i for i in history}
    return [
        lookup[k] for k in store.settings().get("priorities", []) if k in lookup
    ], history


def evaluations(store, history, games):
    """Compare future observations to the frozen baseline, anchored on an actual completion."""
    completions = store.rows("""SELECT e.skill,c.at,p.data FROM completions c JOIN exercises e ON e.id=c.exercise
                              JOIN plans p ON p.id=e.plan ORDER BY c.at""")
    links = store.rows("""SELECT m.finished,d.summary FROM demos d JOIN matches m ON m.id=d.match_id
                        WHERE d.status='done' ORDER BY m.finished""")
    results = []
    account = store.rows("SELECT steam FROM players")
    player = store.settings()["steam_id"] or (account[0]["steam"] if account else "")
    for i in history:
        completion = next(
            (
                c
                for c in completions
                if c["at"] >= i["at"]
                and c["skill"] == i["skill"]
                and i["id"] in json.loads(c["data"]).get("priorities", [])
            ),
            None,
        )
        if not completion:
            continue
        after = sorted(
            (g for g in games if (g["started"] or 0) > completion["at"]),
            key=lambda g: g["started"],
        )[:10]
        before = ratio(i["count"], i["sample"], 100)
        current = None
        sample = len(after)
        unit = "%"
        if i["rule"] in ("damage", "strength", "swing"):
            values = [
                r["adr"] for g in after for r in g["maps"] if r.get("adr") is not None
            ]
            sample = sum(
                any(v.get("adr") is not None for v in g["maps"]) for g in after
            )
            if i["rule"] == "swing":
                from statistics import pstdev

                before = round(pstdev(e["adr"] for e in i["evidence"]), 2)
                current = round(pstdev(values), 2) if len(values) > 1 else None
                unit = "ADR"
            else:
                hits = sum(v < 65 if i["rule"] == "damage" else v >= 80 for v in values)
                current = ratio(hits, len(values), 100)
        else:
            rows = [
                json.loads(r["summary"])
                for r in links
                if r["finished"] > completion["at"]
            ]
            rows = [r for r in rows if player and r["player"] == player][:10]
            sample = len(rows)
            data = [r["metrics"] for r in rows]
            if i["rule"] == "opening":
                deaths = sum(m.get("opening_deaths", 0) for m in data)
                current = ratio(
                    deaths, deaths + sum(m.get("opening_kills", 0) for m in data), 100
                )
            else:
                deaths = sum(m.get("deaths", 0) for m in data)
                current = ratio(
                    deaths - sum(m.get("traded_deaths", 0) for m in data), deaths, 100
                )
        results.append(
            dict(
                id=i["id"],
                title=i["title"],
                before=before,
                current=current,
                unit=unit,
                completed=completion["at"],
                sample=sample,
                ready=sample >= 10 and current is not None,
            )
        )
    return results


SKILLS = {
    "Aim": "На тренировочной карте попрактикуйте перевод на одиночную цель.",
    "Counter-strafing": "Чередуйте остановку и одиночный выстрел на тренировочной карте.",
    "Crosshair placement": "Пройдите маршрут по игровой карте, удерживая прицел на уровне модели.",
    "Peeking": "Отработайте выход из-за одного угла и возврат в укрытие.",
    "Recoil control": "Сравните серии по мишени на двух дистанциях.",
    "Movement": "Повторите маршрут с остановками в выбранных игровых позициях.",
    "Utility": "Воспроизведите две раскидки из недавнего матча на пустом сервере.",
    "Positioning": "Разберите две позиции с возможностью отхода.",
    "Decision-making": "Остановите запись до дуэли и запишите два возможных решения.",
    "Demo review": "Выберите раунд и запишите наблюдение с номером раунда и тиком.",
    "Teamplay": "Разберите совместный выход и дистанцию до напарника.",
}
KINDS = {"День": 1, "Неделя": 7, "Месяц": 30, "Перед сессией": 1, "Восстановление": 1}


def plan(store, kind, manual=None, adapt=False, day=None):
    days = KINDS[kind]
    today = day or date.today()
    active, _ = advice(store)
    priorities = [(i["skill"], i["exercise"]) for i in active[:3]]
    if manual:
        priorities = [(manual, SKILLS[manual])]
    if not priorities:
        if adapt:
            return None
        raise ValueError("Выберите навык вручную, пока недостаточно наблюдений")
    minutes = store.settings()["minutes"]
    if kind == "Перед сессией":
        minutes = min(minutes, 15)
    elif kind == "Восстановление":
        minutes = min(minutes, 10)
        priorities = [
            (
                "Demo review",
                "После перерыва разберите один раунд по теме «"
                + priorities[0][0]
                + "». Отметьте одно удачное решение.",
            )
        ]
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT id,data FROM plans WHERE day=? AND kind=?",
            (today.isoformat(), kind),
        ).fetchone()
        meta = dict(
            manual=bool(manual),
            skill=manual,
            priorities=[i["id"] for i in active],
            minutes=minutes,
        )
        if row:
            pid = row["id"]
            if json.loads(row["data"]) == meta:
                return pid
            if adapt and json.loads(row["data"]).get("manual"):
                return pid
            if db.execute(
                "SELECT 1 FROM completions JOIN exercises ON exercise=id WHERE plan=?",
                (pid,),
            ).fetchone():
                return pid
            db.execute("DELETE FROM exercises WHERE plan=?", (pid,))
            db.execute("UPDATE plans SET data=? WHERE id=?", (dump(meta), pid))
        else:
            pid = db.execute(
                "INSERT INTO plans(day,kind,data) VALUES(?,?,?)",
                (today.isoformat(), kind, dump(meta)),
            ).lastrowid
        for day in range(days):
            for n, (skill, task) in enumerate(priorities):
                duration = minutes // len(priorities) + int(
                    n < minutes % len(priorities)
                )
                db.execute(
                    "INSERT INTO exercises(plan,day,skill,instruction,minutes) VALUES(?,?,?,?,?)",
                    (
                        pid,
                        (today + timedelta(days=day)).isoformat(),
                        skill,
                        task,
                        duration,
                    ),
                )
    return pid


def update_daily(store):
    pid = plan(store, "День", adapt=True)
    if pid and not store.rows(
        """SELECT 1 FROM exercises e LEFT JOIN completions c ON c.exercise=e.id
                                 WHERE e.plan=? AND c.exercise IS NULL LIMIT 1""",
        (pid,),
    ):
        plan(store, "День", adapt=True, day=date.today() + timedelta(days=1))


def training(store):
    rows = store.rows("""SELECT e.*,p.kind,c.at AS completed,c.difficulty FROM exercises e JOIN plans p ON e.plan=p.id
                      LEFT JOIN completions c ON e.id=c.exercise ORDER BY e.day DESC,e.id""")
    return dict(
        exercises=rows,
        skills=list(SKILLS),
        kinds=list(KINDS),
        progress=ratio(sum(bool(r["completed"]) for r in rows), len(rows), 100),
    )
