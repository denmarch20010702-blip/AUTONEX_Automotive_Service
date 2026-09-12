import { useState } from "react";

import { findClientByEmail, registerClient, type ClientInfo } from "../../api/client";

// Клиент без пароля — "вход" это поиск по email, "регистрация" — создание
// нового клиента, если такого email ещё нет (см. buisness/ARCHITECTURE.md).
export function IdentifyForm({ onIdentified }: { onIdentified: (client: ClientInfo) => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [needsRegistration, setNeedsRegistration] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleLogin = async () => {
    setError(null);
    setBusy(true);
    try {
      const client = await findClientByEmail(email.trim());
      if (client) {
        onIdentified(client);
      } else {
        setNeedsRegistration(true);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleRegister = async () => {
    setError(null);
    setBusy(true);
    try {
      const client = await registerClient({ email: email.trim(), name: name.trim() });
      onIdentified(client);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-card">
      {error && <div className="error-banner">{error}</div>}

      <div className="form-field">
        <label htmlFor="identify-email">Email</label>
        <input
          id="identify-email"
          type="email"
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
            setNeedsRegistration(false);
          }}
          placeholder="you@example.com"
        />
      </div>

      {!needsRegistration && (
        <button
          type="button"
          className="primary-button"
          disabled={!email.trim() || busy}
          onClick={handleLogin}
        >
          Войти
        </button>
      )}

      {needsRegistration && (
        <>
          <p style={{ color: "var(--color-muted)", fontSize: "0.9rem", margin: 0 }}>
            Такого email ещё нет — укажи имя, чтобы создать учётную запись.
          </p>
          <div className="form-field">
            <label htmlFor="identify-name">Имя</label>
            <input
              id="identify-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Иван Иванов"
            />
          </div>
          <button
            type="button"
            className="primary-button"
            disabled={!name.trim() || busy}
            onClick={handleRegister}
          >
            Зарегистрироваться
          </button>
        </>
      )}
    </div>
  );
}
