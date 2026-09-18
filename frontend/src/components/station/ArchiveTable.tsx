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
            <th>Услуга</th>
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
              <td>{entry.services_snapshot.map((s) => s.name).join(", ") || "—"}</td>
              <td>{new Date(entry.start_at).toLocaleString()}</td>
              <td>
                <StatusIndicator status={entry.status} />
              </td>
              {/* Показываем расшифровку наценки парковки: общая сумма остаётся
                  компактной, но оператор может проверить, откуда она взялась. */}
              <td>
                {entry.status === "issued" ? (
                  <>
                    {entry.total_price} ₽
                    {Number(entry.parking_surcharge) > 0 && (
                      <small className="price-breakdown">
                        Услуги {entry.service_price} ₽ + парковка {entry.parking_surcharge} ₽
                      </small>
                    )}
                  </>
                ) : "—"}
              </td>
              <td>{new Date(entry.archived_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
