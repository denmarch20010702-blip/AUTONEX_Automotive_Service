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
  // храним это по id предложения — каждое согласие клиент всё равно даёт
  // отдельно, но сам визит теперь выбирается ОДИН на все, что не влезло
  // сразу (см. ниже), а не по отдельному окну на каждую услугу — найдено
  // пользователем на практике (2026-09-17): при очереди на посту каждая
  // доп. работа требовала своего отдельного визита, что неудобно.
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

  // Одно общее предложение визита на ВСЕ работы, которым сейчас не хватило
  // места на посту — а не по отдельному мини-календарю на каждую (прямая
  // находка пользователя: неудобно записываться на каждую услугу отдельным
  // окном, когда на посту уже очередь). Работы без услуги в каталоге
  // (service_id === null) в общий визит не входят — их можно только отклонить.
  const visitEntries = Object.entries(needsVisit);
  const schedulable = visitEntries.filter(([, v]) => v.service_id !== null);
  const unschedulable = visitEntries.filter(([, v]) => v.service_id === null);
  const combinedWorkIds = schedulable.map(([workId]) => Number(workId));
  const combinedServiceIds = schedulable.map(([, v]) => v.service_id as number);

  const clearNeedsVisit = (workIds: number[]) => {
    setNeedsVisit((prev) => {
      const next = { ...prev };
      for (const id of workIds) delete next[id];
      return next;
    });
  };

  return (
    <div style={{ fontSize: "0.85rem" }}>
      {error && <div className="error-banner">{error}</div>}
      {works.map((w) => (
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
              {w.status === "approved"
                ? w.execution_started
                  ? "выполняется сейчас"
                  : "принято, в очереди на посту"
                : "отклонено"}
            </span>
          )}
        </div>
      ))}
      {unschedulable.map(([workId]) => (
        <p key={workId} className="error-banner">
          Услуга для одной из доп. работ больше не в каталоге — отдельный визит невозможен, отклоните предложение.
        </p>
      ))}
      {combinedWorkIds.length > 0 && (
        <ScheduleSeparateVisit
          workIds={combinedWorkIds}
          serviceIds={combinedServiceIds}
          onScheduled={() => {
            clearNeedsVisit(combinedWorkIds);
            reload();
          }}
          onCancel={() => clearNeedsVisit(combinedWorkIds)}
          onError={setError}
        />
      )}
    </div>
  );
}
