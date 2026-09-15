import { useCallback, useEffect, useState } from "react";

import {
  getStationStats,
  issueTireSet,
  listAllCars,
  listAllClients,
  listArchive,
  listBookings,
  listServices,
  listTireSetArchive,
  listTireSets,
  type ArchivedBooking,
  type Booking,
  type CarInfo,
  type ClientInfo,
  type Service,
  type TireSet,
  type TireSetArchiveEntry,
} from "../api/client";
import { useBookingEvents } from "../api/events";
import { Countdown, UpcomingCountdown } from "../components/Countdown";
import { EventLog } from "../components/EventLog";
import { NotificationDot } from "../components/NotificationDot";
import { StatusIndicator } from "../components/StatusIndicator";
import { formatSlotLabel } from "../components/booking/SlotPicker";
import { AddServiceForm } from "../components/station/AddServiceForm";
import { AdditionalWorkPanel } from "../components/station/AdditionalWorkPanel";
import { ArchiveTable } from "../components/station/ArchiveTable";
import { BookingActions } from "../components/station/BookingActions";
import { EditableServiceTile } from "../components/station/EditableServiceTile";
import { PostsBoard } from "../components/station/PostsBoard";
import { TireSetArchiveTable } from "../components/TireSetArchiveTable";

export function StationPage() {
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [services, setServices] = useState<Service[] | null>(null);
  const [cars, setCars] = useState<CarInfo[]>([]);
  const [clients, setClients] = useState<ClientInfo[]>([]);
  const [revenue, setRevenue] = useState<string | null>(null);
  const [archive, setArchive] = useState<ArchivedBooking[]>([]);
  const [showArchive, setShowArchive] = useState(false);
  const [tireSets, setTireSets] = useState<TireSet[]>([]);
  const [tireArchive, setTireArchive] = useState<TireSetArchiveEntry[]>([]);
  const [showTireArchive, setShowTireArchive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const events = useBookingEvents();

  const reloadBookings = useCallback(() => {
    listBookings()
      .then(setBookings)
      .catch((err) => setError(err.message));
  }, []);

  const reloadServices = useCallback(() => {
    listServices()
      .then(setServices)
      .catch((err) => setError(err.message));
  }, []);

  const reloadCars = useCallback(() => {
    listAllCars()
      .then(setCars)
      .catch((err) => setError(err.message));
  }, []);

  const reloadRevenue = useCallback(() => {
    getStationStats()
      .then((stats) => setRevenue(stats.total_revenue))
      .catch((err) => setError(err.message));
  }, []);

  const reloadArchive = useCallback(() => {
    listArchive()
      .then(setArchive)
      .catch((err) => setError(err.message));
  }, []);

  const reloadClients = useCallback(() => {
    listAllClients()
      .then(setClients)
      .catch((err) => setError(err.message));
  }, []);

  const reloadTireSets = useCallback(() => {
    listTireSets({ activeOnly: true })
      .then(setTireSets)
      .catch((err) => setError(err.message));
  }, []);

  const reloadTireArchive = useCallback(() => {
    listTireSetArchive()
      .then(setTireArchive)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    reloadBookings();
    reloadServices();
    reloadCars();
    reloadRevenue();
    reloadArchive();
    reloadClients();
    reloadTireSets();
    reloadTireArchive();
  }, [
    reloadBookings,
    reloadServices,
    reloadCars,
    reloadRevenue,
    reloadArchive,
    reloadClients,
    reloadTireSets,
    reloadTireArchive,
  ]);

  // Пока перезапрашиваем список по каждому событию, а не редактируем его на
  // лету — просто и достаточно для каркаса; B7 (полноценный экран станции
  // по постам) сделает это аккуратнее. Выручка и журнал тоже пересчитываются
  // по событию — они меняются именно в момент "выдачи"/"отмены" заявки.
  useEffect(() => {
    if (events.length > 0) {
      reloadBookings();
      reloadCars();
      reloadRevenue();
      reloadArchive();
      // Каталог услуг раньше не входил в цикл живого обновления — если
      // услугу удаляли в одной вкладке, в другой она "призраком" оставалась
      // видна до ручного обновления страницы (заметка пользователя №5).
      // Каталог не шлёт SSE-события сам по себе, но раз уж событие всё
      // равно прилетело — заодно освежаем и его.
      reloadServices();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events, reloadBookings, reloadCars, reloadRevenue, reloadArchive, reloadServices]);

  const carLabel = (carId: number): string => {
    const car = cars.find((c) => c.id === carId);
    return car ? `${car.make} ${car.model}` : `#${carId}`;
  };

  const clientLabel = (clientId: number): string => {
    const c = clients.find((x) => x.id === clientId);
    return c ? c.name : `#${clientId}`;
  };

  // UI_description.md п.12: в таблице заявок должны быть видны отдельными
  // столбиками и контакты клиента, и изначально забронированная услуга.
  const clientOf = (clientId: number): ClientInfo | undefined =>
    clients.find((x) => x.id === clientId);

  const handleIssueTireSet = async (id: number) => {
    if (!window.confirm("Выдать этот комплект шин клиенту?")) return;
    try {
      await issueTireSet(id);
      reloadTireSets();
      reloadTireArchive();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div>
      <h1 className="step-title">Экран станции</h1>

      <PostsBoard bookings={bookings ?? []} />

      <div
        style={{
          textAlign: "center",
          background: "var(--color-primary)",
          borderRadius: 14,
          padding: "1rem",
          marginBottom: "1.5rem",
        }}
      >
        <div style={{ color: "var(--color-muted)", fontSize: "0.85rem" }}>Заработано станцией</div>
        <div style={{ fontSize: "1.8rem", fontWeight: 700 }}>{revenue ?? "…"} ₽</div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="panel">
        <div className="panel-header">
          <h2>Каталог услуг</h2>
        </div>
        <div className="tile-grid" style={{ marginBottom: "1rem" }}>
          {services?.map((service) => (
            <EditableServiceTile
              key={service.id}
              service={service}
              onSaved={(updated) =>
                setServices((prev) => (prev ?? []).map((s) => (s.id === updated.id ? updated : s)))
              }
              onDeleted={(id) => setServices((prev) => (prev ?? []).filter((s) => s.id !== id))}
              onError={setError}
            />
          ))}
        </div>
        <AddServiceForm onCreated={(service) => setServices((prev) => [...(prev ?? []), service])} />
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>Все заявки</h2>
        </div>
        {!error && bookings === null && <p className="panel-empty">Загрузка...</p>}
        {bookings && bookings.length === 0 && <p className="panel-empty">Заявок пока нет.</p>}
        {bookings && bookings.length > 0 && (
          <div className="data-table-wrap">
            <table className="data-table data-table--fixed">
              <colgroup>
                <col style={{ width: "5%" }} />
                <col style={{ width: "16%" }} />
                <col style={{ width: "14%" }} />
                <col style={{ width: "10%" }} />
                <col style={{ width: "12%" }} />
                <col style={{ width: "15%" }} />
                <col style={{ width: "13%" }} />
                <col style={{ width: "15%" }} />
              </colgroup>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Клиент</th>
                  <th>Услуга</th>
                  <th>Автомобиль</th>
                  <th>Начало</th>
                  <th>Статус</th>
                  <th>Действия</th>
                  <th>Доп. работы</th>
                </tr>
              </thead>
              <tbody>
                {bookings.map((booking) => {
                  const client = clientOf(booking.client_id);
                  return (
                  <tr key={booking.id}>
                    <td>{booking.id}</td>
                    <td>
                      {client ? (
                        <>
                          <div>{client.name}</div>
                          <div style={{ fontSize: "0.8em", color: "var(--color-muted)" }}>{client.email}</div>
                        </>
                      ) : (
                        `#${booking.client_id}`
                      )}
                    </td>
                    <td>{booking.services.map((s) => s.name).join(", ") || "—"}</td>
                    <td>{carLabel(booking.car_id)}</td>
                    <td>{formatSlotLabel(booking.start_at)}</td>
                    <td>
                      <StatusIndicator status={booking.status} />
                      <NotificationDot
                        show={booking.status === "accepted" || booking.status === "ready"}
                        title={
                          booking.status === "accepted"
                            ? "Ждёт приёма на пост"
                            : "Ждёт выдачи клиенту"
                        }
                      />
                      {booking.status === "on_post" && booking.service_ends_at && (
                        <Countdown targetIso={booking.service_ends_at} />
                      )}
                      {booking.status === "accepted" && (
                        <UpcomingCountdown targetIso={booking.start_at} />
                      )}
                    </td>
                    <td>
                      <BookingActions
                        booking={booking}
                        onChanged={() => {
                          reloadBookings();
                          reloadRevenue();
                        }}
                        onError={setError}
                      />
                    </td>
                    <td>
                      <AdditionalWorkPanel
                        bookingId={booking.id}
                        services={services ?? []}
                        refreshKey={events.length}
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
          <h2>Шины на хранении</h2>
        </div>
        {tireSets.length === 0 && <p className="panel-empty">Сейчас никто не хранит шины.</p>}
        {tireSets.length > 0 && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Клиент</th>
                  <th>Автомобиль</th>
                  <th>Сдано</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {tireSets.map((t) => (
                  <tr key={t.id}>
                    <td>{clientLabel(t.client_id)}</td>
                    <td>{carLabel(t.car_id)}</td>
                    <td>{new Date(t.stored_at).toLocaleDateString()}</td>
                    <td>
                      <button type="button" className="action-button" onClick={() => handleIssueTireSet(t.id)}>
                        Выдать
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="panel-header" style={{ marginTop: "1rem" }}>
          <h3 style={{ margin: 0 }}>Журнал приёма и выдачи шин</h3>
          <button type="button" className="ghost-button" onClick={() => setShowTireArchive((v) => !v)}>
            {showTireArchive ? "Скрыть" : `Показать (${tireArchive.length})`}
          </button>
        </div>
        {showTireArchive && <TireSetArchiveTable entries={tireArchive} />}
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>Журнал</h2>
          <button type="button" className="ghost-button" onClick={() => setShowArchive((v) => !v)}>
            {showArchive ? "Скрыть" : `Показать (${archive.length})`}
          </button>
        </div>
        {showArchive && <ArchiveTable entries={archive} />}
      </div>

      <EventLog events={events} />
    </div>
  );
}
