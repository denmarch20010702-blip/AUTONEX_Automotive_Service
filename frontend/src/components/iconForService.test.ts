import { describe, expect, it } from "vitest";

import { iconForService } from "./iconForService";
import { BrakeIcon, DiagnosticsIcon, OilIcon, TireIcon, WashIcon, WrenchIcon } from "./icons";

describe("iconForService", () => {
  it.each([
    ["Замена масла", OilIcon],
    ["Oil change", OilIcon],
    ["Замена шин", TireIcon],
    ["Ремонт тормозов", BrakeIcon],
    ["Диагностика подвески", DiagnosticsIcon],
    ["Мойка кузова", WashIcon],
  ])("подбирает нужную иконку по ключевому слову для %s", (name, expected) => {
    expect(iconForService(name)).toBe(expected);
  });

  it("возвращает иконку-гаечный ключ по умолчанию, если ничего не совпало", () => {
    expect(iconForService("Полировка кузова")).toBe(WrenchIcon);
  });

  it("не срабатывает на ложном совпадении подстроки (найденный реальный баг в rule-based ИИ-диагностике был похож — см. ARCHITECTURE.md про C4)", () => {
    // "авто" не должно совпасть с "то" как отдельным словом-ключом — здесь
    // проверяем то же самое свойство на стороне подбора иконки: "автомойка"
    // должна матчиться по "мойк", а не давать неожиданный ключ где-то ещё.
    expect(iconForService("Автомойка")).toBe(WashIcon);
  });
});
