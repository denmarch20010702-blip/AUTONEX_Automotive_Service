import { useCallback, useEffect, useState } from "react";

import {
  deleteService,
  getStationStats,
  listAllCars,
  listArchive,
  listBookings,
  listServices,
  type ArchivedBooking,
  type Booking,
  type CarInfo,
  type Service,
} from "../api/client";
import { useBookingEvents } from "../api/events";
import { EventLog } from "../components/EventLog";
import { StatusIndicator } from "../components/StatusIndicator";
import { AddServiceForm } from "../components/station/AddServiceForm";
import { ArchiveTable } from "../components/station/ArchiveTable";
import { BookingActions } from "../components/station/BookingActions";
import { iconForService } from "../components/icons";

export function StationPage() {
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [services, setServices] = useState<Service[] | null>(null);
  const [cars, setCars] = useState<CarInfo[]>([]);
  const [revenue, setRevenue] = useState<string | null>(null);
  const [archive, setArchive] = useState<ArchivedBooking[]>([]);
  const [showArchive, setShowArchive] = useState(false);
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

  useEffect(() => {
    reloadBookings();
    reloadServices();
    reloadCars();
    reloadRevenue();
    reloadArchive();
  }, [reloadBookings, reloadServices, reloadCars, reloadRevenue, reloadArchive]);

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
    }
  }, [events, reloadBookings, reloadCars, reloadRevenue, reloadArchive]);

  const handleDeleteService = async (id: number) => {
    if (!window.confirm("Удалить эту услугу из каталога?")) return;
    try {
      await deleteService(id);
      setServices((prev) => (prev ?? []).filter((s) => s.id !== id));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const carLabel = (carId: number): string => {
    const car = cars.find((c) => c.id === carId);
    return car ? `${car.make} ${car.model}` : `#${carId}`;
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
        {services?.map((service) => {
          const Icon = iconForService(service.name);
          return (
            <div key={service.id} className="tile-button" style={{ cursor: "default", position: "relative" }}>
              <button
                type="button"
                onClick={() => handleDeleteService(service.id)}
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
        })}
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
