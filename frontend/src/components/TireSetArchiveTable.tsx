import type { TireSetArchiveEntry } from "../api/client";
import { formatSlotLabel } from "./booking/SlotPicker";

// Журнал приёма/выдачи шин (UI_description.md п.28) — выданный комплект
// переезжает сюда и удаляется из живой `tire-sets`, тот же принцип, что и
// у журнала заявок (ArchiveTable). Тот же стиль таблицы, что и "Все заявки".
export function TireSetArchiveTable({ entries }: { entries: TireSetArchiveEntry[] }) {
  if (entries.length === 0) {
    return <p className="panel-empty">Журнал хранения шин пока пуст.</p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Клиент</th>
            <th>Автомобиль</th>
            <th>Принято на хранение</th>
            <th>Выдано</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id}>
              <td>
                <div>{entry.client_name}</div>
                <div style={{ fontSize: "0.8em", color: "var(--color-muted)" }}>{entry.client_email}</div>
              </td>
              <td>
                {entry.car_make} {entry.car_model}
              </td>
              <td>{formatSlotLabel(entry.stored_at)}</td>
              <td>{formatSlotLabel(entry.issued_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
