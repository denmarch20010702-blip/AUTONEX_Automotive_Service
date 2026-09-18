import { useContext } from "react";

import { NotificationContext, type NotificationValue } from "./notificationStore";

export function useNotifications(): NotificationValue {
  return useContext(NotificationContext);
}
