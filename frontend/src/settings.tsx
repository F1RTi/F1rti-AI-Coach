import { useState } from "react";
import type { Options, State } from "./types";
import { post } from "./net";
import { Panel } from "./ui";
export type Run = (
  action: () => Promise<unknown>,
  message?: string,
) => Promise<void>;
export function Settings({ s, run }: { s: State; run: Run }) {
  const [o, set] = useState<Options>(s.options),
    [f, keyF] = useState(""),
    [a, keyA] = useState(""),
    [erase, confirm] = useState(""),
    [backup, setBackup] = useState("");
  function field<K extends keyof Options>(key: K, value: Options[K]) {
    set({ ...o, [key]: value });
  }
  const save = () =>
    run(async () => {
      await post("settings", { ...o, paused: s.options.paused });
      if (f) {
        await post("key/faceit", { key: f });
        keyF("");
      }
      if (a) {
        await post("key/ai", { key: a });
        keyA("");
      }
    }, "Настройки сохранены");
  return (
    <>
      <div className="columns">
        <Panel title="Подключения">
          <label>
            Ключ FACEIT Data API{" "}
            <small>{s.keys.faceit ? "Сохранён" : "Не задан"}</small>
            <input
              type="password"
              autoComplete="new-password"
              value={f}
              onChange={(e) => keyF(e.target.value)}
              placeholder="Ввести API-ключ"
            />
          </label>
          <p className="hint">
            В кабинете разработчика FACEIT создайте приложение и серверный
            API-ключ. При сохранении начнётся загрузка матчей F1rti.{" "}
            <a
              href="https://developers.faceit.com/"
              target="_blank"
              rel="noreferrer"
            >
              Кабинет FACEIT ↗
            </a>
          </p>
          {s.keys.faceit && (
            <button
              onClick={() =>
                run(() => post("key/faceit", { key: "" }), "Ключ удалён")
              }
            >
              Удалить ключ FACEIT
            </button>
          )}
          <label>
            Адрес AI API
            <input
              value={o.ai_base}
              onChange={(e) => field("ai_base", e.target.value)}
            />
          </label>
          <label>
            Модель
            <input
              value={o.model}
              onChange={(e) => field("model", e.target.value)}
            />
          </label>
          <label>
            Ключ AI <small>{s.keys.ai ? "Сохранён" : "По желанию"}</small>
            <input
              type="password"
              value={a}
              autoComplete="new-password"
              onChange={(e) => keyA(e.target.value)}
            />
          </label>
          <p className="hint">
            По кнопке «Обновить приоритеты» провайдер получит названия
            наблюдений, источники и размеры выборок. При смене адреса введите
            ключ заново.
          </p>
          {s.keys.ai && (
            <button
              onClick={() =>
                run(() => post("key/ai", { key: "" }), "Ключ удалён")
              }
            >
              Удалить ключ AI
            </button>
          )}
        </Panel>
        <Panel title="Локальное приложение">
          <label>
            Папка наблюдения
            <input
              value={o.watch}
              onChange={(e) => field("watch", e.target.value)}
              placeholder="C:\Демозаписи"
            />
          </label>
          <label>
            SteamID64 для анализа демо
            <input
              value={o.steam_id}
              onChange={(e) => field("steam_id", e.target.value)}
              placeholder="Автоматически из FACEIT"
            />
          </label>
          {(
            [
              ["sync_minutes", "Синхронизация, мин"],
              ["session_gap", "Перерыв между сессиями, мин"],
              ["minutes", "Занятие, мин"],
            ] as const
          ).map(([k, l]) => (
            <label key={k}>
              {l}
              <input
                type="number"
                value={o[k]}
                onChange={(e) => field(k, Number(e.target.value))}
              />
            </label>
          ))}
          {(
            [
              ["notifications", "Уведомления в Windows"],
              ["autostart", "Запуск в трее при входе в Windows"],
            ] as const
          ).map(([k, l]) => (
            <label key={k} className="check">
              <input
                type="checkbox"
                checked={o[k]}
                onChange={(e) => field(k, e.target.checked)}
              />
              {l}
            </label>
          ))}
          <p className="hint">Язык интерфейса · Русский</p>
        </Panel>
      </div>
      <button className="primary" onClick={save}>
        Сохранить настройки
      </button>
      <Panel title="Хранение данных">
        <p>{s.root}</p>
        <button
          onClick={() =>
            run(async () => setBackup((await post("backup")).path))
          }
        >
          Создать копию базы
        </button>
        {backup && <p>Копия базы · {backup}</p>}
        <details>
          <summary>Удаление локальных данных</summary>
          <p>
            Будут удалены статистика, импортированные копии демо, планы и ключи.
            Сначала приостановите анализ. Введите УДАЛИТЬ для подтверждения.
          </p>
          <input value={erase} onChange={(e) => confirm(e.target.value)} />
          <button
            disabled={erase !== "УДАЛИТЬ" || !s.options.paused}
            onClick={() =>
              run(async () => {
                await post("reset", { confirm: erase });
                location.reload();
              })
            }
          >
            Удалить данные
          </button>
        </details>
      </Panel>
    </>
  );
}
