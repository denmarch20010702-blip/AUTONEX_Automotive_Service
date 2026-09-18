import { describe, expect, it } from "vitest";

import { formatSlotLabel } from "./formatSlotLabel";

describe("formatSlotLabel", () => {
  it("форматирует ISO-момент как ДД.ММ.ГГГГ - ЧЧ:ММ", () => {
    // Локальная полночь конкретной даты — без часового пояса в строке,
    // чтобы результат не зависел от TZ окружения, где гоняются тесты.
    const iso = new Date(2026, 2, 5, 9, 30).toISOString();
    expect(formatSlotLabel(iso)).toBe("05.03.2026 - 09:30");
  });

  it("дополняет однозначные день/месяц/час/минуту нулём слева", () => {
    const iso = new Date(2026, 0, 1, 0, 5).toISOString();
    expect(formatSlotLabel(iso)).toBe("01.01.2026 - 00:05");
  });
});
