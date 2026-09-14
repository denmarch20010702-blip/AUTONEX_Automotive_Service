import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { getPendingAdditionalWorksCount, getStationActionableCount } from "../api/client";
import { useBookingEvents } from "../api/events";
import { useClientSession } from "./ClientSessionContext";

// UI_description.md п.17/22: красная точка у "Личный кабинет" и у "Станция"
// в шапке держится на РЕАЛЬНОМ количестве вещей, требующих решения — не на
// разовом флаге "было новое событие, погашенном простым заходом на
// страницу" (это и было явно найденной ошибкой: точка гасла от перехода
// между кабинетами, а не от реально принятого решения). Оба счётчика
// пересчитываются с backend'а при монтировании и при каждом релевантном
// SSE-событии, поэтому сами падают до 0, когда решения приняты, и сами
// растут, если появилось новое.
interface NotificationValue {
  clientPendingCount: number;
  stationActionableCount: number;
}

const NotificationContext = createContext<NotificationValue>({
  clientPendingCount: 0,
  stationActionableCount: 0,
});

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { client } = useClientSession();
  const events = useBookingEvents();
  const [clientPendingCount, setClientPendingCount] = useState(0);
  const [stationActionableCount, setStationActionableCount] = useState(0);

  const reloadClientPendingCount = () => {
    if (!client) {
      setClientPendingCount(0);
      return;
    }
    getPendingAdditionalWorksCount(client.id)
      .then(setClientPendingCount)
      .catch(() => {
        /* точка — не критичная функциональность, тихо оставляем как было */
      });
  };

  const reloadStationActionableCount = () => {
    getStationActionableCount()
      .then(setStationActionableCount)
      .catch(() => {
        /* точка — не критичная функциональность, тихо оставляем как было */
      });
  };

  useEffect(reloadClientPendingCount, [client]);
  useEffect(reloadStationActionableCount, []);

  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[0];
    if (latest.type === "additional_work_proposed" || latest.type === "additional_work_responded") {
      reloadClientPendingCount();
    }
    if (
      latest.type === "booking_created" ||
      latest.type === "booking_status_changed" ||
      latest.type === "booking_rescheduled"
    ) {
      reloadStationActionableCount();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  return (
    <NotificationContext.Provider value={{ clientPendingCount, stationActionableCount }}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications(): NotificationValue {
  return useContext(NotificationContext);
}
