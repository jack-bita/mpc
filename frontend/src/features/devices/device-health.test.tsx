// device-health.test.tsx — Hali ya vifaa on the manager's phone (SYNC-14): what each device's card says,
// the one that hasn't synced today marked, a clock out by more than 2 minutes, the week's offline
// periods, one whose clock was put back, and a refusal where the manager sees it.
import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal } from "@/test/fake-server";
import { render } from "@/test/render";

import { DeviceHealthScreen } from "./device-health";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type DeviceHealth = components["schemas"]["DeviceHealth"];

const ME = "/api/auth/me/";
const HEALTH = "/api/v1/people/devices/health/";

// 14 Nov 2026, 18:45 in Arusha (15:45 UTC): the manager looks in the evening.
const NOW = "2026-11-14T15:45:00Z";

const OWNER = whoIsHere([
  { side: DAWA, permissions: ["device.manage"] },
  { side: VYAKULA, permissions: ["device.manage"] },
]);

/** The Dawa laptop: synced five minutes ago, nothing waiting, its clock 6 minutes slow, cut off twice. */
const DAWA_LAPTOP: DeviceHealth = {
  id: "019a5e00-0000-7000-8000-000000000001",
  name: "Laptop ya Dawa",
  code: 1,
  home_side: DAWA.id,
  status: "active",
  last_synced_at: "2026-11-14T15:40:00Z",
  unsent_count: 0,
  app_version: "995a337",
  clock_error_seconds: -360,
  outages: [
    {
      // Today, 10:05 to 10:15 in Arusha.
      id: "019a8000-0000-7000-8000-000000000002",
      started_at: "2026-11-14T07:05:00Z",
      ended_at: "2026-11-14T07:15:00Z",
    },
    {
      // Thursday, 15:30 to 15:45.
      id: "019a8000-0000-7000-8000-000000000001",
      started_at: "2026-11-12T12:30:00Z",
      ended_at: "2026-11-12T12:45:00Z",
    },
  ],
};

/** The Vyakula laptop: last synced yesterday at 17:02, 3 records still on it, its clock right. */
const VYAKULA_LAPTOP: DeviceHealth = {
  id: "019a5e00-0000-7000-8000-000000000002",
  name: "Laptop ya Vyakula",
  code: 2,
  home_side: VYAKULA.id,
  status: "active",
  last_synced_at: "2026-11-13T14:02:00Z",
  unsent_count: 3,
  app_version: "995a337",
  clock_error_seconds: 40,
  outages: [],
};

function healthAnswers(...devices: DeviceHealth[]) {
  answer("GET", ME, { status: 200, body: OWNER });
  answer("GET", HEALTH, { status: 200, body: devices });
}

/** One device's card, found by its name. */
async function cardOf(name: string): Promise<HTMLElement> {
  const heading = await screen.findByRole("heading", { name });
  const card = heading.closest("[data-slot=card]");
  if (!(card instanceof HTMLElement)) throw new Error(`No card for ${name}`);
  return card;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(NOW));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Hali ya vifaa", () => {
  it("says, for each device, when it synced, what waits, its clock, its app and its week offline", async () => {
    healthAnswers(DAWA_LAPTOP, VYAKULA_LAPTOP);

    render(<DeviceHealthScreen />);

    const card = within(await cardOf("Laptop ya Dawa"));
    expect(card.getByText("Na. 1 · Dawa")).toBeTruthy();
    expect(
      card.getByText("Kilituma mara ya mwisho: leo, saa 18:40 jioni."),
    ).toBeTruthy();
    expect(
      card.getByText("Hakuna kumbukumbu inayosubiri kutumwa."),
    ).toBeTruthy();
    expect(card.getByText("Saa yake iko nyuma kwa dakika 6.")).toBeTruthy();
    expect(card.getByText("Toleo la programu: 995a337")).toBeTruthy();
    expect(
      card.getByText("Bila mtandao wiki hii: mara 2, dakika 25 kwa jumla."),
    ).toBeTruthy();
    // Newest first, each with its day, its times in the shop's zone and its length.
    expect(
      card.getAllByRole("listitem").map((item) => item.textContent),
    ).toEqual([
      "14/11/2026: 10:05 asubuhi – 10:15 asubuhi (dakika 10)",
      "12/11/2026: 15:30 mchana – 15:45 mchana (dakika 15)",
    ]);
  });

  it("says once that the offline times are by each device's own clock", async () => {
    healthAnswers(DAWA_LAPTOP);

    render(<DeviceHealthScreen />);

    expect(
      await screen.findByText(/ni kwa saa ya kifaa chenyewe\.$/),
    ).toBeTruthy();
  });

  it("marks a device that hasn't synced on the shop's today, and no other", async () => {
    // The Vyakula laptop last synced yesterday at 17:02: the page says so, in the warning colour, and the
    // card stands out. The Dawa laptop, synced today, does not.
    healthAnswers(DAWA_LAPTOP, VYAKULA_LAPTOP);

    render(<DeviceHealthScreen />);

    const vyakula = await cardOf("Laptop ya Vyakula");
    const line = within(vyakula).getByText(
      "Hakijatuma leo. Mara ya mwisho: 13/11/2026, saa 17:02 jioni.",
    );
    expect(line.className).toContain("text-destructive");
    expect(vyakula.className).toContain("ring-destructive");
    expect(
      within(vyakula).getByText("Kumbukumbu 3 zinasubiri kutumwa."),
    ).toBeTruthy();
    expect(within(vyakula).getByText("Saa yake iko sawa.")).toBeTruthy();
    expect(
      within(vyakula).getByText("Hakijakosa mtandao wiki hii."),
    ).toBeTruthy();

    const dawa = await cardOf("Laptop ya Dawa");
    expect(dawa.className).not.toContain("ring-destructive");
  });

  it("marks a device that never synced, and says nothing it doesn't know", async () => {
    // Paired this morning, never opened since: no last sync, nothing waiting known, no clock, no app.
    healthAnswers({
      ...VYAKULA_LAPTOP,
      last_synced_at: null,
      unsent_count: null,
      app_version: "",
      clock_error_seconds: null,
    });

    render(<DeviceHealthScreen />);

    const card = await cardOf("Laptop ya Vyakula");
    expect(within(card).getByText("Hakijatuma bado.").className).toContain(
      "text-destructive",
    );
    expect(card.textContent).not.toContain("Saa yake");
    expect(card.textContent).not.toContain("Toleo");
    expect(card.textContent).not.toContain("zinasubiri");
  });

  it("says a blocked device is blocked, and doesn't mark it for not syncing", async () => {
    // A blocked laptop can't sync: its one line says why.
    healthAnswers({ ...VYAKULA_LAPTOP, status: "blocked" });

    render(<DeviceHealthScreen />);

    const card = await cardOf("Laptop ya Vyakula");
    expect(within(card).getByText("Kimezuiwa")).toBeTruthy();
    expect(card.className).not.toContain("ring-destructive");
    expect(
      within(card).getByText(
        "Kilituma mara ya mwisho: 13/11/2026, saa 17:02 jioni.",
      ),
    ).toBeTruthy();
  });

  it("says when its clock was changed during a cut, as the laptop told it, with no length", async () => {
    // Someone put the Dawa laptop's clock back 15 minutes during the cut: it ended before it began.
    healthAnswers({
      ...DAWA_LAPTOP,
      outages: [
        {
          id: "019a8000-0000-7000-8000-000000000003",
          started_at: "2026-11-14T07:05:00Z",
          ended_at: "2026-11-14T06:50:00Z",
        },
      ],
    });

    render(<DeviceHealthScreen />);

    const card = within(await cardOf("Laptop ya Dawa"));
    expect(card.getByRole("listitem").textContent).toBe(
      "14/11/2026: 10:05 asubuhi – 09:50 asubuhi (saa ya kifaa ilibadilishwa wakati huo)",
    );
    expect(card.getByText("Bila mtandao wiki hii: mara 1.")).toBeTruthy();
  });

  it("says hours and minutes for a long cut, and names the next day for one that crossed midnight", async () => {
    // The power went at 21:30 on Thursday and came back at 07:45 on Friday, the laptop kept open.
    healthAnswers({
      ...DAWA_LAPTOP,
      outages: [
        {
          id: "019a8000-0000-7000-8000-000000000004",
          started_at: "2026-11-12T18:30:00Z",
          ended_at: "2026-11-13T04:45:00Z",
        },
      ],
    });

    render(<DeviceHealthScreen />);

    const card = within(await cardOf("Laptop ya Dawa"));
    expect(card.getByRole("listitem").textContent).toBe(
      "12/11/2026: 21:30 usiku – 13/11/2026 07:45 asubuhi (saa 10 na dakika 15)",
    );
  });

  it("says why when the server refuses the page", async () => {
    answer("GET", ME, { status: 200, body: OWNER });
    answer("GET", HEALTH, refusal(403, "not_authenticated"));

    render(<DeviceHealthScreen />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Ingia kwanza",
    );
  });

  it("says so when the shop has no device yet", async () => {
    healthAnswers();

    render(<DeviceHealthScreen />);

    expect(
      await screen.findByText("Bado hakuna kifaa kilichosajiliwa."),
    ).toBeTruthy();
  });
});
