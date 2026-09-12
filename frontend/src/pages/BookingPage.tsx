import { useEffect, useState } from "react";

import {
  createBooking,
  getAvailableSlots,
  listCars,
  listServices,
  type Booking,
  type CarInfo,
  type ClientInfo,
  type Service,
  type SlotOption,
} from "../api/client";
import { AddCarForm } from "../components/booking/AddCarForm";
import { CarPicker } from "../components/booking/CarPicker";
import { IdentifyForm } from "../components/booking/IdentifyForm";
import { ServiceTiles } from "../components/booking/ServiceTiles";
import { SlotPicker } from "../components/booking/SlotPicker";
import { SuccessCard } from "../components/booking/SuccessCard";
import { useClientSession } from "../session/ClientSessionContext";

type Step = "services" | "slots" | "identify" | "car" | "add-car" | "success";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

// Мастер записи по шагам из buisness/UI_description.md: услуги → слот →
// вход/регистрация по email (без пароля, только для тех, кто ещё не вошёл
// через личный кабинет) → выбор или добавление автомобиля → подтверждение.
// Личность клиента берётся из общего ClientSessionContext — если клиент уже
// вошёл (в кабинете или в прошлый раз на этом браузере), шаг "identify"
// целиком пропускается, и повторно вводить email не нужно.
export function BookingPage() {
  const { client, login } = useClientSession();
  const [step, setStep] = useState<Step>("services");
  const [error, setError] = useState<string | null>(null);

  const [services, setServices] = useState<Service[] | null>(null);
  const [selectedServiceIds, setSelectedServiceIds] = useState<number[]>([]);

  const [date, setDate] = useState(todayIso());
  const [slots, setSlots] = useState<SlotOption[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<SlotOption | null>(null);

  const [cars, setCars] = useState<CarInfo[]>([]);

  const [booking, setBooking] = useState<Booking | null>(null);

  useEffect(() => {
    listServices()
      .then(setServices)
      .catch((err) => setError((err as Error).message));
  }, []);

  useEffect(() => {
    if (step !== "slots") return;
    setSlotsLoading(true);
    setError(null);
    getAvailableSlots(selectedServiceIds, date)
      .then(setSlots)
      .catch((err) => setError((err as Error).message))
      .finally(() => setSlotsLoading(false));
  }, [step, date, selectedServiceIds]);

  const toggleService = (id: number) => {
    setSelectedServiceIds((prev) =>
      prev.includes(id) ? prev.filter((existing) => existing !== id) : [...prev, id],
    );
  };

  const goToCarStep = async (activeClient: ClientInfo) => {
    setError(null);
    try {
      const clientCars = await listCars(activeClient.id);
      setCars(clientCars);
      setStep(clientCars.length > 0 ? "car" : "add-car");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const handleSlotSelected = (slot: SlotOption) => {
    setSelectedSlot(slot);
    if (client) {
      goToCarStep(client);
    } else {
      setStep("identify");
    }
  };

  const handleIdentified = (identified: ClientInfo) => {
    login(identified);
    goToCarStep(identified);
  };

  const confirmBooking = async (carId: number) => {
    if (!selectedSlot || !client) return;
    setError(null);
    try {
      const created = await createBooking({
        client_id: client.id,
        car_id: carId,
        start_at: selectedSlot.start_at,
        service_ids: selectedServiceIds,
      });
      setBooking(created);
      setStep("success");
    } catch (err) {
      setError((err as Error).message);
      // Слот мог занять кто-то другой прямо сейчас — возвращаем к выбору
      // времени и заново запрашиваем актуальный список свободных слотов.
      setSelectedSlot(null);
      setStep("slots");
    }
  };

  const restart = () => {
    setStep("services");
    setSelectedServiceIds([]);
    setSelectedSlot(null);
    setBooking(null);
    setError(null);
  };

  return (
    <div>
      {error && <div className="error-banner">{error}</div>}

      {step === "services" && (
        <>
          <h1 className="step-title">Выбери услугу</h1>
          <p className="step-subtitle">Можно выбрать несколько — время рассчитается на все сразу</p>
          {services === null && <p style={{ textAlign: "center" }}>Загрузка...</p>}
          {services && (
            <>
              <ServiceTiles
                services={services}
                selectedIds={selectedServiceIds}
                onToggle={toggleService}
              />
              <div className="wizard-nav" style={{ justifyContent: "center" }}>
                <button
                  type="button"
                  className="primary-button"
                  disabled={selectedServiceIds.length === 0}
                  onClick={() => setStep("slots")}
                >
                  Далее
                </button>
              </div>
            </>
          )}
        </>
      )}

      {step === "slots" && (
        <>
          <h1 className="step-title">Выбери время</h1>
          <p className="step-subtitle">Свободные слоты на выбранную дату</p>
          <SlotPicker
            date={date}
            onDateChange={setDate}
            slots={slots}
            selected={selectedSlot}
            onSelect={handleSlotSelected}
            loading={slotsLoading}
          />
          <div className="wizard-nav">
            <button type="button" className="link-button" onClick={() => setStep("services")}>
              Назад к услугам
            </button>
          </div>
        </>
      )}

      {step === "identify" && (
        <>
          <h1 className="step-title">Вход</h1>
          <p className="step-subtitle">Укажи email, чтобы завершить запись</p>
          <IdentifyForm onIdentified={handleIdentified} />
        </>
      )}

      {step === "car" && (
        <>
          <h1 className="step-title">Выбери автомобиль</h1>
          <CarPicker cars={cars} onSelect={(car) => confirmBooking(car.id)} onAddNew={() => setStep("add-car")} />
        </>
      )}

      {step === "add-car" && client && (
        <>
          <h1 className="step-title">Добавь автомобиль</h1>
          <AddCarForm
            clientId={client.id}
            onCreated={(car) => {
              setCars((prev) => [...prev, car]);
              confirmBooking(car.id);
            }}
            onCancel={() => setStep(cars.length > 0 ? "car" : "identify")}
          />
        </>
      )}

      {step === "success" && booking && (
        <SuccessCard
          bookingId={booking.id}
          startAt={booking.start_at}
          initialStatus={booking.status}
          onRestart={restart}
        />
      )}
    </div>
  );
}
