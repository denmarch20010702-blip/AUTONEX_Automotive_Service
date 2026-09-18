import { createContext } from "react";

import type { ClientInfo } from "../api/client";

// Вынесено из ClientSessionContext.tsx (2026-09-18) — см. api/eventsContext.ts
// за тем же приёмом и объяснением (react-refresh/only-export-components).
export interface ClientSessionValue {
  client: ClientInfo | null;
  knownClients: ClientInfo[];
  login: (client: ClientInfo) => void;
  logout: () => void;
  switchTo: (clientId: number) => void;
  forget: (clientId: number) => void;
}

export const ClientSessionContext = createContext<ClientSessionValue | null>(null);
