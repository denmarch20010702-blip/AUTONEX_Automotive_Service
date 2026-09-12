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
}

export interface SlotOption {
  start_at: string;
  end_at: string;
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

export function listBookings(): Promise<Booking[]> {
  return request<Booking[]>("/bookings");
}

export function getAvailableSlots(serviceIds: number[], date: string): Promise<SlotOption[]> {
  const params = new URLSearchParams();
  serviceIds.forEach((id) => params.append("service_ids", String(id)));
  params.set("date", date);
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
