import { useEffect, useState } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import { API_URL } from "./api/client";
import { EventsProvider } from "./api/events";
import { CabinetPage } from "./pages/CabinetPage";
import { BookingPage } from "./pages/BookingPage";
import { StationPage } from "./pages/StationPage";
import { ClientSessionProvider, useClientSession } from "./session/ClientSessionContext";
import { NotificationProvider, useNotifications } from "./session/NotificationContext";

function BackendStatus() {
  const [status, setStatus] = useState<"checking" | "ok" | "error">("checking");

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((response) => (response.ok ? response.json() : Promise.reject(response)))
      .then(() => setStatus("ok"))
      .catch(() => setStatus("error"));
  }, []);

  return (
    <span>
      Backend: {status === "checking" && "проверка..."}
      {status === "ok" && "✅ доступен"}
      {status === "error" && "❌ недоступен"}
    </span>
  );
}

// Мини-виджет аккаунта в шапке — по всему приложению видно, кто вошёл,
// без захода в кабинет. Сама авторизация/переключение аккаунтов — в
// личном кабинете (buisness/UI_description.md).
function AccountWidget() {
  const { client } = useClientSession();
  return (
    <Link to="/cabinet" style={{ fontSize: "0.9rem" }}>
      {client ? `👤 ${client.name}` : "Войти"}
    </Link>
  );
}

// UI_description.md п.17: маленькая красная точка на ссылке навигации,
// пока есть непрочитанное уведомление.
function NotificationDot({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: "var(--color-danger)",
        marginLeft: "0.35rem",
        verticalAlign: "middle",
      }}
    />
  );
}

function NavLinks() {
  const { clientPendingCount, stationHasUnseen } = useNotifications();
  return (
    <nav className="app-nav">
      <Link to="/">Запись</Link>
      <Link to="/cabinet">
        Личный кабинет
        <NotificationDot show={clientPendingCount > 0} />
      </Link>
      <Link to="/station">
        Станция
        <NotificationDot show={stationHasUnseen} />
      </Link>
    </nav>
  );
}

function AppShell() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <NavLinks />
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <AccountWidget />
          <BackendStatus />
        </div>
      </header>

      <Routes>
        <Route path="/" element={<BookingPage />} />
        <Route path="/cabinet" element={<CabinetPage />} />
        <Route path="/station" element={<StationPage />} />
      </Routes>
    </div>
  );
}

function App() {
  return (
    <ClientSessionProvider>
      <EventsProvider>
        <NotificationProvider>
          <BrowserRouter>
            <AppShell />
          </BrowserRouter>
        </NotificationProvider>
      </EventsProvider>
    </ClientSessionProvider>
  );
}

export default App;
