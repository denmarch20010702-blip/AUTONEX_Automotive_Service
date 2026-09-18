import { describe, expect, it } from "vitest";

import type { ParkingSpot } from "../../api/client";
import { makeBooking } from "../../testUtils/makeBooking";
import { computeSpotStates } from "./parkingSpotStatus";

function makeSpots(count: number): ParkingSpot[] {
  return Array.from({ length: count }, (_, i) => ({ id: i + 1, name: `Место ${i + 1}` }));
}

describe("computeSpotStates", () => {
  it("все места свободны, если заявок нет", () => {
    const states = computeSpotStates(makeSpots(2), []);
    expect(states.get(1)?.state).toBe("free");
    expect(states.get(2)?.state).toBe("free");
  });

  it("место занято (независимо от фазы до/после обслуживания) — UI_description.md п.52", () => {
    const waiting = makeBooking({ parking_spot_id: 1, status: "awaiting_approval" });
    const ready = makeBooking({ parking_spot_id: 2, status: "ready" });
    const states = computeSpotStates(makeSpots(2), [waiting, ready]);
    expect(states.get(1)).toEqual({ state: "occupied", booking: waiting });
    expect(states.get(2)).toEqual({ state: "occupied", booking: ready });
  });

  it("заявки на других местах не влияют на статус этого места", () => {
    const otherSpot = makeBooking({ parking_spot_id: 2, status: "ready" });
    expect(computeSpotStates(makeSpots(2), [otherSpot]).get(1)?.state).toBe("free");
  });

  it("заявка без назначенного места (parking_spot_id: null) не занимает никакое место", () => {
    const unparked = makeBooking({ parking_spot_id: null, status: "ready" });
    expect(computeSpotStates(makeSpots(1), [unparked]).get(1)?.state).toBe("free");
  });

  it(
    "UI_description.md п.51/52: свободные места резервируются (оранжевым) по одному на каждую заявку, реально сейчас на посту",
    () => {
      const onPost1 = makeBooking({ status: "on_post" });
      const onPost2 = makeBooking({ status: "on_post" });
      const occupied = makeBooking({ parking_spot_id: 1, status: "ready" });
      const states = computeSpotStates(makeSpots(4), [onPost1, onPost2, occupied]);
      expect(states.get(1)?.state).toBe("occupied");
      // Свободных мест 3 (2, 3, 4), резерв — 2 (по одной на каждую on_post
      // заявку) — первые два свободных по id зарезервированы, третье свободно.
      expect(states.get(2)?.state).toBe("reserved");
      expect(states.get(3)?.state).toBe("reserved");
      expect(states.get(4)?.state).toBe("free");
    },
  );

  it("резерв не может превысить число реально свободных мест", () => {
    const onPost1 = makeBooking({ status: "on_post" });
    const onPost2 = makeBooking({ status: "on_post" });
    const onPost3 = makeBooking({ status: "on_post" });
    const states = computeSpotStates(makeSpots(2), [onPost1, onPost2, onPost3]);
    expect(states.get(1)?.state).toBe("reserved");
    expect(states.get(2)?.state).toBe("reserved");
  });
});
