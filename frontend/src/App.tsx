import { useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function App() {
  const [backendStatus, setBackendStatus] = useState<"checking" | "ok" | "error">("checking");

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((response) => (response.ok ? response.json() : Promise.reject(response)))
      .then(() => setBackendStatus("ok"))
      .catch(() => setBackendStatus("error"));
  }, []);

  return (
    <div style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>Станция техобслуживания</h1>
      <p>
        Backend:{" "}
        {backendStatus === "checking" && "проверка..."}
        {backendStatus === "ok" && "✅ доступен"}
        {backendStatus === "error" && "❌ недоступен"}
      </p>
    </div>
  );
}

export default App;
