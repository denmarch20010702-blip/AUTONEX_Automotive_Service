import { useContext } from "react";

import { ClientSessionContext, type ClientSessionValue } from "./clientSessionStore";

export function useClientSession(): ClientSessionValue {
  const ctx = useContext(ClientSessionContext);
  if (!ctx) throw new Error("useClientSession must be used within ClientSessionProvider");
  return ctx;
}
