import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { getClient, type ClientInfo } from "../api/client";

const KNOWN_KEY = "autonex.knownClients";
const ACTIVE_KEY = "autonex.activeClientId";

interface ClientSessionValue {
  client: ClientInfo | null;
  knownClients: ClientInfo[];
  login: (client: ClientInfo) => void;
  logout: () => void;
  switchTo: (clientId: number) => void;
  forget: (clientId: number) => void;
}

const ClientSessionContext = createContext<ClientSessionValue | null>(null);

function loadKnown(): ClientInfo[] {
  try {
    const raw = localStorage.getItem(KNOWN_KEY);
    return raw ? (JSON.parse(raw) as ClientInfo[]) : [];
  } catch {
    return [];
  }
}

function loadActiveId(): number | null {
  try {
    const raw = localStorage.getItem(ACTIVE_KEY);
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}

// Сессия клиента без пароля (см. ARCHITECTURE.md) — здесь просто "кто сейчас
// активен" на этом браузере, хранится в localStorage. "Аккаунт" — это просто
// клиент, найденный/созданный по email; несколько аккаунтов на одном
// браузере — это несколько таких клиентов в knownClients с возможностью
// переключения без повторного ввода email (buisness/UI_description.md).
export function ClientSessionProvider({ children }: { children: ReactNode }) {
  const [knownClients, setKnownClients] = useState<ClientInfo[]>(() => loadKnown());
  const [activeId, setActiveId] = useState<number | null>(() => loadActiveId());

  useEffect(() => {
    localStorage.setItem(KNOWN_KEY, JSON.stringify(knownClients));
  }, [knownClients]);

  useEffect(() => {
    if (activeId === null) localStorage.removeItem(ACTIVE_KEY);
    else localStorage.setItem(ACTIVE_KEY, String(activeId));
  }, [activeId]);

  useEffect(() => {
    // Активный клиент мог быть удалён на сервере вручную (см. кнопку
    // удаления услуг на станции — для клиентов подобной кнопки пока нет,
    // но проверка на будущее и на случай ручного вмешательства в БД) —
    // тихо разлогиниваем, а не показываем сломанный интерфейс.
    if (activeId === null) return;
    getClient(activeId).catch(() => setActiveId(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const client = useMemo(
    () => knownClients.find((c) => c.id === activeId) ?? null,
    [knownClients, activeId],
  );

  const login = (newClient: ClientInfo) => {
    setKnownClients((prev) => [...prev.filter((c) => c.id !== newClient.id), newClient]);
    setActiveId(newClient.id);
  };

  const logout = () => setActiveId(null);

  const switchTo = (clientId: number) => setActiveId(clientId);

  const forget = (clientId: number) => {
    setKnownClients((prev) => prev.filter((c) => c.id !== clientId));
    if (activeId === clientId) setActiveId(null);
  };

  return (
    <ClientSessionContext.Provider
      value={{ client, knownClients, login, logout, switchTo, forget }}
    >
      {children}
    </ClientSessionContext.Provider>
  );
}

export function useClientSession(): ClientSessionValue {
  const ctx = useContext(ClientSessionContext);
  if (!ctx) throw new Error("useClientSession must be used within ClientSessionProvider");
  return ctx;
}
