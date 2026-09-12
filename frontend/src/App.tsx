import { useEffect, useState } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import { API_URL } from "./api/client";
import { BookingPage } from "./pages/BookingPage";
import { StationPage } from "./pages/StationPage";

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

function App() {
  return (
    <BrowserRouter>
      <div style={{ fontFamily: "sans-serif", padding: "2rem", maxWidth: 800, margin: "0 auto" }}>
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            borderBottom: "1px solid #ddd",
            paddingBottom: "1rem",
            marginBottom: "1.5rem",
          }}
        >
          <nav style={{ display: "flex", gap: "1rem" }}>
            <Link to="/">Запись</Link>
            <Link to="/station">Станция</Link>
          </nav>
          <BackendStatus />
        </header>

        <Routes>
          <Route path="/" element={<BookingPage />} />
          <Route path="/station" element={<StationPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
