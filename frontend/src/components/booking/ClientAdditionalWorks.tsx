import { useEffect, useState } from "react";

import {
  ApiError,
  listAdditionalWorks,
  respondAdditionalWork,
  type AdditionalWork,
  type NeedsSeparateVisit,
} from "../../api/client";
import { formatDuration } from "../../utils/duration";
import { NotificationDot } from "../NotificationDot";
import { ScheduleSeparateVisit } from "./ScheduleSeparateVisit";

// Сторона клиента (B2): видит предложенные доп. работы по своей заявке и
// отвечает — "принять"/"отклонить". Сама доп. работа не начинается, пока
// клиент не ответил; заявка при этом не блокируется (см. AdditionalWorkPanel
// на станции).
export function ClientAdditionalWorks({ bookingId, refreshKey }: { bookingId: number; refreshKey: number }) {
  const [works, setWorks] = useState<AdditionalWork[]>([]);
  const [error, setError] = useState<string | null>(null);
  // UI_description.md п.37: если одобрить сразу не получилось (мест нет —
  // пост занят следующей заявкой), backend отвечает `needs_separate_visit` —
  // вместо голой ошибки показываем мини-календарь для отдельного визита,
  // храним это по id предложения, чтобы каждое могло показывать свой.
  const [needsVisit, setNeedsVisit] = useState<Record<number, NeedsSeparateVisit>>({});

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
      setNeedsVisit((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      reload();
    } catch (err) {
      if (err instanceof ApiError && err.detail && (err.detail as NeedsSeparateVisit).needs_separate_visit) {
        setNeedsVisit((prev) => ({ ...prev, [id]: err.detail as NeedsSeparateVisit }));
        return;
      }
      setError((err as Error).message);
    }
  };

  if (works.length === 0) return null;

  return (
    <div style={{ fontSize: "0.85rem" }}>
      {error && <div className="error-banner">{error}</div>}
      {works.map((w) => {
        const visitNeeded = needsVisit[w.id];
        return (
          <div key={w.id} style={{ marginBottom: "0.25rem" }}>
            <NotificationDot show={w.status === "pending"} title="Требуется ваш ответ" />
            {w.description} ({w.price} ₽, {formatDuration(w.duration_minutes)})
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
            {visitNeeded && visitNeeded.service_id !== null && (
              <ScheduleSeparateVisit
                workId={w.id}
                serviceId={visitNeeded.service_id}
                onScheduled={() => {
                  setNeedsVisit((prev) => {
                    const next = { ...prev };
                    delete next[w.id];
                    return next;
                  });
                  reload();
                }}
                onCancel={() =>
                  setNeedsVisit((prev) => {
                    const next = { ...prev };
                    delete next[w.id];
                    return next;
                  })
                }
                onError={setError}
              />
            )}
            {visitNeeded && visitNeeded.service_id === null && (
              <p className="error-banner">
                Услуга для этой доп. работы больше не в каталоге — отдельный визит невозможен, отклоните предложение.
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
