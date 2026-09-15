import { useEffect, useState } from "react";

import { listAdditionalWorks, proposeAdditionalWork, type AdditionalWork, type Service } from "../../api/client";
import { formatDuration } from "../../utils/duration";

const STATUS_LABEL: Record<AdditionalWork["status"], string> = {
  pending: "ожидает ответа",
  approved: "согласовано",
  declined: "отклонено",
};

// Согласование доп. работ (B2) — станция предлагает, клиент отвечает в
// своём кабинете. Здесь — сторона станции: список уже предложенного по
// заявке + выбор новой работы кликом из каталога услуг (UI_description.md
// п.19 — без ввода данных вручную; после согласования запускается
// настоящий таймер выполнения, см. app/api/additional_works.py).
export function AdditionalWorkPanel({
  bookingId,
  services,
  refreshKey,
}: {
  bookingId: number;
  services: Service[];
  refreshKey: number;
}) {
  const [works, setWorks] = useState<AdditionalWork[]>([]);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyServiceId, setBusyServiceId] = useState<number | null>(null);

  const reload = () => {
    listAdditionalWorks(bookingId).then(setWorks).catch((err) => setError(err.message));
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId, refreshKey]);

  const propose = async (serviceId: number) => {
    setBusyServiceId(serviceId);
    setError(null);
    try {
      await proposeAdditionalWork(bookingId, { service_id: serviceId });
      setPicking(false);
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyServiceId(null);
    }
  };

  return (
    <div style={{ fontSize: "0.85rem" }}>
      {error && <div className="error-banner">{error}</div>}
      {works.map((w) => (
        <div key={w.id}>
          {w.description} ({w.price} ₽, {formatDuration(w.duration_minutes)}) —{" "}
          <span
            style={{
              color:
                w.status === "approved"
                  ? "var(--color-primary-active)"
                  : w.status === "declined"
                    ? "var(--color-danger)"
                    : "var(--color-muted)",
            }}
          >
            {STATUS_LABEL[w.status]}
          </span>
        </div>
      ))}
      {!picking && (
        <button type="button" className="ghost-button" onClick={() => setPicking(true)}>
          + предложить доп. работу
        </button>
      )}
      {picking && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", marginTop: "0.3rem", minWidth: 180 }}>
          {services.length === 0 && <p className="panel-empty">В каталоге пока нет услуг.</p>}
          {services.map((s) => (
            <button
              key={s.id}
              type="button"
              className="ghost-button"
              style={{ textAlign: "left" }}
              disabled={busyServiceId !== null}
              onClick={() => propose(s.id)}
            >
              {s.name} — {s.price} ₽, {formatDuration(s.duration_minutes)}
            </button>
          ))}
          <button type="button" className="ghost-button" onClick={() => setPicking(false)}>
            Отмена
          </button>
        </div>
      )}
    </div>
  );
}
