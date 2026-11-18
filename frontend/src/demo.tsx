import { Telemetry } from "./telemetry";
import { useState, useEffect, useRef } from "react";
import type { State, DemoDetail, EventRow } from "./types";
import { get, post, request } from "./net";
import { Panel, Empty, Icon, fmt, labels } from "./ui";
import type { Run } from "./settings";
export type Episode = { demo: string; round?: number; tick?: number };
const words: Record<string, string> = {
  player_death: "Убийство",
  player_hurt: "Попадание",
  weapon_fire: "Выстрел",
  round_start: "Начало раунда",
  round_end: "Конец раунда",
  player_blind: "Ослепление",
  round_freeze_end: "Конец закупки",
  bomb_planted: "Бомба установлена",
  bomb_defused: "Бомба обезврежена",
  hegrenade_detonate: "Взрыв HE",
  flashbang_detonate: "Взрыв flash",
  smokegrenade_detonate: "Раскрытие smoke",
  inferno_startburn: "Возгорание",
};
const statuses: Record<string, string> = {
  done: "Готово",
  queued: "В очереди",
  running: "Анализ",
  error: "Ошибка",
};
export function Demos({
  s,
  run,
  episode,
}: {
  s: State;
  run: Run;
  episode: Episode | null;
}) {
  const picker = useRef<HTMLInputElement>(null),
    [id, select] = useState(episode?.demo || ""),
    [info, set] = useState<DemoDetail | null>(null),
    [num, round] = useState(episode?.round || 0),
    [events, load] = useState<EventRow[]>([]),
    [filter, kind] = useState(""),
    [upload, setUpload] = useState(""),
    [error, err] = useState(""),
    [steam, choose] = useState(""),
    [linked, link] = useState(""),
    [selectedTick, seek] = useState(episode?.tick || 0);
  const stamp = s.demos.find((d) => d.id === id)?.status;
  useEffect(() => {
    let live = true;
    set(null);
    err("");
    if (id)
      get<DemoDetail>("demo/" + id)
        .then((d) => {
          if (live) {
            set(d);
            choose(d.summary.player || "");
            link(d.match_id || "");
            round((n) =>
              d.rounds.some((r) => r.number === n)
                ? n
                : d.rounds[0]?.number || 0,
            );
          }
        })
        .catch((e) => live && err(e.message));
    return () => {
      live = false;
    };
  }, [id, stamp]);
  useEffect(() => {
    let live = true;
    load([]);
    if (id && num)
      get<EventRow[]>("demo/" + id + "/round/" + num)
        .then((d) => live && load(d))
        .catch((e) => live && err(e.message));
    return () => {
      live = false;
    };
  }, [id, num, stamp]);
  useEffect(() => {
    if (selectedTick && events.length) {
      const next = events.find(
        (e) => e.tick >= selectedTick && (!filter || e.kind === filter),
      );
      if (next)
        document
          .getElementById("tick-" + next.tick)
          ?.scrollIntoView({ block: "nearest" });
    }
  }, [selectedTick, events, filter]);
  async function files(list: FileList | null) {
    if (!list) return;
    await run(async () => {
      try {
        for (const file of Array.from(list)) {
          setUpload(file.name);
          await request("demo?name=" + encodeURIComponent(file.name), {
            method: "POST",
            body: file,
          });
        }
      } finally {
        setUpload("");
      }
    }, "Импорт завершён");
  }
  const r = info?.rounds.find((r) => r.number === num);
  return (
    <>
      <div
        className="drop"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          files(e.dataTransfer.files);
        }}
      >
        <Icon name="folder" size={32} />
        <div>
          <h2>Импорт демозаписи</h2>
          <p>
            {upload || "Перетащите .dem или .dem.gz сюда · до 2 ГиБ на файл"}
          </p>
        </div>
        <input
          type="file"
          hidden
          multiple
          accept=".dem,.gz"
          ref={picker}
          onChange={(e) => {
            files(e.target.files);
            e.target.value = "";
          }}
        />
        <button className="primary" onClick={() => picker.current?.click()}>
          Выбрать файлы
        </button>
      </div>
      <Panel
        title="Очередь анализа"
        side={
          <button onClick={() => run(() => post("pause"))}>
            {s.options.paused ? "Возобновить" : "Приостановить анализ"}
          </button>
        }
      >
        {s.demos.length ? (
          s.demos.map((d) => (
            <div className="entry" key={d.id}>
              <div>
                <b>{d.name}</b>
                <small>
                  {statuses[d.status]} · {d.progress}% {d.error}
                </small>
              </div>
              <div>
                {d.status === "done" && (
                  <button
                    onClick={() => {
                      select(d.id);
                      seek(0);
                    }}
                  >
                    Открыть
                  </button>
                )}{" "}
                {["done", "error"].includes(d.status) && (
                  <button
                    onClick={() => run(() => post("demo/" + d.id + "/retry"))}
                  >
                    Повторить
                  </button>
                )}
              </div>
            </div>
          ))
        ) : (
          <Empty>Очередь пуста. Можно добавить несколько файлов сразу.</Empty>
        )}
      </Panel>
      {error && <p role="alert">{error}</p>}
      {info?.summary.map && (
        <Panel
          title={info.summary.map}
          side={<span className="tag">CS2 DEMO</span>}
        >
          <p>
            {info.name} · {info.rounds.length} раундов · {info.summary.version}
          </p>
          <div className="row">
            <select
              aria-label="Игрок в демозаписи"
              value={steam}
              onChange={(e) => choose(e.target.value)}
            >
              <option value="">Выберите свой SteamID</option>
              {Object.entries(info.summary.players || {}).map(([k, v]) => (
                <option key={k} value={k}>
                  {v} · {k}
                </option>
              ))}
            </select>
            <button
              disabled={!steam}
              onClick={() =>
                run(
                  () => post("settings", { ...s.options, steam_id: steam }),
                  "SteamID сохранён",
                )
              }
            >
              Мой игрок
            </button>
          </div>
          <div className="row">
            <select
              aria-label="Связанный матч"
              value={linked}
              onChange={(e) => link(e.target.value)}
            >
              <option value="">Без привязки к матчу</option>
              {s.matches.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.maps.map((x) => x.map).join(", ")} · {m.id}
                </option>
              ))}
            </select>
            <button
              onClick={() =>
                run(
                  () => post("demo/" + id + "/link", { match_id: linked }),
                  "Привязка сохранена",
                )
              }
            >
              Связать с матчем
            </button>
          </div>
          {Object.keys(info.summary.metrics || {}).length > 0 && (
            <div className="tiles">
              {Object.entries(info.summary.metrics || {}).map(([k, v]) => (
                <div key={k}>
                  <small>{labels[k] || k}</small>
                  <b>{fmt(v)}</b>
                </div>
              ))}
            </div>
          )}
          {(
            [
              "weapons",
              "distances",
              "sides",
              "repeated_zones",
              "grenades",
              "utility",
              "metric_records",
              "supported",
            ] as const
          ).map((k, i) => (
            <details key={k}>
              <summary>
                {
                  [
                    "Оружие и дуэли",
                    "Дистанции в игровых единицах",
                    "Стороны",
                    "Повторные смерти по зонам 256 × 256",
                    "Гранаты · тики и координаты",
                    "Урон гранатами и ослепление",
                    "Источники и методы метрик",
                    "Доступные события",
                  ][i]
                }
              </summary>
              <Telemetry
                data={info.summary[k]}
                index={
                  k === "weapons"
                    ? "Оружие"
                    : k === "distances"
                      ? "Дистанция"
                      : k === "repeated_zones"
                        ? "Координаты зоны"
                        : "Показатель"
                }
              />
            </details>
          ))}
        </Panel>
      )}
      {r && (
        <Panel
          title="Таймлайн раунда"
          side={
            <select
              aria-label="Раунд"
              value={num}
              onChange={(e) => round(+e.target.value)}
            >
              {info!.rounds.map((r) => (
                <option key={r.number} value={r.number}>
                  Раунд {r.number}
                </option>
              ))}
            </select>
          }
        >
          <p>
            Тики {r.start}–{r.end} · Сторона {r.side || "—"} · Победитель{" "}
            {r.winner}
          </p>
          {r.facts.map((f, i) => (
            <button
              key={i}
              onClick={() => {
                kind("");
                seek(f.tick);
              }}
            >
              {f.label} · {f.tick}
            </button>
          ))}
          {r.hypotheses?.map((h, i) => (
            <p key={i} className="hint">
              Гипотеза · тик {h.tick} · {h.label}
            </p>
          ))}
          <details>
            <summary>Составы, экономика и дуэли</summary>
            <Telemetry
              data={r.roster}
              columns={["name", "team_num", "current_equip_value", "balance"]}
            />
            <h3>Завершённые дуэли</h3>
            <Telemetry data={r.duels} />
          </details>
          <div className="row">
            <select
              value={filter}
              onChange={(e) => kind(e.target.value)}
              aria-label="Тип события"
            >
              <option value="">Все события</option>
              {Array.from(new Set(events.map((e) => e.kind))).map((k) => (
                <option key={k} value={k}>
                  {words[k] || k}
                </option>
              ))}
            </select>
            <label>
              Перейти к тику
              <input
                type="number"
                value={selectedTick || ""}
                onChange={(e) => seek(+e.target.value)}
              />
            </label>
          </div>
          <div className="timeline">
            {events
              .filter((e) => !filter || e.kind === filter)
              .map((e, i) => (
                <details
                  key={i}
                  id={"tick-" + e.tick}
                  className={e.tick === selectedTick ? "selected" : ""}
                >
                  <summary>
                    <code>{e.tick}</code> {words[e.kind] || e.kind} ·{" "}
                    {e.attacker_name || e.user_name || ""} {e.weapon}
                  </summary>
                  <pre>{JSON.stringify(e, null, 2)}</pre>
                </details>
              ))}
          </div>
        </Panel>
      )}
    </>
  );
}
