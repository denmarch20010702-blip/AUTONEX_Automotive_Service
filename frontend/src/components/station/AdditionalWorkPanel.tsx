import { useEffect, useState } from "react";

import { listAdditionalWorks, proposeAdditionalWork, type AdditionalWork } from "../../api/client";

const STATUS_LABEL: Record<AdditionalWork["status"], string> = {
  pending: "ожидает ответа",
  approved: "согласовано",
  declined: "отклонено",
};

// Согласование доп. работ (B2) — станция предлагает, клиент отвечает в
// своём кабинете. Здесь — сторона станции: список уже предложенного по
// заявке + форма предложить новое.
export function AdditionalWorkPanel({
  bookingId,
  refreshKey,
}: {
  bookingId: number;
  refreshKey: number;
}) {
  const [works, setWorks] = useState<AdditionalWork[]>([]);
  const [adding, setAdding] = useState(false);
  const [description, setDescription] = useState("");
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = () => {
    listAdditionalWorks(bookingId).then(setWorks).catch((err) => setError(err.message));
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId, refreshKey]);

  const propose = async () => {
    setBusy(true);
    setError(null);
    try {
      await proposeAdditionalWork(bookingId, { description: description.trim(), price: Number(price) });
      setDescription("");
      setPrice("");
      setAdding(false);
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ fontSize: "0.85rem" }}>
      {error && <div className="error-banner">{error}</div>}
      {works.map((w) => (
        <div key={w.id}>
          {w.description} ({w.price} ₽) —{" "}
          <span
            style={{
              color:
                w.status === "approved"
                  ? "var(--color-primary-active)"
                  : w.status === "declined"
                    ? "var(--color-danger)"
                    : "var(--color-muted)",
            }}
          >
            {STATUS_LABEL[w.status]}
          </span>
        </div>
      ))}
      {!adding && (
        <button type="button" className="link-button" onClick={() => setAdding(true)}>
          + предложить доп. работу
        </button>
      )}
      {adding && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", marginTop: "0.3rem" }}>
          <input
            type="text"
            placeholder="Описание"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <input
            type="number"
            min={0}
            step="0.01"
            placeholder="Цена, ₽"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" className="link-button" onClick={() => setAdding(false)}>
              Отмена
            </button>
            <button
              type="button"
              className="link-button"
              disabled={!description.trim() || !price || busy}
              onClick={propose}
            >
              Отправить
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
