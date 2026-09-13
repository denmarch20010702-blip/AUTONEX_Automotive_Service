import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  deleteCar,
  issueTireSet,
  listArchive,
  listBookings,
  listCars,
  listTireSets,
  storeTireSet,
  updateBookingStatus,
  updateCar,
  type ArchivedBooking,
  type Booking,
  type CarInfo,
  type TireSet,
} from "../api/client";
import { useBookingEvents } from "../api/events";
import { AddCarForm } from "../components/booking/AddCarForm";
import { CAR_MAKES, modelsForMake } from "../data/carCatalog";
import { ClientAdditionalWorks } from "../components/booking/ClientAdditionalWorks";
import { IdentifyForm } from "../components/booking/IdentifyForm";
import { formatSlotLabel } from "../components/booking/SlotPicker";
import { CarIcon, PlusIcon } from "../components/icons";
import { StatusIndicator } from "../components/StatusIndicator";
import { useClientSession } from "../session/ClientSessionContext";

const CANCELLABLE = new Set(["accepted", "on_post", "awaiting_approval", "ready"]);

// Хранение шин (B1) — issued_at === null означает "на хранении сейчас".
function TireSetRow({
  car,
  activeSet,
  onChanged,
  onError,
}: {
  car: CarInfo;
  activeSet: TireSet | undefined;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  const store = async () => {
    setBusy(true);
    try {
      await storeTireSet({ client_id: car.client_id, car_id: car.id });
      onChanged();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const issue = async () => {
    if (!activeSet) return;
    if (!window.confirm(`Забрать шины для ${car.make} ${car.model}?`)) return;
    setBusy(true);
    try {
      await issueTireSet(activeSet.id);
      onChanged();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <tr>
      <td>
        {car.make} {car.model}
      </td>
      <td>
        {activeSet ? (
          <>На хранении с {new Date(activeSet.stored_at).toLocaleDateString()}</>
        ) : (
          <span style={{ color: "var(--color-muted)" }}>Не сдавались</span>
        )}
      </td>
      <td>
        {activeSet ? (
          <button type="button" className="link-button" disabled={busy} onClick={issue}>
            Забрать
          </button>
        ) : (
          <button type="button" className="link-button" disabled={busy} onClick={store}>
            Сдать на хранение
          </button>
        )}
      </td>
    </tr>
  );
}

function EditableCarTile({
  car,
  onSaved,
  onDeleted,
}: {
  car: CarInfo;
  onSaved: (car: CarInfo) => void;
  onDeleted: (id: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [make, setMake] = useState(car.make);
  const [model, setModel] = useState(car.model);
  const [mileage, setMileage] = useState(String(car.mileage));
  const [lastServiceDate, setLastServiceDate] = useState(car.last_service_date ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await updateCar(car.id, {
        make: make.trim(),
        model: model.trim(),
        mileage: Number(mileage),
        last_service_date: lastServiceDate || null,
      });
      onSaved(updated);
      setEditing(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Удалить ${car.make} ${car.model}?`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteCar(car.id);
      onDeleted(car.id);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <div className="form-card" style={{ maxWidth: 280 }}>
        {error && <div className="error-banner">{error}</div>}
        <div className="form-field">
          <label>Марка</label>
          <input value={make} list="edit-car-makes-list" onChange={(e) => setMake(e.target.value)} />
          <datalist id="edit-car-makes-list">
            {CAR_MAKES.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </div>
        <div className="form-field">
          <label>Модель</label>
          <input value={model} list="edit-car-models-list" onChange={(e) => setModel(e.target.value)} />
          <datalist id="edit-car-models-list">
            {modelsForMake(make).map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </div>
        <div className="form-field">
          <label>Пробег, км</label>
          <input type="number" min={0} value={mileage} onChange={(e) => setMileage(e.target.value)} />
        </div>
        <div className="form-field">
          <label>Дата последнего ТО</label>
          <input
            type="date"
            value={lastServiceDate}
            onChange={(e) => setLastServiceDate(e.target.value)}
          />
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

  return (
    <div className="tile-button" style={{ cursor: "default" }}>
      <CarIcon />
      <span>
        {car.make} {car.model}
      </span>
      <span className="price">{car.mileage} км</span>
      {error && <div className="error-banner">{error}</div>}
      <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.5rem" }}>
        <button type="button" className="link-button" onClick={() => setEditing(true)}>
          Изменить
        </button>
        <button
          type="button"
          className="link-button"
          style={{ color: "var(--color-danger)" }}
          disabled={busy}
          onClick={remove}
        >
          Удалить
        </button>
      </div>
    </div>
  );
}

// Личный кабинет — по прямой просьбе пользователя: после входа клиент
// видит профиль, управляет своими автомобилями и записями и не должен
// каждый раз заново авторизовываться или проходить мастер записи с нуля.
// Быстрое переключение между уже известными на этом браузере аккаунтами —
// через ClientSessionContext (localStorage), без пароля, как и весь
// остальной клиентский флоу.
export function CabinetPage() {
  const { client, knownClients, login, logout, switchTo } = useClientSession();
  const navigate = useNavigate();
  const [cars, setCars] = useState<CarInfo[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [history, setHistory] = useState<ArchivedBooking[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [tireSets, setTireSets] = useState<TireSet[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [addingCar, setAddingCar] = useState(false);
  const events = useBookingEvents();

  const reload = useCallback(() => {
    if (!client) return;
    listCars(client.id).then(setCars).catch((err) => setError(err.message));
    listBookings(client.id).then(setBookings).catch((err) => setError(err.message));
    listArchive(client.id).then(setHistory).catch((err) => setError(err.message));
    listTireSets({ clientId: client.id }).then(setTireSets).catch((err) => setError(err.message));
  }, [client]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    if (events.length > 0) reload();
  }, [events, reload]);

  const cancelBooking = async (id: number) => {
    if (!window.confirm("Отменить эту запись?")) return;
    try {
      await updateBookingStatus(id, "cancelled");
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  if (!client) {
    return (
      <div>
        <h1 className="step-title">Личный кабинет</h1>
        <p className="step-subtitle">Войди или зарегистрируйся, чтобы увидеть профиль</p>
        <IdentifyForm onIdentified={login} />

        {knownClients.length > 0 && (
          <div style={{ marginTop: "2rem", textAlign: "center" }}>
            <p style={{ color: "var(--color-muted)" }}>Или выбери аккаунт, куда уже входил на этом устройстве:</p>
            {knownClients.map((c) => (
              <button
                key={c.id}
                type="button"
                className="link-button"
                style={{ display: "block", margin: "0.25rem auto" }}
                onClick={() => switchTo(c.id)}
              >
                {c.name} ({c.email})
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  const otherAccounts = knownClients.filter((c) => c.id !== client.id);

  return (
    <div>
      <h1 className="step-title">Личный кабинет</h1>
      <p className="step-subtitle">
        {client.name} · {client.email}
      </p>

      <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1.5rem" }}>
        <button type="button" className="primary-button" onClick={() => navigate("/")}>
          Записаться на услугу
        </button>
        <button type="button" className="link-button" onClick={logout}>
          Выйти
        </button>
      </div>

      {otherAccounts.length > 0 && (
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <p style={{ color: "var(--color-muted)", marginBottom: "0.5rem", fontSize: "0.9rem" }}>
            Переключиться на другой аккаунт:
          </p>
          <div style={{ display: "flex", justifyContent: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            {otherAccounts.map((c) => (
              <button key={c.id} type="button" className="link-button" onClick={() => switchTo(c.id)}>
                {c.name} ({c.email})
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      <h2>Мои автомобили</h2>
      <div className="tile-grid" style={{ marginBottom: "1rem" }}>
        {cars.map((car) => (
          <EditableCarTile
            key={car.id}
            car={car}
            onSaved={(updated) => setCars((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))}
            onDeleted={(id) => setCars((prev) => prev.filter((c) => c.id !== id))}
          />
        ))}
      </div>
      {!addingCar && (
        <div style={{ display: "flex", justifyContent: "center" }}>
          <button type="button" className="add-car-button" onClick={() => setAddingCar(true)}>
            <CarIcon width={24} height={24} />
            <PlusIcon />
            добавить автомобиль
          </button>
        </div>
      )}
      {addingCar && (
        <AddCarForm
          clientId={client.id}
          onCreated={(car) => {
            setCars((prev) => [...prev, car]);
            setAddingCar(false);
          }}
          onCancel={() => setAddingCar(false)}
        />
      )}

      <h2 style={{ marginTop: "2rem" }}>Хранение шин</h2>
      {cars.length === 0 ? (
        <p style={{ color: "var(--color-muted)" }}>Сначала добавь автомобиль.</p>
      ) : (
        <table border={1} cellPadding={6} style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th>Автомобиль</th>
              <th>Статус</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {cars.map((car) => (
              <TireSetRow
                key={car.id}
                car={car}
                activeSet={tireSets.find((t) => t.car_id === car.id && t.issued_at === null)}
                onChanged={reload}
                onError={setError}
              />
            ))}
          </tbody>
        </table>
      )}

      <h2 style={{ marginTop: "2rem" }}>Мои записи</h2>
      {bookings.length === 0 && <p>Записей пока нет.</p>}
      {bookings.length > 0 && (
        <table border={1} cellPadding={6} style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th>ID</th>
              <th>Когда</th>
              <th>Статус</th>
              <th></th>
              <th>Доп. работы</th>
            </tr>
          </thead>
          <tbody>
            {bookings.map((b) => (
              <tr key={b.id}>
                <td>{b.id}</td>
                <td>{formatSlotLabel(b.start_at)}</td>
                <td>
                  <StatusIndicator status={b.status} />
                </td>
                <td>
                  {CANCELLABLE.has(b.status) && (
                    <button
                      type="button"
                      className="link-button"
                      style={{ color: "var(--color-danger)" }}
                      onClick={() => cancelBooking(b.id)}
                    >
                      Отменить
                    </button>
                  )}
                </td>
                <td>
                  <ClientAdditionalWorks bookingId={b.id} refreshKey={events.length} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ marginTop: "2rem" }}>
        <button type="button" className="link-button" onClick={() => setShowHistory((v) => !v)}>
          {showHistory ? "Скрыть историю" : `Показать историю завершённых/отменённых (${history.length})`}
        </button>
        {showHistory && (
          <div style={{ marginTop: "1rem", overflowX: "auto" }}>
            {history.length === 0 ? (
              <p style={{ color: "var(--color-muted)" }}>Пока пусто.</p>
            ) : (
              <table border={1} cellPadding={6} style={{ borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th>Когда была запись</th>
                    <th>Автомобиль</th>
                    <th>Статус</th>
                    <th>Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((entry) => (
                    <tr key={entry.id}>
                      <td>{formatSlotLabel(entry.start_at)}</td>
                      <td>
                        {entry.car_make} {entry.car_model}
                      </td>
                      <td>
                        <StatusIndicator status={entry.status} />
                      </td>
                      {/* Сумма реально оплачена только за выданные заявки —
                          см. тот же фикс в ArchiveTable.tsx (станция). */}
                      <td>{entry.status === "issued" ? `${entry.total_price} ₽` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
