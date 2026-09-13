import { useCallback, useEffect, useState } from "react";

import {
  getStationStats,
  issueTireSet,
  listAllCars,
  listAllClients,
  listArchive,
  listBookings,
  listServices,
  listTireSets,
  type ArchivedBooking,
  type Booking,
  type CarInfo,
  type ClientInfo,
  type Service,
  type TireSet,
} from "../api/client";
import { useBookingEvents } from "../api/events";
import { EventLog } from "../components/EventLog";
import { StatusIndicator } from "../components/StatusIndicator";
import { AddServiceForm } from "../components/station/AddServiceForm";
import { AdditionalWorkPanel } from "../components/station/AdditionalWorkPanel";
import { ArchiveTable } from "../components/station/ArchiveTable";
import { BookingActions } from "../components/station/BookingActions";
import { EditableServiceTile } from "../components/station/EditableServiceTile";

export function StationPage() {
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [services, setServices] = useState<Service[] | null>(null);
  const [cars, setCars] = useState<CarInfo[]>([]);
  const [clients, setClients] = useState<ClientInfo[]>([]);
  const [revenue, setRevenue] = useState<string | null>(null);
  const [archive, setArchive] = useState<ArchivedBooking[]>([]);
  const [showArchive, setShowArchive] = useState(false);
  const [tireSets, setTireSets] = useState<TireSet[]>([]);
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

  useEffect(() => {
    reloadBookings();
    reloadServices();
    reloadCars();
    reloadRevenue();
    reloadArchive();
    reloadClients();
    reloadTireSets();
  }, [reloadBookings, reloadServices, reloadCars, reloadRevenue, reloadArchive, reloadClients, reloadTireSets]);

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
  }, [events, reloadBookings, reloadCars, reloadRevenue, reloadArchive, reloadServices]);

  const carLabel = (carId: number): string => {
    const car = cars.find((c) => c.id === carId);
    return car ? `${car.make} ${car.model}` : `#${carId}`;
  };

  const clientLabel = (clientId: number): string => {
    const c = clients.find((x) => x.id === clientId);
    return c ? c.name : `#${clientId}`;
  };

  const handleIssueTireSet = async (id: number) => {
    if (!window.confirm("Выдать этот комплект шин клиенту?")) return;
    try {
      await issueTireSet(id);
      reloadTireSets();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div>
      <h1>Экран станции</h1>
      <p style={{ color: "#666" }}>
        Здесь будет полноценная доска заявок по постам (шаг B7). Пока — каркас страницы,
        подключение к API и живое обновление списка по событиям из A6.
      </p>

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

      <h2>Каталог услуг</h2>
      {error && <p style={{ color: "red" }}>Ошибка: {error}</p>}
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

      <h2 style={{ marginTop: "2rem" }}>Все заявки</h2>
      {!error && bookings === null && <p>Загрузка...</p>}
      {bookings && bookings.length === 0 && <p>Заявок пока нет.</p>}
      {bookings && bookings.length > 0 && (
        <table border={1} cellPadding={6} style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th>ID</th>
              <th>Пост</th>
              <th>Автомобиль</th>
              <th>Начало</th>
              <th>Статус</th>
              <th>Действия</th>
              <th>Доп. работы</th>
            </tr>
          </thead>
          <tbody>
            {bookings.map((booking) => (
              <tr key={booking.id}>
                <td>{booking.id}</td>
                <td>{booking.post_id}</td>
                <td>{carLabel(booking.car_id)}</td>
                <td>{new Date(booking.start_at).toLocaleString()}</td>
                <td>
                  <StatusIndicator status={booking.status} />
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
                  <AdditionalWorkPanel bookingId={booking.id} refreshKey={events.length} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2 style={{ marginTop: "2rem" }}>Шины на хранении</h2>
      {tireSets.length === 0 && <p style={{ color: "var(--color-muted)" }}>Сейчас никто не хранит шины.</p>}
      {tireSets.length > 0 && (
        <table border={1} cellPadding={6} style={{ borderCollapse: "collapse" }}>
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
                  <button type="button" className="link-button" onClick={() => handleIssueTireSet(t.id)}>
                    Выдать
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ marginTop: "2rem" }}>
        <button type="button" className="link-button" onClick={() => setShowArchive((v) => !v)}>
          {showArchive ? "Скрыть журнал" : `Показать журнал завершённых/отменённых (${archive.length})`}
        </button>
        {showArchive && (
          <div style={{ marginTop: "1rem", overflowX: "auto" }}>
            <ArchiveTable entries={archive} />
          </div>
        )}
      </div>

      <EventLog events={events} />
    </div>
  );
}
