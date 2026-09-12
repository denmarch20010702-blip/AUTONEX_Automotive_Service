import { useState } from "react";

import { createCar, type CarInfo } from "../../api/client";
import { CAR_MAKES, modelsForMake } from "../../data/carCatalog";

// Ровно два поля — марка и модель (buisness/UI_description.md). Каждое —
// обычный текстовый input с `list` (нативный HTML datalist): можно сразу
// выбрать значение из выпадающего списка, либо начать вводить текст — тогда
// браузер сам сужает список до совпадений. Список моделей зависит от того,
// что сейчас введено в поле марки.
export function AddCarForm({
  clientId,
  onCreated,
  onCancel,
}: {
  clientId: number;
  onCreated: (car: CarInfo) => void;
  onCancel: () => void;
}) {
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [mileage, setMileage] = useState("");
  const [lastServiceDate, setLastServiceDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const models = modelsForMake(make);

  const handleSubmit = async () => {
    setError(null);
    setBusy(true);
    try {
      const car = await createCar({
        client_id: clientId,
        make: make.trim(),
        model: model.trim(),
        mileage: mileage ? Number(mileage) : 0,
        last_service_date: lastServiceDate || null,
      });
      onCreated(car);
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
        <label htmlFor="car-make">Марка</label>
        <input
          id="car-make"
          type="text"
          list="car-makes-list"
          value={make}
          onChange={(event) => {
            setMake(event.target.value);
            setModel("");
          }}
          placeholder="Начни вводить или выбери из списка"
        />
        <datalist id="car-makes-list">
          {CAR_MAKES.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      </div>

      <div className="form-field">
        <label htmlFor="car-model">Модель</label>
        <input
          id="car-model"
          type="text"
          list="car-models-list"
          value={model}
          onChange={(event) => setModel(event.target.value)}
          placeholder="Начни вводить или выбери из списка"
        />
        <datalist id="car-models-list">
          {models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      </div>

      <div className="form-field">
        <label htmlFor="car-mileage">Пробег, км</label>
        <input
          id="car-mileage"
          type="number"
          min={0}
          value={mileage}
          onChange={(event) => setMileage(event.target.value)}
        />
      </div>
      <div className="form-field">
        <label htmlFor="car-last-service">Дата последнего ТО</label>
        <input
          id="car-last-service"
          type="date"
          value={lastServiceDate}
          onChange={(event) => setLastServiceDate(event.target.value)}
        />
      </div>

      <div className="wizard-nav">
        <button type="button" className="link-button" onClick={onCancel}>
          Назад
        </button>
        <button
          type="button"
          className="primary-button"
          disabled={!make.trim() || !model.trim() || busy}
          onClick={handleSubmit}
        >
          Добавить автомобиль
        </button>
      </div>
    </div>
  );
}
