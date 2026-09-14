import { useEffect, useState } from "react";

import { listAdditionalWorks, respondAdditionalWork, type AdditionalWork } from "../../api/client";
import { NotificationDot } from "../NotificationDot";

// Сторона клиента (B2): видит предложенные доп. работы по своей заявке и
// отвечает — "принять"/"отклонить". Сама доп. работа не начинается, пока
// клиент не ответил; заявка при этом не блокируется (см. AdditionalWorkPanel
// на станции).
export function ClientAdditionalWorks({ bookingId, refreshKey }: { bookingId: number; refreshKey: number }) {
  const [works, setWorks] = useState<AdditionalWork[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = () => {
    listAdditionalWorks(bookingId).then(setWorks).catch((err) => setError(err.message));
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId, refreshKey]);

  const respond = async (id: number, status: "approved" | "declined") => {
    try {
      await respondAdditionalWork(id, status);
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  if (works.length === 0) return null;

  return (
    <div style={{ fontSize: "0.85rem" }}>
      {error && <div className="error-banner">{error}</div>}
      {works.map((w) => (
        <div key={w.id} style={{ marginBottom: "0.25rem" }}>
          <NotificationDot show={w.status === "pending"} title="Требуется ваш ответ" />
          {w.description} ({w.price} ₽)
          {w.status === "pending" ? (
            <span style={{ marginLeft: "0.5rem", display: "inline-flex", gap: "0.4rem" }}>
              <button type="button" className="action-button" onClick={() => respond(w.id, "approved")}>
                Принять
              </button>
              <button
                type="button"
                className="action-button danger"
                onClick={() => respond(w.id, "declined")}
              >
                Отклонить
              </button>
            </span>
          ) : (
            <span style={{ marginLeft: "0.5rem", color: "var(--color-muted)" }}>
              {w.status === "approved" ? "принято" : "отклонено"}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
