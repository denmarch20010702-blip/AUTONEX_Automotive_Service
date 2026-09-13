import type { ArchivedBooking } from "../../api/client";
import { StatusIndicator } from "../StatusIndicator";

// Журнал завершённых/отменённых заявок — они больше не в активном списке,
// но не удалены совсем (по прямой просьбе пользователя, см.
// buisness/ARCHITECTURE.md). Показывает снимок на момент архивации, не
// живые данные — клиент/машина могли с тех пор измениться.
export function ArchiveTable({ entries }: { entries: ArchivedBooking[] }) {
  if (entries.length === 0) {
    return <p className="panel-empty">Журнал пока пуст.</p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>ID заявки</th>
            <th>Клиент</th>
            <th>Автомобиль</th>
            <th>Когда была запись</th>
            <th>Статус</th>
            <th>Сумма</th>
            <th>Архивировано</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id}>
              <td>{entry.original_booking_id}</td>
              <td>
                {entry.client_name} ({entry.client_email})
              </td>
              <td>
                {entry.car_make} {entry.car_model}
              </td>
              <td>{new Date(entry.start_at).toLocaleString()}</td>
              <td>
                <StatusIndicator status={entry.status} />
              </td>
              {/* Сумма реально оплачена только за выданные заявки (issued
                  кредитует StationStats) — для отменённых показывать сумму
                  рядом с красным индикатором вводит в заблуждение, будто
                  деньги были получены. Найдено на практике 2026-09-13. Сумма
                  включает согласованные доп. работы сверх услуги (п.14). */}
              <td>{entry.status === "issued" ? `${entry.total_price} ₽` : "—"}</td>
              <td>{new Date(entry.archived_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
