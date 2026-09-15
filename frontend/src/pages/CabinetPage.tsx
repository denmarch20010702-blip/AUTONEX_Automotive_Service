import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  deleteCar,
  deleteClient,
  getMaintenanceSuggestions,
  issueTireSet,
  listArchive,
  listBookings,
  listCars,
  listTireSetArchive,
  listTireSets,
  storeTireSet,
  updateBookingStatus,
  updateCar,
  updateClient,
  type ArchivedBooking,
  type Booking,
  type CarInfo,
  type ClientInfo,
  type MaintenanceSuggestion,
  type TireSet,
  type TireSetArchiveEntry,
} from "../api/client";
import { useBookingEvents } from "../api/events";
import { AddCarForm } from "../components/booking/AddCarForm";
import { CAR_MAKES, modelsForMake } from "../data/carCatalog";
import { ClientAdditionalWorks } from "../components/booking/ClientAdditionalWorks";
import { TireSetArchiveTable } from "../components/TireSetArchiveTable";
import { IdentifyForm } from "../components/booking/IdentifyForm";
import { RescheduleControl } from "../components/booking/RescheduleControl";
import { formatSlotLabel } from "../components/booking/SlotPicker";
import { Countdown, UpcomingCountdown } from "../components/Countdown";
import { CarIcon, PlusIcon } from "../components/icons";
import { StatusIndicator } from "../components/StatusIndicator";
import { useClientSession } from "../session/ClientSessionContext";

const CANCELLABLE = new Set(["accepted", "on_post", "awaiting_approval", "ready"]);

// "YYYY-MM-DD" -> "DD.MM.YYYY" по компонентам строки, без создания
// Date-объекта — та же ловушка часового пояса, что уже чинили в
// localMidnightIso (api/client.ts): `new Date("2026-09-14")` трактуется как
// UTC-полночь и при отрицательном смещении часового пояса устройства
// сдвигается на день назад при выводе через toLocaleDateString.
function formatDateOnly(isoDate: string): string {
  const [year, month, day] = isoDate.split("-");
  return `${day}.${month}.${year}`;
}

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
          <button type="button" className="action-button" disabled={busy} onClick={issue}>
            Забрать
          </button>
        ) : (
          <button type="button" className="action-button" disabled={busy} onClick={store}>
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
          <button type="button" className="ghost-button" onClick={() => setEditing(false)}>
            Отмена
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={!make.trim() || !model.trim() || busy}
            onClick={save}
          >
            Сохранить
          </button>
        </div>
      </div>
    );
  }

  return (
    // Найдено на практике (UI_description.md, п.18): кнопки "Изменить"/
    // "Удалить" не помещались бок о бок в жёстко квадратной 150×150
    // `.tile-button` и выпирали за её границы. Плитка авто — не кнопка
    // выбора услуги из спеки, ей не обязательно быть строго квадратной:
    // высота теперь "auto" (не меньше исходной), а кнопки — в столбик на
    // всю ширину, что гарантированно вписывается в 150px.
    <div className="tile-button" style={{ cursor: "default", height: "auto", minHeight: 150 }}>
      <CarIcon />
      <span>
        {car.make} {car.model}
      </span>
      <span className="price">{car.mileage} км</span>
      {/* UI_description.md п.31: дата последнего ТО теперь обновляется сама
          при выдаче заявки — стоит показывать её, иначе изменение будет
          незаметно клиенту. */}
      <span className="price">ТО: {car.last_service_date ? formatDateOnly(car.last_service_date) : "нет данных"}</span>
      {error && <div className="error-banner">{error}</div>}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", marginTop: "0.5rem", width: "100%" }}>
        <button type="button" className="ghost-button" style={{ width: "100%" }} onClick={() => setEditing(true)}>
          Изменить
        </button>
        <button
          type="button"
          className="action-button danger"
          style={{ width: "100%" }}
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
// UI_description.md п.21/29: клиент сам меняет своё имя/почту или удаляет
// свой аккаунт — прямо из личного кабинета, без обращения к станции.
function ProfilePanel({
  client,
  onSaved,
  onDeleted,
}: {
  client: ClientInfo;
  onSaved: (client: ClientInfo) => void;
  onDeleted: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(client.name);
  const [email, setEmail] = useState(client.email);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await updateClient(client.id, { name: name.trim(), email: email.trim() });
      onSaved(updated);
      setEditing(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Удалить личный кабинет навсегда? Это действие нельзя отменить.")) return;
    setBusy(true);
    setError(null);
    try {
      await deleteClient(client.id);
      onDeleted();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <div className="form-card" style={{ maxWidth: 320, margin: "0 auto 1.5rem" }}>
        {error && <div className="error-banner">{error}</div>}
        <div className="form-field">
          <label>Имя</label>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="form-field">
          <label>Почта</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="wizard-nav">
          <button type="button" className="ghost-button" onClick={() => setEditing(false)}>
            Отмена
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={!name.trim() || !email.trim() || busy}
            onClick={save}
          >
            Сохранить
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ textAlign: "center", marginBottom: "1.5rem" }}>
      {error && <div className="error-banner">{error}</div>}
      <p className="step-subtitle" style={{ marginBottom: "0.5rem" }}>
        {client.name} · {client.email}
      </p>
      <div style={{ display: "flex", justifyContent: "center", gap: "0.5rem" }}>
        <button type="button" className="ghost-button" onClick={() => setEditing(true)}>
          Изменить профиль
        </button>
        <button type="button" className="action-button danger" disabled={busy} onClick={remove}>
          Удалить аккаунт
        </button>
      </div>
    </div>
  );
}

export function CabinetPage() {
  const { client, knownClients, login, logout, switchTo, forget } = useClientSession();
  const navigate = useNavigate();
  const [cars, setCars] = useState<CarInfo[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [history, setHistory] = useState<ArchivedBooking[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [tireSets, setTireSets] = useState<TireSet[]>([]);
  const [tireHistory, setTireHistory] = useState<TireSetArchiveEntry[]>([]);
  const [showTireHistory, setShowTireHistory] = useState(false);
  const [maintenance, setMaintenance] = useState<{
    suggestions: MaintenanceSuggestion[];
    slots_scarce: boolean;
  }>({ suggestions: [], slots_scarce: false });
  const [error, setError] = useState<string | null>(null);
  const [addingCar, setAddingCar] = useState(false);
  const events = useBookingEvents();

  const reload = useCallback(() => {
    if (!client) return;
    listCars(client.id).then(setCars).catch((err) => setError(err.message));
    listBookings(client.id).then(setBookings).catch((err) => setError(err.message));
    listArchive(client.id).then(setHistory).catch((err) => setError(err.message));
    listTireSets({ clientId: client.id }).then(setTireSets).catch((err) => setError(err.message));
    listTireSetArchive(client.id).then(setTireHistory).catch((err) => setError(err.message));
    // B5: проактивное предложение — не критично для основного функционала
    // кабинета, поэтому тихо игнорируем ошибку, а не показываем баннер.
    getMaintenanceSuggestions(client.id)
      .then(setMaintenance)
      .catch(() => {});
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
                className="ghost-button"
                style={{ display: "block", margin: "0.35rem auto" }}
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

  const handleAccountDeleted = () => {
    forget(client.id);
    navigate("/");
  };

  return (
    <div>
      <h1 className="step-title">Личный кабинет</h1>
      <ProfilePanel client={client} onSaved={login} onDeleted={handleAccountDeleted} />

      <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "1.5rem" }}>
        <button type="button" className="primary-button" onClick={() => navigate("/")}>
          Записаться на услугу
        </button>
        <button type="button" className="ghost-button" onClick={logout}>
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
              <button key={c.id} type="button" className="ghost-button" onClick={() => switchTo(c.id)}>
                {c.name} ({c.email})
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {/* UI_description.md п.23: письмо-напоминание за день до записи (B3)
          пишется в email-заглушку, невидимую самому клиенту в интерфейсе —
          тот же факт нужно показать и здесь, а не только в outbox_emails. */}
      {(() => {
        const now = Date.now();
        const soon = bookings.filter((b) => {
          const startsAt = new Date(b.start_at).getTime();
          return startsAt > now && startsAt - now <= 24 * 60 * 60 * 1000;
        });
        if (soon.length === 0) return null;
        return (
          <div className="panel" style={{ background: "var(--color-primary)", textAlign: "center" }}>
            {soon.map((b) => (
              <p key={b.id} style={{ margin: "0.25rem 0" }}>
                Напоминание: тебя ждём {formatSlotLabel(b.start_at)} — не забудь про этот визит.
              </p>
            ))}
          </div>
        );
      })()}

      {/* B5: проактивное предложение записи по сроку/пробегу ТО, плюс
          пометка пользователя — если мест мало, стоит поторопиться. */}
      {maintenance.suggestions.length > 0 && (
        <div className="panel" style={{ background: "var(--color-primary)", textAlign: "center" }}>
          {maintenance.suggestions.map((s) => (
            <p key={s.car_id} style={{ margin: "0.25rem 0" }}>
              {s.make} {s.model}: похоже, пора на ТО (
              {s.reason === "time"
                ? `не было ${s.months_since_service} мес.`
                : `пробег +${s.km_since_service?.toLocaleString("ru-RU")} км с последнего`}
              ).{" "}
              {maintenance.slots_scarce && (
                <b>Свободных мест становится мало — рекомендуем не откладывать.</b>
              )}
            </p>
          ))}
          <button type="button" className="primary-button" onClick={() => navigate("/")}>
            Записаться
          </button>
        </div>
      )}

      <div className="panel">
        <div className="panel-header">
          <h2>Мои автомобили</h2>
        </div>
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
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>Хранение шин</h2>
        </div>
        {cars.length === 0 ? (
          <p className="panel-empty">Сначала добавь автомобиль.</p>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
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
          </div>
        )}
        <div className="panel-header" style={{ marginTop: "1rem" }}>
          <h3 style={{ margin: 0 }}>История хранения шин</h3>
          <button type="button" className="ghost-button" onClick={() => setShowTireHistory((v) => !v)}>
            {showTireHistory ? "Скрыть" : `Показать (${tireHistory.length})`}
          </button>
        </div>
        {showTireHistory && <TireSetArchiveTable entries={tireHistory} />}
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>Мои записи</h2>
        </div>
        {bookings.length === 0 && <p className="panel-empty">Записей пока нет.</p>}
        {bookings.length > 0 && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Услуга</th>
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
                    <td>{b.services.map((s) => s.name).join(", ") || "—"}</td>
                    <td>{formatSlotLabel(b.start_at)}</td>
                    <td>
                      <StatusIndicator status={b.status} />
                      {b.status === "on_post" && b.service_ends_at && (
                        <Countdown targetIso={b.service_ends_at} />
                      )}
                      {b.status === "accepted" && <UpcomingCountdown targetIso={b.start_at} />}
                    </td>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                        <RescheduleControl booking={b} onRescheduled={reload} onError={setError} />
                        {CANCELLABLE.has(b.status) && (
                          <button
                            type="button"
                            className="action-button danger"
                            onClick={() => cancelBooking(b.id)}
                          >
                            Отменить
                          </button>
                        )}
                      </div>
                    </td>
                    <td>
                      <ClientAdditionalWorks bookingId={b.id} refreshKey={events.length} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>История</h2>
          <button type="button" className="ghost-button" onClick={() => setShowHistory((v) => !v)}>
            {showHistory ? "Скрыть" : `Показать (${history.length})`}
          </button>
        </div>
        {showHistory && (
          <>
            {history.length === 0 ? (
              <p className="panel-empty">Пока пусто.</p>
            ) : (
              <div className="data-table-wrap">
                <table className="data-table">
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
                            см. тот же фикс в ArchiveTable.tsx (станция);
                            включает согласованные доп. работы (п.14). */}
                        <td>{entry.status === "issued" ? `${entry.total_price} ₽` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
