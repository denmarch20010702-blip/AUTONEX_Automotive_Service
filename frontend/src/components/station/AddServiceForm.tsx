import { useState } from "react";

import { createService, type Service } from "../../api/client";
import { PlusIcon, WrenchIcon } from "../icons";

// Добавление услуги станцией — в том же стиле, что и остальной интерфейс
// (buisness/UI_description.md: "делать в таком же стиле кнопки для
// добавления услуг").
export function AddServiceForm({ onCreated }: { onCreated: (service: Service) => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [duration, setDuration] = useState("");
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) {
    return (
      <button type="button" className="add-tile-button" onClick={() => setOpen(true)}>
        <WrenchIcon width={24} height={24} />
        <PlusIcon />
        добавить услугу
      </button>
    );
  }

  const handleSubmit = async () => {
    setError(null);
    setBusy(true);
    try {
      const service = await createService({
        name: name.trim(),
        duration_minutes: Number(duration),
        price: Number(price),
      });
      onCreated(service);
      setName("");
      setDuration("");
      setPrice("");
      setOpen(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-card" style={{ maxWidth: 320 }}>
      {error && <div className="error-banner">{error}</div>}
      <div className="form-field">
        <label htmlFor="service-name">Название услуги</label>
        <input
          id="service-name"
          type="text"
          maxLength={60}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="form-field">
        <label htmlFor="service-duration">Длительность, мин</label>
        <input
          id="service-duration"
          type="number"
          min={1}
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
        />
      </div>
      <div className="form-field">
        <label htmlFor="service-price">Цена, ₽</label>
        <input
          id="service-price"
          type="number"
          min={0}
          step="0.01"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
        />
      </div>
      <div className="wizard-nav">
        <button type="button" className="ghost-button" onClick={() => setOpen(false)}>
          Отмена
        </button>
        <button
          type="button"
          className="primary-button"
          disabled={!name.trim() || !duration || !price || busy}
          onClick={handleSubmit}
        >
          Добавить
        </button>
      </div>
    </div>
  );
}
