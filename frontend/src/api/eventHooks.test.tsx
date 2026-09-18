import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDebouncedEventTick } from "./eventHooks";
import { EventsContext, type BookingEvent } from "./eventsContext";

function makeEvent(overrides: Partial<BookingEvent> = {}): BookingEvent {
  return {
    type: "booking_status_changed",
    data: {},
    receivedAt: new Date().toISOString(),
    ...overrides,
  };
}

// Регресс-тест на найденный на практике реальный баг (2026-09-15,
// пользователь: "невозможно перейти в кабинет станции — не открывался") —
// см. eventHooks.ts. Без дебаунса каждое отдельное SSE-событие в пачке
// вызывало бы отдельный тик/перезапрос; здесь проверяем именно то свойство,
// которое чинит баг: пачка событий даёт ОДИН тик, а не по одному на событие.
describe("useDebouncedEventTick", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("не тикает, пока событий не было", () => {
    const { result } = renderHook(() => useDebouncedEventTick(400), {
      wrapper: ({ children }) => (
        <EventsContext.Provider value={[]}>{children}</EventsContext.Provider>
      ),
    });
    expect(result.current).toBe(0);
  });

  it("пачка из нескольких событий подряд даёт ровно один тик, а не один на каждое", () => {
    let events: BookingEvent[] = [];
    const { result, rerender } = renderHook(() => useDebouncedEventTick(400), {
      wrapper: ({ children }) => (
        <EventsContext.Provider value={events}>{children}</EventsContext.Provider>
      ),
    });

    // Три события подряд, каждое приходит раньше, чем истекли 400мс после
    // предыдущего — имитация всплеска (например, серия propose/respond по
    // доп. работам, где каждый шаг публикует своё SSE-событие).
    events = [makeEvent()];
    act(() => rerender());
    act(() => vi.advanceTimersByTime(200));

    events = [makeEvent(), ...events];
    act(() => rerender());
    act(() => vi.advanceTimersByTime(200));

    events = [makeEvent(), ...events];
    act(() => rerender());

    // Тишина после последнего события ещё не достигла 400мс — тика не было.
    act(() => vi.advanceTimersByTime(399));
    expect(result.current).toBe(0);

    // Ровно через 400мс тишины после ПОСЛЕДНЕГО события — один тик.
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe(1);
  });

  it("два отдельных всплеска с паузой между ними дают два отдельных тика", () => {
    let events: BookingEvent[] = [];
    const { result, rerender } = renderHook(() => useDebouncedEventTick(400), {
      wrapper: ({ children }) => (
        <EventsContext.Provider value={events}>{children}</EventsContext.Provider>
      ),
    });

    events = [makeEvent()];
    act(() => rerender());
    act(() => vi.advanceTimersByTime(400));
    expect(result.current).toBe(1);

    events = [makeEvent(), ...events];
    act(() => rerender());
    act(() => vi.advanceTimersByTime(400));
    expect(result.current).toBe(2);
  });
});
