import { describe, expect, it } from "vitest";

import { formatRemaining, formatUntil } from "./countdownFormat";

describe("formatRemaining", () => {
  it("меньше часа — только мм:сс", () => {
    expect(formatRemaining(65_000)).toBe("01:05");
  });

  it(
    "найденный пользователем реальный баг (2026-09-18): долгая услуга (>1ч) показывает часы, а не голые минуты (было '1426:33')",
    () => {
      // 23ч 46мин 33с — тот самый пример из отчёта пользователя.
      const ms = ((23 * 60 + 46) * 60 + 33) * 1000;
      expect(formatRemaining(ms)).toBe("23:46:33");
    },
  );

  it("больше суток — добавляет дни перед чч:мм:сс", () => {
    const ms = (25 * 3600 + 2 * 60 + 3) * 1000;
    expect(formatRemaining(ms)).toBe("1д 01:02:03");
  });

  it("ноль/отрицательное — 00:00", () => {
    expect(formatRemaining(0)).toBe("00:00");
    expect(formatRemaining(-5000)).toBe("00:00");
  });
});

describe("formatUntil", () => {
  it("прошедший момент — 'уже наступило'", () => {
    expect(formatUntil(0)).toBe("уже наступило");
  });

  it("меньше часа — минуты и секунды", () => {
    expect(formatUntil(90_000)).toBe("1 мин 30 с");
  });

  it("несколько часов — часы и минуты", () => {
    expect(formatUntil((3 * 60 + 15) * 60 * 1000)).toBe("3 ч 15 мин");
  });

  it("больше суток — дни и часы", () => {
    expect(formatUntil((26 * 60) * 60 * 1000)).toBe("1 дн 2 ч");
  });
});
