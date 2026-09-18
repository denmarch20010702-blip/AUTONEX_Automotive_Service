import { describe, expect, it } from "vitest";

import { makeBooking } from "../../testUtils/makeBooking";
import { statusOf } from "./postStatus";

describe("statusOf", () => {
  it("пост свободен, если на нём нет заявок", () => {
    expect(statusOf([], 1).state).toBe("free");
  });

  it("пост занят, если на нём заявка со статусом on_post", () => {
    const active = makeBooking({ post_id: 1, status: "on_post" });
    const result = statusOf([active], 1);
    expect(result.state).toBe("busy");
    expect(result.booking).toBe(active);
  });

  it("пост зарезервирован, если ближайшая accepted-заявка начинается скоро", () => {
    const soon = makeBooking({
      post_id: 1,
      status: "accepted",
      start_at: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
    });
    const result = statusOf([soon], 1);
    expect(result.state).toBe("reserved");
  });

  it("дальняя accepted-заявка (не в пределах 2 часов) не делает пост занятым на вид", () => {
    const farAway = makeBooking({
      post_id: 1,
      status: "accepted",
      start_at: new Date(Date.now() + 5 * 60 * 60 * 1000).toISOString(),
    });
    expect(statusOf([farAway], 1).state).toBe("free");
  });

  it(
    "найденный на практике реальный баг (2026-09-16): пост busy показывает и следующую в очереди заявку ('Далее:'), а не только текущую",
    () => {
      const active = makeBooking({ post_id: 1, status: "on_post" });
      const next = makeBooking({
        post_id: 1,
        status: "accepted",
        start_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
      });
      const result = statusOf([active, next], 1);
      expect(result.state).toBe("busy");
      expect(result.booking).toBe(active);
      expect(result.next).toBe(next);
    },
  );

  it("заявки на других постах не влияют на статус этого поста", () => {
    const otherPost = makeBooking({ post_id: 2, status: "on_post" });
    expect(statusOf([otherPost], 1).state).toBe("free");
  });
});
