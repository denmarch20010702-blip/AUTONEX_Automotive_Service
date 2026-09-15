import { useState } from "react";

import { createService, type Service } from "../../api/client";
import { toTotalMinutes } from "../../utils/duration";
import { PlusIcon, WrenchIcon } from "../icons";

// Добавление услуги станцией — в том же стиле, что и остальной интерфейс
// (buisness/UI_description.md: "делать в таком же стиле кнопки для
// добавления услуг").
export function AddServiceForm({ onCreated }: { onCreated: (service: Service) => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  // UI_description.md п.33: длительность вводится часами И минутами — не
  // обязательно оба поля, главное чтобы итог был больше нуля.
  const [hours, setHours] = useState("");
  const [minutes, setMinutes] = useState("");
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

  const totalMinutes = toTotalMinutes(hours, minutes);

  const handleSubmit = async () => {
    setError(null);
    setBusy(true);
    try {
      const service = await createService({
        name: name.trim(),
        duration_minutes: totalMinutes,
        price: Number(price),
      });
      onCreated(service);
      setName("");
      setHours("");
      setMinutes("");
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
        <label>Длительность</label>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            id="service-duration-hours"
            type="number"
            min={0}
            placeholder="часы"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
          />
          <input
            id="service-duration-minutes"
            type="number"
            min={0}
            max={59}
            placeholder="минуты"
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
          />
        </div>
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
          disabled={!name.trim() || totalMinutes <= 0 || !price || busy}
          onClick={handleSubmit}
        >
          Добавить
        </button>
      </div>
    </div>
  );
}
