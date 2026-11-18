import React from "react";
import type { State, Match, Metrics } from "./types";
export const labels: Record<string, string> = {
  kd: "K/D",
  kr: "K/R",
  adr: "ADR",
  hs: "Headshots, %",
  mvp: "MVP",
  winrate: "Победы, %",
  kills: "Убийства",
  deaths: "Смерти",
  assists: "Помощь",
  streak: "Текущая серия",
  variability: "Разброс ADR",
  entries: "Первые дуэли",
  opening_deaths: "Первые смерти",
  entry_success: "Успех первых дуэлей, %",
  trade_kills: "Размены",
  traded_deaths: "Разменянные смерти",
  flash_assists: "Флеш-ассисты",
  utility_damage: "Урон гранатами",
  clutches: "Попытки клатча",
  clutch_success: "Успех клатчей, %",
  kast: "KAST, %",
  damage: "Урон",
  opening_kills: "Первые убийства",
  clutch_wins: "Выигранные клатчи",
  advantage_deaths: "Смерти в преимуществе",
  kast_round: "Раунды KAST",
};
export const fmt = (n: unknown) =>
  n == null
    ? "—"
    : typeof n === "number"
      ? n.toLocaleString("ru-RU", { maximumFractionDigits: 2 })
      : String(n);
export const date = (n: number) =>
  new Date(n * 1000).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
export const today = () => new Date().toLocaleDateString("sv-SE");
export function Icon({ name, size = 19 }: { name: string; size?: number }) {
  const shapes: Record<string, React.ReactNode> = {
    home: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.4" />
        <rect x="14" y="3" width="7" height="7" rx="1.4" />
        <rect x="3" y="14" width="7" height="7" rx="1.4" />
        <rect x="14" y="14" width="7" height="7" rx="1.4" />
      </>
    ),
    stats: <path d="M3 20h18M6 16V9m6 7V4m6 12v-5" />,
    match: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="M7 10h4m-4 4h7" />
      </>
    ),
    demo: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="m10 9 5 3-5 3z" />
      </>
    ),
    coach: (
      <>
        <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" />
      </>
    ),
    training: (
      <>
        <path d="m6 5 13 13M3 8l5-5m8 18 5-5M5 11l6-6m2 14 6-6" />
      </>
    ),
    report: (
      <>
        <path d="M6 3h9l4 4v14H6zM9 12h7m-7 4h5" />
      </>
    ),
    settings: (
      <>
        <path d="M4 6h16M4 12h16M4 18h16" />
        <path strokeWidth="4" d="M8 4v4m8 2v4m-6 2v4" />
      </>
    ),
    sync: (
      <>
        <path d="M20 9A8 8 0 0 0 6 6L3 9m0-5v5h5m-4 6a8 8 0 0 0 14 3l3-3m0 5v-5h-5" />
      </>
    ),
    arrow: <path d="M6 12h12m-5-5 5 5-5 5" />,
    target: (
      <>
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="5" />
        <circle cx="12" cy="12" r="1" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v6l4 2" />
      </>
    ),
    folder: <path d="M3 7V5h6l2 2h10v12H3z" />,
    link: (
      <>
        <path d="m8 16 8-8m-6 0 2-2a4 4 0 0 1 6 6l-2 2m-2 2-2 2a4 4 0 0 1-6-6l2-2" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {shapes[name] || shapes.target}
    </svg>
  );
}
export function Panel({
  title,
  side,
  children,
}: {
  title: string;
  side?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panelhead">
        <h2>{title}</h2>
        {side}
      </header>
      {children}
    </section>
  );
}
export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="empty">{children}</p>;
}
export function MetricTable({
  metrics,
  delta,
}: {
  metrics: Metrics;
  delta?: Record<string, number | null>;
}) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>Показатель</th>
            <th>Значение</th>
            {delta && <th>Δ периода</th>}
            <th>Выборка</th>
            <th>Метод</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(metrics).map(([k, m]) => (
            <tr key={k}>
              <td>{labels[k] || k}</td>
              <td className="num">{fmt(m.value)}</td>
              {delta && (
                <td
                  className={
                    delta[k] &&
                    [
                      "winrate",
                      "kd",
                      "adr",
                      "kr",
                      "hs",
                      "entry_success",
                      "clutch_success",
                    ].includes(k)
                      ? delta[k]! > 0
                        ? "green"
                        : "red"
                      : ""
                  }
                >
                  {delta[k] != null && delta[k]! > 0 ? "+" : ""}
                  {fmt(delta[k])}
                </td>
              )}
              <td>{m.sample}</td>
              <td className="muted">{m.method}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function MatchList({
  rows,
  open,
}: {
  rows: Match[];
  open: (id: string) => void;
}) {
  return rows.length ? (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>Дата</th>
            <th>Карта</th>
            <th>Результат</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.id}>
              <td>{date(m.finished)}</td>
              <td>{m.maps.map((v) => v.map).join(", ") || "—"}</td>
              <td className={m.won === 1 ? "green" : m.won === 0 ? "red" : ""}>
                {m.won === 1 ? "Победа" : m.won === 0 ? "Поражение" : "—"}
              </td>
              <td>
                <button className="textbtn" onClick={() => open(m.id)}>
                  Разбор ↗
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty>Матчи появятся после синхронизации с FACEIT.</Empty>
  );
}
export function Chart({ points }: { points: State["goal"]["history"] }) {
  const min = Math.min(...points.map((p) => p.elo)),
    max = Math.max(...points.map((p) => p.elo));
  const x = (i: number) =>
    points.length < 2
      ? 300
      : 28 +
        ((points[i].at - points[0].at) /
          (points.at(-1)!.at - points[0].at || 1)) *
          544;
  const y = (n: number) =>
    max === min ? 65 : 112 - ((n - min) / (max - min)) * 94;
  return (
    <div className="chart">
      <svg
        viewBox="0 0 600 135"
        role="img"
        aria-label="История наблюдений ELO"
        preserveAspectRatio="none"
      >
        {[20, 55, 90, 125].map((v) => (
          <path
            key={v}
            d={"M0 " + v + "H600"}
            stroke="#35383b"
            strokeDasharray="3 5"
          />
        ))}
        {points.length > 0 && (
          <>
            <polyline
              fill="none"
              stroke="#ff762f"
              strokeWidth="3"
              points={points.map((p, i) => x(i) + "," + y(p.elo)).join(" ")}
            />
            <circle
              cx={x(points.length - 1)}
              cy={y(points.at(-1)!.elo)}
              r="4"
              fill="#ff762f"
            />
          </>
        )}
      </svg>
      {!points.length && (
        <span>История рейтинга появится после подключения</span>
      )}
    </div>
  );
}
