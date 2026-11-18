import { fmt, labels, Empty } from "./ui";
const names: Record<string, string> = {
  ...labels,
  key: "Показатель",
  value: "Значение",
  source: "Источник",
  method: "Расчёт",
  available: "Доступно",
  updated: "Обновлено",
  period: "Раундов",
  won: "Исход",
  position: "Координаты",
  round: "Раунд",
  tick: "Тик",
  event: "Событие",
  weapon: "Оружие",
  rounds: "Раунды",
  shots: "Применения",
  hits: "Попадания",
  duels: "Дуэли",
  distance: "Дистанция, ед.",
  first_hit_ticks: "От первого урона, тики",
  steamid: "SteamID",
  team_num: "Сторона",
  name: "Игрок",
  current_equip_value: "Снаряжение, $",
  balance: "Деньги, $",
  health: "Здоровье",
  wins: "Победы",
  blinds: "Ослепления",
  blind_seconds: "Суммарно, с",
  assists: "Помощь",
};
function object(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
function cell(key: string, v: unknown): string {
  if (v == null) return "—";
  if (key === "team_num") return v === 2 ? "T" : v === 3 ? "CT" : fmt(v);
  if (key === "won") return v ? "Победа" : "Поражение";
  if (key === "updated" && typeof v === "number")
    return new Date(v * 1000).toLocaleString("ru-RU");
  if (typeof v === "boolean") return v ? "Да" : "Нет";
  if (Array.isArray(v)) return v.map((n) => fmt(n)).join(", ");
  return fmt(v);
}
export function Telemetry({
  data,
  index = "Показатель",
  columns,
}: {
  data: unknown;
  index?: string;
  columns?: string[];
}) {
  if (
    Array.isArray(data) &&
    data.length &&
    data.every((v) => typeof v === "string")
  )
    return <p className="hint">{data.join(" · ")}</p>;
  const rows: Record<string, unknown>[] = Array.isArray(data)
    ? data.filter(object)
    : object(data)
      ? Object.entries(data).map(([key, v]) => ({
          key: labels[key] || key,
          ...(object(v) ? v : { value: v }),
        }))
      : [];
  if (!rows.length) return <Empty>Нет наблюдений.</Empty>;
  const fields =
    columns || Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            {fields.map((k) => (
              <th key={k}>{k === "key" ? index : names[k] || k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {fields.map((k) => (
                <td key={k}>{cell(k, row[k])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
