import { useState, useEffect, useCallback, useRef } from "react";
import { createRoot } from "react-dom/client";
import type { State, Match } from "./types";
import { get, post } from "./net";
import { Panel, Empty, Icon, Chart, MatchList, fmt, date, today } from "./ui";
import { Settings } from "./settings";
import { Demos, type Episode } from "./demo";
import { Sessions, Coaching, Training, Reports, Statistics } from "./pages";
import "./style.css";

const nav = [
  ["home", "Обзор"],
  ["stats", "Статистика"],
  ["match", "Разбор матчей"],
  ["demo", "Демозаписи"],
  ["coach", "AI-тренер"],
  ["training", "Тренировки"],
  ["report", "Отчёты"],
  ["settings", "Настройки"],
];
function App() {
  const [page, go] = useState("home"),
    [s, set] = useState<State | null>(null),
    [n, windowSize] = useState(20),
    [days, setDays] = useState(0),
    [message, msg] = useState(""),
    [error, err] = useState(""),
    [busy, working] = useState(false),
    [mid, selectMatch] = useState(""),
    [ep, selectEp] = useState<Episode | null>(null);
  const sequence = useRef(0);
  const reload = useCallback(async () => {
    const ticket = ++sequence.current;
    const value = await get<State>(
      "state?window=" + n + "&days=" + (page === "stats" ? days : 0),
    );
    if (ticket === sequence.current) set(value);
  }, [n, days, page]);
  useEffect(() => {
    reload().catch((e) => err(e.message));
    const timer = setInterval(() => {
      if (!document.hidden) reload().catch((e) => err(e.message));
    }, 7000);
    return () => {
      clearInterval(timer);
      sequence.current++;
    };
  }, [reload]);
  async function run(action: () => Promise<unknown>, success = "") {
    working(true);
    msg("");
    err("");
    try {
      await action();
      await reload();
      msg(success);
    } catch (e) {
      err(e instanceof Error ? e.message : String(e));
    } finally {
      working(false);
    }
  }
  function openMatch(id: string) {
    selectMatch(id);
    go("match");
  }
  function openEpisode(episode: Episode) {
    selectEp(episode);
    go("demo");
  }
  const profile = () => go("settings"),
    title = nav.find((v) => v[0] === page)![1],
    job = s?.jobs[0];
  return (
    <div className="app">
      <aside>
        <div className="brand">
          <div className="brandmark">
            F<span>1</span>
          </div>
          <div>
            F1rti <em>AI Coach</em>
            <small>COUNTER-STRIKE 2</small>
          </div>
        </div>
        <nav>
          {nav.map(([k, l]) => (
            <button
              key={k}
              className={page === k ? "active" : ""}
              onClick={() => {
                go(k);
                msg("");
                err("");
                if (k === "match") selectMatch("");
                if (k === "demo") selectEp(null);
              }}
            >
              <Icon name={k} />
              <span>{l}</span>
            </button>
          ))}
        </nav>
        <div className="identity">
          <div className="avatar">F1</div>
          <div>
            <b>F1rti</b>
            <small>Локальный профиль</small>
          </div>
        </div>
      </aside>
      <main>
        <header className="top">
          <div>
            <span>Рабочее пространство</span>
            <i>/</i>
            {title}
          </div>
          <div className="online">
            <b /> Локально
          </div>
        </header>
        <article>
          <div className="pagehead">
            <div className="heading">
              <small>
                F1RTI <i>/</i> CS2
              </small>
              <h1>{title}</h1>
            </div>
            {s && (page === "home" || page === "stats") && (
              <label className="window">
                Период
                <select value={n} onChange={(e) => windowSize(+e.target.value)}>
                  {[5, 10, 20, 50, 100].map((v) => (
                    <option key={v} value={v}>
                      {v} матчей
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          {(error || message || busy) && (
            <div className={"notice " + (error ? "failure" : "")} role="status">
              {error || (busy ? "Выполняется…" : message)}{" "}
              {!busy && (
                <button
                  aria-label="Закрыть сообщение"
                  onClick={() => {
                    err("");
                    msg("");
                  }}
                >
                  ×
                </button>
              )}
            </div>
          )}
          {job && (
            <div className={"job " + (job.state === "error" ? "red" : "")}>
              {
                (
                  {
                    queued: "В очереди",
                    running: "В работе",
                    error: "Ошибка",
                    done: "Готово",
                  } as Record<string, string>
                )[job.state]
              }{" "}
              · {job.message || job.kind}
            </div>
          )}
          {!s ? (
            <Panel title="Открытие локальной базы">
              <p>Подключение к приложению…</p>
            </Panel>
          ) : (
            <>
              {page === "home" && (
                <>
                  <div className="hero">
                    <div className="heroleft">
                      <div className="eyebrow">
                        <span className="tinyline" /> FACEIT ELO
                      </div>
                      <div className="score">
                        {fmt(s.goal.current)} <small>ELO</small>
                      </div>
                      <div className="goal">
                        <Icon name="target" size={16} /> Целевой рейтинг{" "}
                        <b>3 000+</b>
                      </div>
                    </div>
                    <div className="herochart">
                      <div className="charttitle">
                        <b>Динамика рейтинга</b>
                        <span>История снимков</span>
                      </div>
                      <Chart points={s.goal.history} />
                      <div className="chartfoot">
                        <span>
                          {s.goal.history.length
                            ? date(s.goal.history[0].at)
                            : "Первый снимок"}
                        </span>
                        <span>
                          {s.goal.history.length
                            ? date(s.goal.history.at(-1)!.at)
                            : "Сегодня"}
                        </span>
                      </div>
                    </div>
                  </div>
                  {!s.keys.faceit && (
                    <div className="connect">
                      <span className="connecticon">
                        <Icon name="link" />
                      </span>
                      <div>
                        <b>Подключите профиль FACEIT</b>
                        <small>
                          Добавьте API-ключ, чтобы загрузить рейтинг и историю
                          матчей F1rti.
                        </small>
                      </div>
                      <button onClick={profile}>
                        Подключить <Icon name="arrow" size={14} />
                      </button>
                    </div>
                  )}
                  <div className="kpis">
                    {[
                      ["winrate", "Победы", "%"],
                      ["kd", "Убийства / смерти", "K/D"],
                      ["adr", "Средний урон", "ADR"],
                      ["hs", "Попадания в голову", "%"],
                    ].map(([k, name, unit]) => (
                      <div className="kpi" key={k}>
                        <small>{name}</small>
                        <strong>
                          {fmt(s.analytics.metrics[k].value)} <sub>{unit}</sub>
                        </strong>
                        <span>
                          FACEIT · {s.analytics.metrics[k].sample} наблюд.
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="columns">
                    <Panel
                      title="Последние матчи"
                      side={
                        <button className="textbtn" onClick={() => go("match")}>
                          Все матчи ↗
                        </button>
                      }
                    >
                      <MatchList
                        rows={s.matches.slice(0, 5)}
                        open={openMatch}
                      />
                    </Panel>
                    <Panel
                      title="Тренировка на сегодня"
                      side={<Icon name="training" />}
                    >
                      {s.training.exercises
                        .filter((e) => e.day === today())
                        .slice(0, 3)
                        .map((e) => (
                          <p key={e.id}>
                            {e.skill} · {e.minutes} мин {e.completed ? "✓" : ""}
                          </p>
                        ))}
                      {!s.training.exercises.some((e) => e.day === today()) && (
                        <Empty>План на сегодня ещё не создан.</Empty>
                      )}
                      <button onClick={() => go("training")}>
                        Открыть тренировки ↗
                      </button>
                    </Panel>
                  </div>
                  <Panel
                    title="Приоритеты развития"
                    side={
                      <button className="textbtn" onClick={() => go("coach")}>
                        К тренеру ↗
                      </button>
                    }
                  >
                    {s.insights.length ? (
                      s.insights.slice(0, 3).map((i) => (
                        <div className="entry" key={i.id}>
                          <b>{i.title}</b>
                          <small>
                            {i.count} / {i.sample} · {i.source}
                          </small>
                        </div>
                      ))
                    ) : (
                      <Empty>
                        Тренер сформирует приоритеты, когда накопятся
                        сопоставимые наблюдения.
                      </Empty>
                    )}
                  </Panel>
                  <Panel title="Путь к 3000 ELO">
                    <div className="tiles">
                      {[
                        ["До цели", s.goal.remaining],
                        ["Ближайшая цель", s.goal.next],
                        ["За неделю", s.goal.week],
                        ["За месяц", s.goal.month],
                        ["Наблюдаемый максимум", s.goal.peak],
                      ].map(([k, v]) => (
                        <div key={k}>
                          <small>{k}</small>
                          <b>{fmt(v)}</b>
                        </div>
                      ))}
                    </div>
                  </Panel>
                  <button
                    disabled={busy}
                    onClick={() =>
                      s.keys.faceit
                        ? run(
                            () => post("job/sync"),
                            "Синхронизация поставлена в очередь",
                          )
                        : profile()
                    }
                  >
                    <Icon name="sync" /> Синхронизировать сейчас
                  </button>
                </>
              )}
              {page === "stats" && (
                <>
                  <label className="window">
                    По времени
                    <select
                      value={days}
                      onChange={(e) => setDays(+e.target.value)}
                    >
                      {[0, 7, 30, 90].map((d) => (
                        <option key={d} value={d}>
                          {d ? d + " дней" : "Вся история"}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Statistics s={s} />
                  <Sessions s={s} run={run} match={openMatch} />
                </>
              )}
              {page === "match" && (
                <>
                  {mid && s.matches.find((m) => m.id === mid) && (
                    <MatchDetail
                      key={mid}
                      m={s.matches.find((m) => m.id === mid)!}
                      demos={s.demos.filter((d) => d.match_id === mid)}
                      episode={openEpisode}
                    />
                  )}
                  <Panel title="История матчей">
                    <MatchList rows={s.matches} open={openMatch} />
                  </Panel>
                </>
              )}
              {page === "demo" && <Demos s={s} run={run} episode={ep} />}
              {page === "coach" && (
                <Coaching
                  s={s}
                  run={run}
                  match={openMatch}
                  episode={openEpisode}
                />
              )}
              {page === "training" && <Training s={s} run={run} />}
              {page === "report" && <Reports s={s} run={run} />}
              {page === "settings" && <Settings s={s} run={run} />}
            </>
          )}
        </article>
      </main>
    </div>
  );
}
function MatchDetail({
  m,
  demos,
  episode,
}: {
  m: Match;
  demos: State["demos"];
  episode: (ep: Episode) => void;
}) {
  const [detail, set] = useState<unknown>(null);
  useEffect(() => {
    get("match/" + m.id)
      .then(set)
      .catch((e) => set(e.message));
  }, [m.id]);
  return (
    <Panel
      title={"Разбор · " + date(m.finished)}
      side={<span className="tag">FACEIT</span>}
    >
      <small>{m.id}</small>
      {m.maps.map((v, i) => (
        <div key={i}>
          <h3>{v.map}</h3>
          <div className="tiles">
            {Object.entries(v)
              .filter(([k, x]) => k !== "map" && x != null)
              .map(([k, x]) => (
                <div key={k}>
                  <small>{k}</small>
                  <b>{fmt(x)}</b>
                </div>
              ))}
          </div>
        </div>
      ))}
      {demos.map((d) => (
        <button key={d.id} onClick={() => episode({ demo: d.id })}>
          {d.name} · Разбор раундов ↗
        </button>
      ))}
      {!demos.length && (
        <p className="hint">
          Для таймлайна привяжите запись к матчу в разделе «Демозаписи».
        </p>
      )}
      <details>
        <summary>Карточка FACEIT</summary>
        <pre>{JSON.stringify(detail, null, 2)}</pre>
      </details>
    </Panel>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
