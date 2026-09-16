import { useEffect, useState } from "react";

import { listAdditionalWorks, proposeAdditionalWork, type AdditionalWork, type Service } from "../../api/client";
import { formatDuration } from "../../utils/duration";

const STATUS_LABEL: Record<AdditionalWork["status"], string> = {
  pending: "ожидает ответа",
  approved: "согласовано",
  declined: "отклонено",
};

// C2 (2026-09-15): очередь задач на посту — согласованная доп. работа не
// начинает выполняться сама в момент согласования, а становится следующей
// в очереди (execution_started=false) и запускается только когда до неё
// реально дойдёт черёд (resolve_next_step в robot_timer.py). Различаем это
// в UI, а не показываем одинаковое "согласовано" для обеих фаз.
function statusLabel(w: AdditionalWork): string {
  if (w.status === "approved") {
    return w.execution_started ? "выполняется сейчас" : "в очереди на посту";
  }
  return STATUS_LABEL[w.status];
}

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
      {/* Найдено пользователем (2026-09-16): при нескольких доп. работах
          список растягивался в длинный столбик — каждая ИИ-строка занимала
          две строки текста (причина под ней) плюс повторяла марку/модель/
          пробег машины в самой причине (убрано в ai_diagnostics.py). Теперь
          одна компактная строка на работу; причина ИИ доступна по наведению
          на бейдж (title), а не отдельной строкой под каждой работой. */}
      {works.map((w) => (
        <div key={w.id} style={{ lineHeight: 1.5 }}>
          {/* C5 (2026-09-16): пометка "от ИИ" + причина/уверенность — только
              здесь, на станции (оверсайт мастера, пока он в контуре), НЕ в
              кабинете клиента (см. ClientAdditionalWorks.tsx — там этого нет
              намеренно, клиенту не важно и не нужно знать источник). */}
          {w.proposed_by === "ai" && (
            <span
              title={w.ai_reason ?? undefined}
              style={{
                display: "inline-block",
                marginRight: "0.35rem",
                padding: "0.05rem 0.4rem",
                borderRadius: 999,
                background: "var(--color-primary)",
                fontSize: "0.72rem",
              }}
            >
              🤖 ИИ{w.ai_confidence !== null ? ` ${Math.round(w.ai_confidence * 100)}%` : ""}
            </span>
          )}
          {w.description} ({w.price} ₽, {formatDuration(w.duration_minutes)}) —{" "}
          <span
            style={{
              color:
                w.status === "approved"
                  ? "var(--color-primary-active)"
                  : w.status === "declined"
                    ? "var(--color-danger)"
                    : "var(--color-muted)",
              fontWeight: w.status === "approved" && w.execution_started ? 700 : 400,
            }}
          >
            {statusLabel(w)}
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
