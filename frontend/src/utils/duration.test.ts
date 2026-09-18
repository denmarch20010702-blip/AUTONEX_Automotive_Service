import { describe, expect, it } from "vitest";

import { formatDuration, splitMinutes, toTotalMinutes } from "./duration";

describe("formatDuration", () => {
  it("показывает только минуты, если меньше часа", () => {
    expect(formatDuration(45)).toBe("45 мин");
  });

  it("показывает только часы, если минут нет", () => {
    expect(formatDuration(120)).toBe("2 ч");
  });

  it("показывает и часы, и минуты", () => {
    expect(formatDuration(95)).toBe("1 ч 35 мин");
  });

  it("0 минут — это 0 мин, а не пустая строка", () => {
    expect(formatDuration(0)).toBe("0 мин");
  });
});

describe("toTotalMinutes / splitMinutes", () => {
  it("складывают часы и минуты в общее число минут", () => {
    expect(toTotalMinutes("1", "35")).toBe(95);
  });

  it("не ломаются на пустой строке (недописанный ввод в форме)", () => {
    expect(toTotalMinutes("", "")).toBe(0);
    expect(toTotalMinutes("2", "")).toBe(120);
  });

  it("splitMinutes — обратная операция к toTotalMinutes", () => {
    expect(splitMinutes(95)).toEqual({ hours: "1", minutes: "35" });
    expect(splitMinutes(45)).toEqual({ hours: "0", minutes: "45" });
  });
});
