import { useCallback, useEffect, useState } from "react";

import {
  getStationStats,
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
  type StationStats,
  type TireSet,
  type TireSetArchiveEntry,
} from "../api/client";
import { useBookingEvents, useDebouncedEventTick } from "../api/events";
import { Countdown, UpcomingCountdown } from "../components/Countdown";
import { EventLog } from "../components/EventLog";
import { NotificationDot } from "../components/NotificationDot";
import { OdometerNumber } from "../components/OdometerNumber";
import { Pagination } from "../components/Pagination";
import { StatusIndicator } from "../components/StatusIndicator";
import { formatSlotLabel } from "../components/booking/SlotPicker";
import { AddServiceForm } from "../components/station/AddServiceForm";
import { AdditionalWorkPanel } from "../components/station/AdditionalWorkPanel";
import { ArchiveTable } from "../components/station/ArchiveTable";
import { BookingActions } from "../components/station/BookingActions";
import { EditableServiceTile } from "../components/station/EditableServiceTile";
import { PostsBoard } from "../components/station/PostsBoard";
import { TireSetArchiveTable } from "../components/TireSetArchiveTable";

// UI_description.md п.45 (2026-09-15) — только сами цифры катятся в
// OdometerNumber, разряды разделяем пробелом (ru-RU), без копеек — для
// компактного счётчика в углу это достаточная точность.
function formatMoney(value: string | number): string {
  return `${Math.round(Number(value)).toLocaleString("ru-RU")} ₽`;
}

// "Сегодня" — сутки по UTC (та же осознанная договорённость про часовой
// пояс, что и у today_revenue на backend'е, station.py) — не по локальному
// времени станции/клиента.
function isTodayUtc(startAtIso: string): boolean {
  const start = new Date(startAtIso);
  const now = new Date();
  return (
    start.getUTCFullYear() === now.getUTCFullYear() &&
    start.getUTCMonth() === now.getUTCMonth() &&
    start.getUTCDate() === now.getUTCDate()
  );
}

export function StationPage() {
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [services, setServices] = useState<Service[] | null>(null);
  const [cars, setCars] = useState<CarInfo[]>([]);
  const [clients, setClients] = useState<ClientInfo[]>([]);
  const [stats, setStats] = useState<StationStats | null>(null);
  const [archive, setArchive] = useState<ArchivedBooking[]>([]);
  const [archiveTotal, setArchiveTotal] = useState(0);
  const [archivePage, setArchivePage] = useState(1);
  const [showArchive, setShowArchive] = useState(false);
  const [tireSets, setTireSets] = useState<TireSet[]>([]);
  const [tireArchive, setTireArchive] = useState<TireSetArchiveEntry[]>([]);
  const [tireArchiveTotal, setTireArchiveTotal] = useState(0);
  const [tireArchivePage, setTireArchivePage] = useState(1);
  const [showTireArchive, setShowTireArchive] = useState(false);
  // Прямая просьба пользователя (2026-09-17): кнопка-переключатель "Все
  // заявки" ⇄ "заявки на сегодня" — тот же принцип "сегодня", что и везде в
  // проекте (сутки по UTC, см. today_revenue в station.py), чтобы не вводить
  // ещё одну трактовку часового пояса.
  const [showTodayOnly, setShowTodayOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const events = useBookingEvents();
  const reloadTick = useDebouncedEventTick();

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

  const reloadStats = useCallback(() => {
    getStationStats()
      .then(setStats)
      .catch((err) => setError(err.message));
  }, []);

  const reloadArchive = useCallback(() => {
    listArchive(undefined, archivePage)
      .then((res) => {
        setArchive(res.items);
        setArchiveTotal(res.total);
      })
      .catch((err) => setError(err.message));
  }, [archivePage]);

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
    listTireSetArchive(undefined, tireArchivePage)
      .then((res) => {
        setTireArchive(res.items);
        setTireArchiveTotal(res.total);
      })
      .catch((err) => setError(err.message));
  }, [tireArchivePage]);

  useEffect(() => {
    reloadBookings();
    reloadServices();
    reloadCars();
    reloadStats();
    reloadArchive();
    reloadClients();
    reloadTireSets();
    reloadTireArchive();
  }, [
    reloadBookings,
    reloadServices,
    reloadCars,
    reloadStats,
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
    if (reloadTick > 0) {
      reloadBookings();
      reloadCars();
      reloadStats();
      reloadArchive();
      // Каталог услуг раньше не входил в цикл живого обновления — если
      // услугу удаляли в одной вкладке, в другой она "призраком" оставалась
      // видна до ручного обновления страницы (заметка пользователя №5).
      // Каталог не шлёт SSE-события сам по себе, но раз уж событие всё
      // равно прилетело — заодно освежаем и его.
      reloadServices();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadTick, reloadBookings, reloadCars, reloadStats, reloadArchive, reloadServices]);

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

  return (
    <div>
      <h1 className="step-title">Экран станции</h1>

      {/* UI_description.md п.45 (2026-09-15): "Заработано станцией" — в
          самый верх страницы, без визуальных изменений (тот же вид, что и
          раньше, просто выше — было под доской постов). */}
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
        <div style={{ fontSize: "1.8rem", fontWeight: 700 }}>
          {stats ? formatMoney(stats.total_revenue) : "…"}
        </div>
      </div>

      {/* UI_description.md п.45 — компактная панель метрик под "Заработано
          станцией", прижата к правому краю (тот же край, что у панелей
          ниже). Заменяет прежние 4 счётчика очереди заявок (B7) — очередь
          задач уже видна отдельно, в панели доп. работ у каждой заявки. */}
      {stats && (
        <div className="station-top-metrics">
          <div className="station-top-metrics__card station-top-metrics__card--revenue">
            <div className="station-top-metrics__row">
              <span className="station-top-metrics__label">За всё время</span>
              <OdometerNumber value={formatMoney(stats.total_revenue)} />
            </div>
            <div className="station-top-metrics__row">
              <span className="station-top-metrics__label">За сегодня</span>
              <OdometerNumber value={formatMoney(stats.today_revenue)} />
            </div>
          </div>
          <div className="station-top-metrics__card">
            <span className="station-top-metrics__value">
              {stats.average_check !== null ? formatMoney(stats.average_check) : "—"}
            </span>
            <span className="station-top-metrics__label">Средний чек</span>
          </div>
          <div className="station-top-metrics__card">
            <span className="station-top-metrics__value">
              {stats.completion_rate_percent !== null ? `${stats.completion_rate_percent}%` : "—"}
            </span>
            <span className="station-top-metrics__label">Выполнено vs отменено</span>
          </div>
          <div className="station-top-metrics__card">
            <span className="station-top-metrics__value">
              {stats.additional_work_conversion_percent !== null
                ? `${stats.additional_work_conversion_percent}%`
                : "—"}
            </span>
            <span className="station-top-metrics__label">Конверсия доп. работ</span>
          </div>
        </div>
      )}

      <PostsBoard bookings={bookings ?? []} clients={clients} cars={cars} />

      {error && <div className="error-banner">{error}</div>}

      {/* UI_description.md п.45 (2026-09-15): "окно заявок поменять местами
          с каталогом услуг" — "Все заявки" теперь выше "Каталога услуг". */}
      <div className="panel">
        <div className="panel-header">
          <h2>{showTodayOnly ? "Заявки на сегодня" : "Все заявки"}</h2>
          {bookings && bookings.length > 0 && (
            <button type="button" className="ghost-button" onClick={() => setShowTodayOnly((v) => !v)}>
              {showTodayOnly ? "Показать заявки за всё время" : "Показать заявки на сегодня"}
            </button>
          )}
        </div>
        {(() => {
          const displayedBookings = showTodayOnly
            ? (bookings ?? []).filter((b) => isTodayUtc(b.start_at))
            : bookings;
          return (
            <>
              {!error && displayedBookings === null && <p className="panel-empty">Загрузка...</p>}
              {displayedBookings && displayedBookings.length === 0 && (
                <p className="panel-empty">
                  {showTodayOnly ? "На сегодня заявок нет." : "Заявок пока нет."}
                </p>
              )}
              {displayedBookings && displayedBookings.length > 0 && (
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
                {displayedBookings.map((booking) => {
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
                        <Countdown
                          targetIso={booking.service_ends_at}
                          startedIso={booking.on_post_started_at}
                        />
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
                          reloadStats();
                        }}
                        onError={setError}
                      />
                    </td>
                    <td>
                      <AdditionalWorkPanel
                        bookingId={booking.id}
                        bookingStatus={booking.status}
                        services={services ?? []}
                        refreshKey={reloadTick}
                      />
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
              )}
            </>
          );
        })()}
      </div>

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

      {/* UI_description.md п.45: "журнал и журнал приёма и выдачи шин
          поменять местами" — журнал станции теперь выше блока хранения шин
          (у которого свой вложенный журнал приёма/выдачи ниже). */}
      <div className="panel">
        <div className="panel-header">
          <h2>Журнал</h2>
          <button type="button" className="ghost-button" onClick={() => setShowArchive((v) => !v)}>
            {showArchive ? "Скрыть" : `Показать (${archiveTotal})`}
          </button>
        </div>
        {showArchive && (
          <>
            <Pagination page={archivePage} total={archiveTotal} pageSize={50} onChange={setArchivePage} />
            <ArchiveTable entries={archive} />
            <Pagination page={archivePage} total={archiveTotal} pageSize={50} onChange={setArchivePage} />
          </>
        )}
      </div>

      <div className="panel">
        <div className="panel-header">
          {/* UI_description.md п.45: счётчик комплектов, которые прямо
              сейчас на хранении, рядом с названием таблицы. */}
          <h2>Шины на хранении ({tireSets.length})</h2>
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
                </tr>
              </thead>
              <tbody>
                {tireSets.map((t) => (
                  <tr key={t.id}>
                    <td>{clientLabel(t.client_id)}</td>
                    <td>{carLabel(t.car_id)}</td>
                    <td>{new Date(t.stored_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {/* UI_description.md п.47 (2026-09-16): выдача теперь возможна
            только во время реального визита на "Получить/сдать шины" —
            станция больше не выдаёт шины напрямую кликом из этой таблицы,
            клиент сам запускает выдачу из личного кабинета во время визита. */}
        <div className="panel-header" style={{ marginTop: "1rem" }}>
          <h3 style={{ margin: 0 }}>Журнал приёма и выдачи шин</h3>
          <button type="button" className="ghost-button" onClick={() => setShowTireArchive((v) => !v)}>
            {showTireArchive ? "Скрыть" : `Показать (${tireArchiveTotal})`}
          </button>
        </div>
        {showTireArchive && (
          <>
            <Pagination page={tireArchivePage} total={tireArchiveTotal} pageSize={50} onChange={setTireArchivePage} />
            <TireSetArchiveTable entries={tireArchive} />
            <Pagination page={tireArchivePage} total={tireArchiveTotal} pageSize={50} onChange={setTireArchivePage} />
          </>
        )}
      </div>

      <EventLog events={events} />
    </div>
  );
}
