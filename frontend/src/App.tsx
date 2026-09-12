import { useEffect, useState } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import { API_URL } from "./api/client";
import { CabinetPage } from "./pages/CabinetPage";
import { BookingPage } from "./pages/BookingPage";
import { StationPage } from "./pages/StationPage";
import { ClientSessionProvider, useClientSession } from "./session/ClientSessionContext";

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

function App() {
  return (
    <ClientSessionProvider>
      <BrowserRouter>
        <div className="app-shell">
          <header className="app-header">
            <nav className="app-nav">
              <Link to="/">Запись</Link>
              <Link to="/cabinet">Личный кабинет</Link>
              <Link to="/station">Станция</Link>
            </nav>
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
      </BrowserRouter>
    </ClientSessionProvider>
  );
}

export default App;
