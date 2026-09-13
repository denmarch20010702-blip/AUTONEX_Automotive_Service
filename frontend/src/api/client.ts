export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface Service {
  id: number;
  name: string;
  duration_minutes: number;
  price: string;
}

export interface Booking {
  id: number;
  client_id: number;
  car_id: number;
  post_id: number;
  start_at: string;
  end_at: string;
  status: string;
  service_ends_at: string | null;
  services: Service[];
}

export interface SlotOption {
  start_at: string;
  end_at: string;
}

export interface ClientInfo {
  id: number;
  email: string;
  name: string;
}

export interface CarInfo {
  id: number;
  client_id: number;
  make: string;
  model: string;
  mileage: number;
  last_service_date: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Запрос не удался: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function listServices(): Promise<Service[]> {
  return request<Service[]>("/catalog");
}

export function createService(payload: {
  name: string;
  duration_minutes: number;
  price: number;
}): Promise<Service> {
  return request<Service>("/catalog", { method: "POST", body: JSON.stringify(payload) });
}

export function deleteService(id: number): Promise<void> {
  return request<void>(`/catalog/${id}`, { method: "DELETE" });
}

export function updateService(
  id: number,
  payload: Partial<{ name: string; duration_minutes: number; price: number }>,
): Promise<Service> {
  return request<Service>(`/catalog/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function listAllCars(): Promise<CarInfo[]> {
  return request<CarInfo[]>("/cars");
}

export function listBookings(clientId?: number): Promise<Booking[]> {
  return request<Booking[]>(clientId ? `/bookings?client_id=${clientId}` : "/bookings");
}

// `date` — обычная "YYYY-MM-DD" строка из <input type="date"> (её собственный
// календарь всегда локальный для устройства). backend'у нужен не календарный
// день сам по себе, а точный момент начала этих суток в часовом поясе
// устройства — иначе интерпретация как UTC-суток на backend'е отрезает
// вечер/ночь при ненулевом смещении (обнаружено на практике 2026-09-13,
// см. backend/app/services/slots.py). new Date("YYYY-MM-DD") трактовал бы
// строку как UTC-полночь (классическая ловушка JS) — поэтому раскладываем
// на компоненты и строим локальную полночь через многоаргументный
// конструктор Date, который как раз использует часовой пояс устройства.
function localMidnightIso(dateStr: string): string {
  const [year, month, day] = dateStr.split("-").map(Number);
  return new Date(year, month - 1, day, 0, 0, 0, 0).toISOString();
}

export function getAvailableSlots(serviceIds: number[], date: string): Promise<SlotOption[]> {
  const params = new URLSearchParams();
  serviceIds.forEach((id) => params.append("service_ids", String(id)));
  params.set("date", localMidnightIso(date));
  return request<SlotOption[]>(`/bookings/available-slots?${params.toString()}`);
}

export function createBooking(payload: {
  client_id: number;
  car_id: number;
  start_at: string;
  service_ids: number[];
}): Promise<Booking> {
  return request<Booking>("/bookings", { method: "POST", body: JSON.stringify(payload) });
}

export function updateBookingStatus(bookingId: number, status: string): Promise<Booking> {
  return request<Booking>(`/bookings/${bookingId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export interface StationStats {
  total_revenue: string;
}

export function getStationStats(): Promise<StationStats> {
  return request<StationStats>("/station/stats");
}

export interface ArchivedBooking {
  id: number;
  original_booking_id: number;
  client_id: number;
  client_name: string;
  client_email: string;
  car_id: number;
  car_make: string;
  car_model: string;
  post_id: number;
  start_at: string;
  end_at: string;
  status: string;
  total_price: string;
  services_snapshot: Array<{ id: number; name: string; price: string; duration_minutes: number }>;
  additional_works_snapshot: Array<{ id: number; description: string; price: string; proposed_by: string; status: string }>;
  created_at: string;
  archived_at: string;
}

// Журнал завершённых/отменённых заявок — по прямой просьбе пользователя,
// вместо полного удаления (см. buisness/ARCHITECTURE.md).
export function listArchive(clientId?: number): Promise<ArchivedBooking[]> {
  return request<ArchivedBooking[]>(clientId ? `/station/archive?client_id=${clientId}` : "/station/archive");
}

// Клиент — без пароля, идентификация по email (см. buisness/ARCHITECTURE.md).
// "Вход" — это просто поиск существующего клиента по email, "регистрация" —
// создание нового при отсутствии совпадения.
export async function findClientByEmail(email: string): Promise<ClientInfo | null> {
  const results = await request<ClientInfo[]>(`/clients?email=${encodeURIComponent(email)}`);
  return results[0] ?? null;
}

export function registerClient(payload: { email: string; name: string }): Promise<ClientInfo> {
  return request<ClientInfo>("/clients", { method: "POST", body: JSON.stringify(payload) });
}

export function getClient(id: number): Promise<ClientInfo> {
  return request<ClientInfo>(`/clients/${id}`);
}

export function listAllClients(): Promise<ClientInfo[]> {
  return request<ClientInfo[]>("/clients");
}

export function listCars(clientId: number): Promise<CarInfo[]> {
  return request<CarInfo[]>(`/cars?client_id=${clientId}`);
}

export function createCar(payload: {
  client_id: number;
  make: string;
  model: string;
  mileage: number;
  last_service_date: string | null;
}): Promise<CarInfo> {
  return request<CarInfo>("/cars", { method: "POST", body: JSON.stringify(payload) });
}

export function updateCar(
  id: number,
  payload: Partial<{ make: string; model: string; mileage: number; last_service_date: string | null }>,
): Promise<CarInfo> {
  return request<CarInfo>(`/cars/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteCar(id: number): Promise<void> {
  return request<void>(`/cars/${id}`, { method: "DELETE" });
}

export interface TireSet {
  id: number;
  client_id: number;
  car_id: number;
  stored_at: string;
  issued_at: string | null;
}

// Хранение шин (B1) — issued_at === null означает "на хранении сейчас".
export function listTireSets(params: { clientId?: number; carId?: number; activeOnly?: boolean }): Promise<TireSet[]> {
  const query = new URLSearchParams();
  if (params.clientId !== undefined) query.set("client_id", String(params.clientId));
  if (params.carId !== undefined) query.set("car_id", String(params.carId));
  if (params.activeOnly) query.set("active_only", "true");
  return request<TireSet[]>(`/tire-sets?${query.toString()}`);
}

export function storeTireSet(payload: { client_id: number; car_id: number }): Promise<TireSet> {
  return request<TireSet>("/tire-sets", { method: "POST", body: JSON.stringify(payload) });
}

export function issueTireSet(id: number): Promise<TireSet> {
  return request<TireSet>(`/tire-sets/${id}/issue`, { method: "POST" });
}

export interface AdditionalWork {
  id: number;
  booking_id: number;
  description: string;
  price: string;
  duration_minutes: number;
  proposed_by: "mechanic" | "ai";
  status: "pending" | "approved" | "declined";
  created_at: string;
}

// Согласование доп. работ (B2) — предлагается сразу при обнаружении;
// сама доп. работа не начинается без ответа клиента, но статус заявки
// (A5) этим не блокируется — станция может продолжать уже согласованное.
export function listAdditionalWorks(bookingId: number): Promise<AdditionalWork[]> {
  return request<AdditionalWork[]>(`/bookings/${bookingId}/additional-works`);
}

// UI_description.md п.19: доп. работа выбирается кликом из каталога услуг,
// не вводится вручную — backend сам берёт название/цену/длительность из
// выбранной услуги.
export function proposeAdditionalWork(bookingId: number, payload: { service_id: number }): Promise<AdditionalWork> {
  return request<AdditionalWork>(`/bookings/${bookingId}/additional-works`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// UI_description.md п.17: количество неотвеченных предложений доп. работы
// клиента — на этом держится красная точка у "Личный кабинет" в шапке.
export async function getPendingAdditionalWorksCount(clientId: number): Promise<number> {
  const result = await request<{ count: number }>(`/clients/${clientId}/additional-works/pending-count`);
  return result.count;
}

export function respondAdditionalWork(id: number, status: "approved" | "declined"): Promise<AdditionalWork> {
  return request<AdditionalWork>(`/additional-works/${id}/respond`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}
