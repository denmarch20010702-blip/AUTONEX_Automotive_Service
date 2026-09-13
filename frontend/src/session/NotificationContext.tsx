import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { getPendingAdditionalWorksCount } from "../api/client";
import { useBookingEvents } from "../api/events";
import { useClientSession } from "./ClientSessionContext";

// UI_description.md п.17: красная точка у "Личный кабинет" и у "Станция" в
// шапке, пока не прочитано/не отработано новое событие.
// - У клиента точка держится на РЕАЛЬНОМ количестве неотвеченных предложений
//   доп. работы — гаснет сама, когда он их примет/отклонит (не просто
//   зайдёт в кабинет и уйдёт, не ответив).
// - У станции точка — более простой принцип "есть новое, которое ещё не
//   видели": загорается на новую заявку/смену статуса, гаснет при заходе на
//   /station (у станции нет единого действия вроде "принять/отклонить" на
//   уровне всего экрана, поэтому применяем правило "увидел — погасло").
interface NotificationValue {
  clientPendingCount: number;
  stationHasUnseen: boolean;
  markStationSeen: () => void;
}

const NotificationContext = createContext<NotificationValue>({
  clientPendingCount: 0,
  stationHasUnseen: false,
  markStationSeen: () => {},
});

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { client } = useClientSession();
  const events = useBookingEvents();
  const [clientPendingCount, setClientPendingCount] = useState(0);
  const [stationHasUnseen, setStationHasUnseen] = useState(false);

  const reloadPendingCount = () => {
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

  useEffect(reloadPendingCount, [client]);

  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[0];
    if (latest.type === "additional_work_proposed" || latest.type === "additional_work_responded") {
      reloadPendingCount();
    }
    if (latest.type === "booking_created" || latest.type === "booking_status_changed") {
      setStationHasUnseen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  const markStationSeen = () => setStationHasUnseen(false);

  return (
    <NotificationContext.Provider value={{ clientPendingCount, stationHasUnseen, markStationSeen }}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications(): NotificationValue {
  return useContext(NotificationContext);
}
