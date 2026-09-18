import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  confirmParked,
  declineTireStorageOffer,
  deleteCar,
  deleteClient,
  dismissTireSeasonReminder,
  getMaintenanceSuggestions,
  getTireSeasonReminder,
  issueTireSet,
  listArchive,
  listBookings,
  listCars,
  listParkingSpots,
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
  type ParkingSpot,
  type TireSet,
  type TireSetArchiveEntry,
} from "../api/client";
import { useDebouncedEventTick } from "../api/events";
import { AddCarForm } from "../components/booking/AddCarForm";
import { CAR_MAKES, modelsForMake } from "../data/carCatalog";
import { ClientAdditionalWorks } from "../components/booking/ClientAdditionalWorks";
import { TireSetArchiveTable } from "../components/TireSetArchiveTable";
import { IdentifyForm } from "../components/booking/IdentifyForm";
import { RescheduleControl } from "../components/booking/RescheduleControl";
import { formatSlotLabel } from "../components/booking/SlotPicker";
import { Countdown, UpcomingCountdown } from "../components/Countdown";
import { CarIcon, PlusIcon } from "../components/icons";
import { Pagination } from "../components/Pagination";
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

// UI_description.md п.47 (2026-09-16): сдать/забрать шины — больше не
// голая кнопка в кабинете, а действие, привязанное к реальному визиту на
// одну из двух защищённых услуг, пока машина физически на посту (иначе
// backend вернёт 409 — см. app/api/tire_sets.py). "Сезонная замена шин"
// дополнительно предлагает вопрос "сдать шины на хранение или нет"
// (согласие — по кнопке ниже; отказ фиксируется отдельным эндпоинтом,
// чтобы не спрашивать повторно в рамках этого же визита); "Получить/сдать
// шины" — отдельный визит именно за этим, без вопроса.
const SEASONAL_TIRE_SWAP_SERVICE_NAME = "Сезонная замена шин";
const TIRE_VISIT_SERVICE_NAME = "Получить/сдать шины";

// Действие про шины теперь живёт прямо в строке заявки в "Мои записи" (по
// прямой правке пользователя 2026-09-16, после того как вопрос "сдать на
// хранение?" был найден незаметным в отдельной таблице ниже) — рядом с тем
// же местом, где заявке предлагаются доп. работы. Ничего не рисует для
// заявок, не находящихся прямо сейчас на посту по одной из двух защищённых
// услуг — не захламляет остальные строки.
function TireStorageAction({
  booking,
  activeSet,
  onChanged,
  onError,
}: {
  booking: Booking;
  activeSet: TireSet | undefined;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  const canHandOverNow = booking.services.some((s) => s.name === TIRE_VISIT_SERVICE_NAME);
  const isSeasonalSwapVisit = booking.services.some(
    (s) => s.name === SEASONAL_TIRE_SWAP_SERVICE_NAME,
  );
  if (booking.status !== "on_post" || (!canHandOverNow && !isSeasonalSwapVisit)) {
    return null;
  }

  const store = async () => {
    setBusy(true);
    try {
      await storeTireSet({ client_id: booking.client_id, car_id: booking.car_id });
      onChanged();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const decline = async () => {
    setBusy(true);
    try {
      await declineTireStorageOffer(booking.id);
      onChanged();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const issue = async () => {
    if (!activeSet) return;
    if (!window.confirm("Забрать шины сейчас?")) return;
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
    <div
      style={{
        marginTop: "0.5rem",
        paddingTop: "0.5rem",
        borderTop: "1px dashed var(--color-border)",
      }}
    >
      {activeSet ? (
        canHandOverNow ? (
          <button type="button" className="action-button" disabled={busy} onClick={issue}>
            Забрать шины
          </button>
        ) : (
          <span style={{ color: "var(--color-muted)" }}>
            Забрать можно во время визита на «{TIRE_VISIT_SERVICE_NAME}»
          </span>
        )
      ) : isSeasonalSwapVisit && booking.tire_offer_declined ? (
        <span style={{ color: "var(--color-muted)" }}>Хранение отклонено в этом визите</span>
      ) : isSeasonalSwapVisit ? (
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
          <span>Сдать снятые шины на хранение?</span>
          <button type="button" className="action-button" disabled={busy} onClick={store}>
            Да, сдать
          </button>
          <button type="button" className="ghost-button" disabled={busy} onClick={decline}>
            Нет
          </button>
        </div>
      ) : (
        <button type="button" className="action-button" disabled={busy} onClick={store}>
          Сдать на хранение
        </button>
      )}
    </div>
  );
}

// Таблица "Хранение шин" (B1) — теперь только история/текущий статус,
// без кнопок действия (см. TireStorageAction выше). issued_at === null
// означает "на хранении сейчас".
function TireStorageStatusRow({ car, activeSet }: { car: CarInfo; activeSet: TireSet | undefined }) {
  return (
    <tr>
      <td>
        {car.make} {car.model}
      </td>
      <td>
        {activeSet ? (
          <>На хранении с {new Date(activeSet.stored_at).toLocaleDateString()}</>
        ) : (
          <span style={{ color: "var(--color-muted)" }}>Не хранятся</span>
        )}
      </td>
    </tr>
  );
}

// C7 (buisness.md, "Smart Parking Management", 2026-09-17): клиент сам
// подтверждает приезд из кабинета ("Ставит автомобиль на один из свободных
// парковочных слотов. В личном кабинете подтверждает что машина на месте")
// — до этого подтверждения выезд на пост не наступит автоматически, даже
// когда придёт время визита (см. app/services/parking.py). Когда заявка
// готова, тот же принцип для другой стороны: клиент сам подтверждает, что
// забрал машину — это и есть момент, когда начисляются деньги (buisness.md:
// "клиент нажимает кнопку... после чего... начисляются деньги").
function ParkingAction({
  booking,
  parkingSpots,
  onChanged,
  onError,
}: {
  booking: Booking;
  parkingSpots: ParkingSpot[];
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const spotName = booking.parking_spot_id
    ? parkingSpots.find((s) => s.id === booking.parking_spot_id)?.name ?? `место №${booking.parking_spot_id}`
    : null;

  const park = async () => {
    setBusy(true);
    try {
      await confirmParked(booking.id);
      onChanged();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const pickup = async () => {
    if (!window.confirm("Подтвердить, что вы забрали автомобиль? После этого начислится оплата.")) return;
    setBusy(true);
    try {
      await updateBookingStatus(booking.id, "issued");
      onChanged();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (booking.status === "accepted") {
    if (booking.parking_spot_id === null) {
      return (
        <button type="button" className="action-button" disabled={busy} onClick={park}>
          Я приехал, машина на парковке
        </button>
      );
    }
    return (
      <span style={{ color: "var(--color-muted)" }}>
        На парковке ({spotName}) — ждём начала обслуживания
      </span>
    );
  }

  // Найдено пользователем на практике (2026-09-17): пока клиент решает по
  // доп. работе (см. колонку "Доп. работы" в этой же строке), машина
  // физически должна где-то стоять на станции — иначе непонятно, где она,
  // хотя пост уже визуально свободен. Здесь только статус, без действия —
  // решение принимается кнопками "Принять"/"Отклонить" в доп. работах.
  if (booking.status === "awaiting_approval") {
    return (
      <span style={{ color: "var(--color-muted)" }}>
        {spotName
          ? `Машина на парковке (${spotName}) — ждём вашего решения по доп. работам`
          : "Ждём вашего решения по доп. работам ниже"}
      </span>
    );
  }

  if (booking.status === "ready") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        <span style={{ color: "var(--color-primary-active)", fontWeight: 600 }}>
          Машина готова{spotName ? ` (${spotName})` : ""} — можно забирать
        </span>
        <button type="button" className="action-button" disabled={busy} onClick={pickup}>
          Забрал(а) автомобиль
        </button>
      </div>
    );
  }

  return null;
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
    if (
      !window.confirm(
        "Удалить личный кабинет навсегда? Все ваши машины и активные записи будут отменены и удалены вместе с профилем. Если у вас есть шины на хранении — забери их первым делом, иначе удаление не пройдёт. Отменить это действие нельзя."
      )
    )
      return;
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
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [showHistory, setShowHistory] = useState(false);
  const [tireSets, setTireSets] = useState<TireSet[]>([]);
  const [tireHistory, setTireHistory] = useState<TireSetArchiveEntry[]>([]);
  const [tireHistoryTotal, setTireHistoryTotal] = useState(0);
  const [tireHistoryPage, setTireHistoryPage] = useState(1);
  const [showTireHistory, setShowTireHistory] = useState(false);
  const [maintenance, setMaintenance] = useState<{
    suggestions: MaintenanceSuggestion[];
    slots_scarce: boolean;
  }>({ suggestions: [], slots_scarce: false });
  const [tireSeasonReminder, setTireSeasonReminder] = useState<{ active: boolean; season_label: string } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [addingCar, setAddingCar] = useState(false);
  const reloadTick = useDebouncedEventTick();
  // C7 (buisness.md, "Smart Parking Management") — фиксированный справочник
  // из 6 мест, не меняется, достаточно загрузить один раз, а не гонять
  // внутри reload() на каждый SSE-тик.
  const [parkingSpots, setParkingSpots] = useState<ParkingSpot[]>([]);
  useEffect(() => {
    listParkingSpots().then(setParkingSpots).catch(() => {});
  }, []);

  const reload = useCallback(() => {
    if (!client) return;
    listCars(client.id).then(setCars).catch((err) => setError(err.message));
    listBookings(client.id).then(setBookings).catch((err) => setError(err.message));
    listArchive(client.id, historyPage)
      .then((res) => {
        setHistory(res.items);
        setHistoryTotal(res.total);
      })
      .catch((err) => setError(err.message));
    listTireSets({ clientId: client.id }).then(setTireSets).catch((err) => setError(err.message));
    listTireSetArchive(client.id, tireHistoryPage)
      .then((res) => {
        setTireHistory(res.items);
        setTireHistoryTotal(res.total);
      })
      .catch((err) => setError(err.message));
    // B5: проактивное предложение — не критично для основного функционала
    // кабинета, поэтому тихо игнорируем ошибку, а не показываем баннер.
    getMaintenanceSuggestions(client.id)
      .then(setMaintenance)
      .catch(() => {});
    // B6: сезонное промо про хранение шин — тот же принцип, что и B5 выше.
    getTireSeasonReminder(client.id)
      .then(setTireSeasonReminder)
      .catch(() => {});
  }, [client, historyPage, tireHistoryPage]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    if (reloadTick > 0) reload();
  }, [reloadTick, reload]);

  // UI_description.md п.44: закрыть баннер крестиком — сразу прячем (не
  // дожидаясь ответа сервера) и не показываем больше до конца сезона; при
  // ошибке возвращаем баннер обратно, чтобы не потерять напоминание молча.
  const dismissTireReminder = async () => {
    if (!client || !tireSeasonReminder) return;
    const previous = tireSeasonReminder;
    setTireSeasonReminder({ ...tireSeasonReminder, active: false });
    try {
      await dismissTireSeasonReminder(client.id);
    } catch (err) {
      setTireSeasonReminder(previous);
      setError((err as Error).message);
    }
  };

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
      {/* UI_description.md п.45 (2026-09-15): баннер сезонного хранения шин
          (B6) — под шапку меню, НАД написью "Личный кабинет" (был ниже, под
          профилем и переключателем аккаунтов). */}
      {tireSeasonReminder?.active && (
        <div
          className="panel"
          style={{ background: "var(--color-primary)", textAlign: "center", position: "relative" }}
        >
          <button
            type="button"
            onClick={dismissTireReminder}
            title="Закрыть до конца сезона"
            style={{
              position: "absolute",
              top: 6,
              right: 10,
              border: "none",
              background: "none",
              color: "inherit",
              fontWeight: 700,
              cursor: "pointer",
              fontSize: "1.1rem",
              lineHeight: 1,
            }}
          >
            ×
          </button>
          <p style={{ margin: "0.25rem 0" }}>
            Сезонное напоминание ({tireSeasonReminder.season_label}): наша станция принимает шины на сезонное
            хранение — можно освободить место в гараже или багажнике на весь сезон. Если вы ещё не пользовались
            этой услугой — посмотрите раздел "Хранение шин" ниже.
          </p>
        </div>
      )}

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
              onSaved={(updated) => {
                setCars((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
                // UI_description.md п.43 (2026-09-15): без этого предложение
                // пройти ТО (баннер ниже — зависит от пробега/даты именно
                // этой машины) обновлялось только "случайно" — если что-то
                // другое отдельно вызывало reload() — а не сразу после
                // сохранения новых данных машины.
                reload();
              }}
              onDeleted={(id) => {
                setCars((prev) => prev.filter((c) => c.id !== id));
                reload();
              }}
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
              // UI_description.md п.43: новая машина может сразу нуждаться в
              // ТО (например, при ручном вводе старой даты последнего
              // обслуживания) — баннер должен появиться сразу, не только
              // после перехода со страницы и обратно.
              reload();
            }}
            onCancel={() => setAddingCar(false)}
          />
        )}
      </div>

      {/* UI_description.md п.45 (2026-09-15): "поменять местами таблицы мои
          записи и хранение шин" — "Мои записи" теперь выше "Хранения шин". */}
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
                  <th>Автомобиль</th>
                  <th>Услуга</th>
                  <th>Когда</th>
                  <th>Статус</th>
                  <th></th>
                  <th>Доп. работы</th>
                </tr>
              </thead>
              <tbody>
                {bookings.map((b) => {
                  const car = cars.find((c) => c.id === b.car_id);
                  return (
                  <tr key={b.id}>
                    <td>{b.id}</td>
                    <td>{car ? `${car.make} ${car.model}` : `#${b.car_id}`}</td>
                    <td>{b.services.map((s) => s.name).join(", ") || "—"}</td>
                    <td>{formatSlotLabel(b.start_at)}</td>
                    <td>
                      <StatusIndicator status={b.status} />
                      {b.status === "on_post" && b.service_ends_at && (
                        <Countdown targetIso={b.service_ends_at} startedIso={b.on_post_started_at} />
                      )}
                      {b.status === "accepted" && <UpcomingCountdown targetIso={b.start_at} />}
                    </td>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                        <ParkingAction
                          booking={b}
                          parkingSpots={parkingSpots}
                          onChanged={reload}
                          onError={setError}
                        />
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
                      <ClientAdditionalWorks bookingId={b.id} refreshKey={reloadTick} />
                      <TireStorageAction
                        booking={b}
                        activeSet={tireSets.find((t) => t.car_id === b.car_id && t.issued_at === null)}
                        onChanged={reload}
                        onError={setError}
                      />
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
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
                </tr>
              </thead>
              <tbody>
                {cars.map((car) => (
                  <TireStorageStatusRow
                    key={car.id}
                    car={car}
                    activeSet={tireSets.find((t) => t.car_id === car.id && t.issued_at === null)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="panel-header" style={{ marginTop: "1rem" }}>
          <h3 style={{ margin: 0 }}>История хранения шин</h3>
          <button type="button" className="ghost-button" onClick={() => setShowTireHistory((v) => !v)}>
            {showTireHistory ? "Скрыть" : `Показать (${tireHistoryTotal})`}
          </button>
        </div>
        {showTireHistory && (
          <>
            <Pagination page={tireHistoryPage} total={tireHistoryTotal} pageSize={50} onChange={setTireHistoryPage} />
            <TireSetArchiveTable entries={tireHistory} />
            <Pagination page={tireHistoryPage} total={tireHistoryTotal} pageSize={50} onChange={setTireHistoryPage} />
          </>
        )}
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>История</h2>
          <button type="button" className="ghost-button" onClick={() => setShowHistory((v) => !v)}>
            {showHistory ? "Скрыть" : `Показать (${historyTotal})`}
          </button>
        </div>
        {showHistory && (
          <>
            <Pagination page={historyPage} total={historyTotal} pageSize={50} onChange={setHistoryPage} />
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
                        <td>
                          {entry.status === "issued" ? (
                            <>
                              {entry.total_price} ₽
                              {Number(entry.parking_surcharge) > 0 && (
                                <small className="price-breakdown">
                                  Услуги {entry.service_price} ₽ + парковка {entry.parking_surcharge} ₽
                                </small>
                              )}
                            </>
                          ) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Pagination page={historyPage} total={historyTotal} pageSize={50} onChange={setHistoryPage} />
          </>
        )}
      </div>
    </div>
  );
}
