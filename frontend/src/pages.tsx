import { useState, useEffect } from "react";
import type { State, Session } from "./types";
import { download, get, post, request } from "./net";
import { Panel, Empty, date, fmt, MetricTable, today } from "./ui";
import type { Run } from "./settings";
import type { Episode } from "./demo";

export function Sessions({
  s,
  run,
  match,
}: {
  s: State;
  run: Run;
  match: (id: string) => void;
}) {
  const [id, set] = useState(s.sessions[0]?.id || "");
  const session = s.sessions.find((g) => g.id === id) || s.sessions[0];
  return (
    <Panel title="Игровые сессии">
      {session ? (
        <>
          <select
            value={session.id}
            aria-label="Сессия"
            onChange={(e) => set(e.target.value)}
          >
            {s.sessions.map((g) => (
              <option key={g.id} value={g.id}>
                {date(g.started)} ·{" "}
                {new Date(g.started * 1000).toLocaleTimeString("ru-RU")} ·
                Матчей {g.matches.length}
              </option>
            ))}
          </select>
          <div className="tiles">
            {["winrate", "kd", "adr"].map((k) => (
              <div key={k}>
                <small>{k.toUpperCase()}</small>
                <b>{fmt(session.metrics[k].value)}</b>
              </div>
            ))}
            <div>
              <small>Δ ELO сессии</small>
              <b>{fmt(session.elo_delta)}</b>
            </div>
          </div>
          {session.best && (
            <button onClick={() => match(session.best!)}>
              Лучший по ADR ↗
            </button>
          )}{" "}
          {session.worst && (
            <button onClick={() => match(session.worst!)}>
              Худший по ADR ↗
            </button>
          )}
          <p className="hint">
            ADR по ходу сессии ·{" "}
            {session.trend.map((v) => fmt(v[1])).join(" → ")}
          </p>
          {session.observations.map((v) => (
            <p className="hint" key={v}>
              {v}
            </p>
          ))}
          <Diary key={session.id} g={session} run={run} />
        </>
      ) : (
        <Empty>Сессии появятся после загрузки истории матчей.</Empty>
      )}
    </Panel>
  );
}
function Diary({ g, run }: { g: Session; run: Run }) {
  const [fields, set] = useState(g.diary);
  return (
    <details>
      <summary>Дневник сессии</summary>
      <div className="tiles">
        {Object.entries({
          wellbeing: "Самочувствие",
          focus: "Концентрация",
          fatigue: "Усталость",
          stress: "Стресс",
          rating: "Самооценка",
        }).map(([k, v]) => (
          <label key={k}>
            {v}
            <select
              value={fields[k] || ""}
              onChange={(e) =>
                set({ ...fields, [k]: e.target.value ? +e.target.value : null })
              }
            >
              <option value="">—</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <label>
        Комментарий
        <textarea
          value={fields.note || ""}
          onChange={(e) => set({ ...fields, note: e.target.value })}
        />
      </label>
      <button
        onClick={() =>
          run(() => post("diary/" + g.id, fields), "Запись сохранена")
        }
      >
        Сохранить запись
      </button>
    </details>
  );
}
export function Coaching({
  s,
  run,
  match,
  episode,
}: {
  s: State;
  run: Run;
  match: (id: string) => void;
  episode: (ep: Episode) => void;
}) {
  return (
    <>
      <div className="row">
        <span className="tag">{s.ranking || "Локальные правила"}</span>
        <button
          className="primary"
          onClick={() =>
            run(() => post("job/ai"), "Обновление поставлено в очередь")
          }
        >
          Обновить приоритеты
        </button>
      </div>
      {s.insights.length ? (
        s.insights.map((i) => (
          <Panel
            title={i.title}
            key={i.id}
            side={<span className="tag">{i.source}</span>}
          >
            <p className="lead">
              {i.label} ·{" "}
              <strong>
                {i.count} / {i.sample}
              </strong>
            </p>
            <p>
              Уверенность · {i.confidence}. Гипотеза · {i.impact}
            </p>
            <blockquote>{i.exercise}</blockquote>
            <p>
              {i.minutes} мин · {i.criterion}
            </p>
            <small>{i.reassess}</small>
            <details>
              <summary>Открыть доказательства</summary>
              <div className="row wrap">
                {i.evidence.map((e, n) => (
                  <button
                    key={n}
                    onClick={() =>
                      e.demo
                        ? episode({
                            demo: e.demo,
                            round: e.round,
                            tick: e.tick,
                          })
                        : e.match && match(e.match)
                    }
                  >
                    {e.demo
                      ? "Раунд " + e.round + " · тик " + e.tick
                      : "Матч · ADR " + e.adr}{" "}
                    ↗
                  </button>
                ))}
              </div>
            </details>
          </Panel>
        ))
      ) : (
        <Panel title="Наблюдения тренера">
          <Empty>
            Пока недостаточно наблюдений. Для анализа доступны статистика FACEIT
            и демозаписи с выбранным SteamID.
          </Empty>
        </Panel>
      )}
      <Panel title="Проверка улучшений">
        {s.evaluations.length ? (
          s.evaluations.map((e) => (
            <div className="entry" key={e.id}>
              <div>
                <b>{e.title}</b>
                <small>
                  После выполнения {date(e.completed)} · выборка {e.sample} / 10
                  · {e.ready ? "Период завершён" : "Данные накапливаются"}
                </small>
              </div>
              <span>
                {fmt(e.before)} → {fmt(e.current)} {e.unit}
              </span>
            </div>
          ))
        ) : (
          <Empty>
            Сравнение появится после подтверждения упражнения из персонального
            плана.
          </Empty>
        )}
        <p className="hint">
          Изменение показателя после занятий само по себе не устанавливает
          причину.
        </p>
      </Panel>
      <Panel title="История рекомендаций">
        {s.history.length ? (
          s.history.map((i) => (
            <div key={i.id} className="entry">
              <div>
                <b>{i.title}</b>
                <small>
                  {date(i.at)} · {i.source} · {i.count} / {i.sample}
                </small>
              </div>
              <span>
                {s.insights.some((x) => x.id === i.id)
                  ? "Актуально"
                  : "Предыдущий период"}
              </span>
            </div>
          ))
        ) : (
          <Empty>Здесь будут сохраняться выводы и размеры выборок.</Empty>
        )}
      </Panel>
    </>
  );
}
export function Training({ s, run }: { s: State; run: Run }) {
  const [kind, set] = useState("День"),
    [skill, choose] = useState(""),
    [difficulty, rate] = useState<Record<number, number>>({}),
    [scope, filter] = useState("Сегодня");
  const rows = s.training.exercises
    .filter(
      (e) =>
        scope === "Все" ||
        (scope === "Выполнено" ? !!e.completed : e.day === today()),
    )
    .sort((a, b) => a.day.localeCompare(b.day));
  return (
    <>
      <Panel title="Создать тренировку">
        <div className="formrow">
          <label>
            Период
            <select value={kind} onChange={(e) => set(e.target.value)}>
              {s.training.kinds.map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <label>
            Направление
            <select value={skill} onChange={(e) => choose(e.target.value)}>
              <option value="">По наблюдениям тренера</option>
              {s.training.skills.map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <button
            className="primary"
            onClick={() =>
              run(() => post("plan", { kind, skill }), "План сохранён")
            }
          >
            Создать план
          </button>
        </div>
        <p className="hint">
          Бюджет занятия · {s.options.minutes} мин. Навык можно выбрать вручную.
        </p>
      </Panel>
      <Panel
        title="Мои упражнения"
        side={
          <select
            aria-label="Фильтр тренировок"
            value={scope}
            onChange={(e) => filter(e.target.value)}
          >
            {["Сегодня", "Все", "Выполнено"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        }
      >
        {rows.map((e) => (
          <div key={e.id} className="exercise">
            <small>
              {e.day} · {e.kind} · {e.minutes} мин
            </small>
            <h3>{e.skill}</h3>
            <p>{e.instruction}</p>
            <div className="row">
              <label>
                Сложность
                <select
                  value={difficulty[e.id] || e.difficulty || 3}
                  onChange={(v) =>
                    rate({ ...difficulty, [e.id]: +v.target.value })
                  }
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
              <button
                onClick={() =>
                  run(() =>
                    post("exercise/" + e.id, {
                      done: !e.completed,
                      difficulty: difficulty[e.id] || 3,
                    }),
                  )
                }
              >
                {e.completed ? "Отменить отметку" : "Отметить выполнение"}
              </button>
            </div>
          </div>
        ))}
        {!rows.length && (
          <Empty>Упражнений в выбранном периоде пока нет.</Empty>
        )}
        <small>Выполнение всех планов · {fmt(s.training.progress)} %</small>
      </Panel>
      <Panel title="Практика по навыкам">
        {s.training.skills
          .filter((k) => s.training.exercises.some((e) => e.skill === k))
          .map((k) => {
            const tasks = s.training.exercises.filter((e) => e.skill === k),
              done = tasks.filter((e) => e.completed);
            return (
              <div className="entry" key={k}>
                <b>{k}</b>
                <span>
                  {done.length} / {tasks.length} ·{" "}
                  {done.reduce((n, e) => n + e.minutes, 0)} мин выполнено
                </span>
              </div>
            );
          })}
        {!s.training.exercises.length && (
          <Empty>Пока нет запланированных упражнений.</Empty>
        )}
      </Panel>
    </>
  );
}
export function Reports({ s, run }: { s: State; run: Run }) {
  const [kind, set] = useState("Сессия"),
    [preview, view] = useState(""),
    [ref, choose] = useState("");
  return (
    <>
      <Panel title="Новый отчёт">
        <div className="formrow">
          <label>
            Период
            <select
              value={kind}
              onChange={(e) => {
                set(e.target.value);
                choose("");
              }}
            >
              {["Матч", "Сессия", "Неделя", "Месяц"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          {["Матч", "Сессия"].includes(kind) && (
            <label>
              Выбор
              <select value={ref} onChange={(e) => choose(e.target.value)}>
                <option value="">Последний</option>
                {(kind === "Матч" ? s.matches : s.sessions).map((x) => (
                  <option key={x.id} value={x.id}>
                    {date(x.started)} · {x.id.slice(0, 10)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            className="primary"
            onClick={() =>
              run(() => post("report", { kind, ref }), "Отчёт сохранён")
            }
          >
            Сформировать
          </button>
        </div>
      </Panel>
      <Panel title="Архив отчётов">
        {s.reports.map((r) => (
          <div className="entry" key={r.id}>
            <div>
              <b>{r.title}</b>
              <small>
                {date(r.at)} · {r.id}
              </small>
            </div>
            <div className="row">
              <button
                onClick={() =>
                  run(async () =>
                    view(
                      await (
                        await request(
                          "report/" + encodeURIComponent(r.id) + "/html",
                        )
                      ).text(),
                    ),
                  )
                }
              >
                Просмотр
              </button>
              {["html", "pdf"].map((k) => (
                <button
                  key={k}
                  onClick={() =>
                    run(() =>
                      download(
                        "report/" + encodeURIComponent(r.id) + "/" + k,
                        "F1rti-" + r.id + "." + k,
                      ),
                    )
                  }
                >
                  {k.toUpperCase()} ↓
                </button>
              ))}
            </div>
          </div>
        ))}
        {!s.reports.length && (
          <Empty>Отчёты появятся после обработки матчей.</Empty>
        )}
      </Panel>
      {preview && (
        <Panel
          title="Просмотр отчёта"
          side={<button onClick={() => view("")}>Закрыть</button>}
        >
          <iframe title="Отчёт" sandbox="" srcDoc={preview} />
        </Panel>
      )}
    </>
  );
}
export function Statistics({ s }: { s: State }) {
  const [map, set] = useState(""),
    [demo, load] = useState<{
      count: number;
      sides: Record<string, Record<string, number>>;
      weapons: Record<string, Record<string, number>>;
      distances: Record<string, Record<string, number>>;
    } | null>(null),
    [lifetime, life] = useState<Record<string, unknown> | null>(null),
    [error, err] = useState("");
  const signature =
    s.demos.map((d) => d.id + d.status).join("") + s.options.steam_id;
  useEffect(() => {
    let live = true;
    get<NonNullable<typeof demo>>("demo-stats")
      .then((d) => live && load(d))
      .catch((e) => live && err(e.message));
    return () => {
      live = false;
    };
  }, [signature]);
  return (
    <>
      <Panel
        title="Сводка показателей"
        side={<span className="tag">FACEIT</span>}
      >
        <p className="hint">
          Матчей в периоде · {s.analytics.count}. В предыдущем ·{" "}
          {s.analytics.previous.winrate.period}. Δ рассчитана относительно
          предыдущего непересекающегося периода.
        </p>
        <MetricTable metrics={s.analytics.metrics} delta={s.analytics.delta} />
      </Panel>
      <Panel title="По картам">
        <select
          value={map}
          aria-label="Карта"
          onChange={(e) => set(e.target.value)}
        >
          <option value="">Выберите карту</option>
          {Object.keys(s.analytics.maps).map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
        {s.analytics.maps[map] && (
          <MetricTable metrics={s.analytics.maps[map]} />
        )}
      </Panel>
      <Panel title="Статистика профиля FACEIT">
        <button
          onClick={() =>
            get<Record<string, unknown>>("lifetime")
              .then(life)
              .catch((e) => err(e.message))
          }
        >
          Показать данные профиля и карт
        </button>
        {lifetime && (
          <pre>
            {Object.keys(lifetime).length
              ? JSON.stringify(lifetime, null, 2)
              : "Профиль ещё не загружен"}
          </pre>
        )}
      </Panel>
      <Panel
        title="Стороны и оружие"
        side={<span className="tag">CS2 DEMO</span>}
      >
        {error && <p>{error}</p>}
        {demo?.count ? (
          <>
            <p className="hint">Персональные демозаписи · {demo.count}</p>
            <table>
              <thead>
                <tr>
                  <th>Сторона</th>
                  <th>Раунды</th>
                  <th>Победы, %</th>
                  <th>ADR</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(demo.sides).map(([name, v]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>{v.rounds}</td>
                    <td>{fmt(v.winrate)}</td>
                    <td>{fmt(v.adr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h3>Использование оружия игроком</h3>
            <table>
              <thead>
                <tr>
                  <th>Оружие</th>
                  <th>Применения</th>
                  <th>Убийства</th>
                  <th>Урон</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(demo.weapons).map(([name, v]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>{fmt(v.shots)}</td>
                    <td>{fmt(v.kills)}</td>
                    <td>{fmt(v.damage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <Empty>
            Для разбивки нужны обработанные записи с выбранным SteamID.
          </Empty>
        )}
      </Panel>
    </>
  );
}
