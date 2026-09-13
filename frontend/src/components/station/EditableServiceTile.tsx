import { useState } from "react";

import { deleteService, updateService, type Service } from "../../api/client";
import { iconForService, PencilIcon } from "../icons";

// По заметке пользователя: рядом с крестиком удаления нужен карандаш для
// редактирования уже существующей услуги.
export function EditableServiceTile({
  service,
  onSaved,
  onDeleted,
  onError,
}: {
  service: Service;
  onSaved: (service: Service) => void;
  onDeleted: (id: number) => void;
  onError: (message: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(service.name);
  const [duration, setDuration] = useState(String(service.duration_minutes));
  const [price, setPrice] = useState(service.price);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const updated = await updateService(service.id, {
        name: name.trim(),
        duration_minutes: Number(duration),
        price: Number(price),
      });
      onSaved(updated);
      setEditing(false);
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Удалить эту услугу из каталога?")) return;
    try {
      await deleteService(service.id);
      onDeleted(service.id);
    } catch (err) {
      // Услуга могла быть уже удалена из другой вкладки/другим сотрудником
      // станции (заметка пользователя: "услуга исчезает после обновления
      // страницы") — 404 в этом случае означает, что желаемое состояние уже
      // достигнуто, а не настоящую ошибку, поэтому тоже убираем локально.
      if ((err as Error).message.includes("не найдена")) {
        onDeleted(service.id);
      } else {
        onError((err as Error).message);
      }
    }
  };

  if (editing) {
    return (
      <div className="form-card" style={{ maxWidth: 280 }}>
        <div className="form-field">
          <label>Название</label>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="form-field">
          <label>Длительность, мин</label>
          <input type="number" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} />
        </div>
        <div className="form-field">
          <label>Цена, ₽</label>
          <input type="number" min={0} step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} />
        </div>
        <div className="wizard-nav">
          <button type="button" className="link-button" onClick={() => setEditing(false)}>
            Отмена
          </button>
          <button type="button" className="primary-button" disabled={busy} onClick={save}>
            Сохранить
          </button>
        </div>
      </div>
    );
  }

  const Icon = iconForService(service.name);

  return (
    <div className="tile-button" style={{ cursor: "default", position: "relative" }}>
      <button
        type="button"
        onClick={() => setEditing(true)}
        title="Редактировать услугу"
        style={{
          position: "absolute",
          top: 6,
          left: 6,
          border: "none",
          background: "none",
          color: "var(--color-text)",
          cursor: "pointer",
          padding: 0,
          lineHeight: 1,
        }}
      >
        <PencilIcon />
      </button>
      <button
        type="button"
        onClick={remove}
        title="Удалить услугу"
        style={{
          position: "absolute",
          top: 6,
          right: 6,
          border: "none",
          background: "none",
          color: "var(--color-danger)",
          fontWeight: 700,
          cursor: "pointer",
          fontSize: "1rem",
          lineHeight: 1,
        }}
      >
        ×
      </button>
      <Icon />
      <span>{service.name}</span>
      <span className="price">{service.price} ₽</span>
    </div>
  );
}
