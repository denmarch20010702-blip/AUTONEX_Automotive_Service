import { createContext } from "react";

// Вынесено из NotificationContext.tsx (2026-09-18) — см. api/eventsContext.ts
// за тем же приёмом и объяснением (react-refresh/only-export-components).
export interface NotificationValue {
  clientPendingCount: number;
  stationActionableCount: number;
}

export const NotificationContext = createContext<NotificationValue>({
  clientPendingCount: 0,
  stationActionableCount: 0,
});
