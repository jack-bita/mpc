// needs-attention.test.tsx — the records the server refused, on the counter (SYNC-11, SYNC-8, 03 §6.3): each
// set aside on the laptop, never sent again; the counter names what it was, says why in words of its own for
// each of the server's reasons, and says to tell the manager, as a resend can't mend it.
import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { setLanguage } from "@/i18n/language";
import { saveDocument } from "@/offline/outbox";
import { LAST_DEVICE_SEQ } from "@/offline/sync/meta";
import { shopDatabase } from "@/offline/this-shop";
import { DAWA_LAPTOP } from "@/test/devices";
import { swahiliIn } from "@/test/language";
import { staffRow, theLaptopKnows } from "@/test/laptop";
import { render } from "@/test/render";

import { NeedsAttention } from "./needs-attention";

// A seller on the laptop. A fake person.
const ASHA = staffRow(
  "019a5e00-0000-7000-8000-0000000000c2",
  "Asha Mfano",
  "Asha",
);

const db = () => shopDatabase(DAWA_LAPTOP.shop.id);

/** Now, as the tests read the warning: 08:10 in Dar on 13 November. */
const NOW = new Date("2026-11-13T05:10:00Z");

/** A record saved on the laptop, by default at 07:55 in Dar that same morning, then refused by the server for
 * `reason`, as the push sets one aside (push.ts). The laptop's clock is back at NOW after. */
async function refused(
  reason: string,
  {
    draft = {
      type: "clock",
      payload: { kind: "in", last_server_time: "2026-11-13T04:00:00Z" },
    },
    at = "2026-11-13T04:55:00Z",
  }: { draft?: { type: string; payload: object }; at?: string } = {},
) {
  vi.setSystemTime(new Date(at));
  const saved = await saveDocument(db(), {
    ...draft,
    schema_version: 1,
    created_by: ASHA.id,
  });
  await db().outbox.update(saved.id, {
    status: "needs_attention",
    last_error: reason,
  });
  vi.setSystemTime(NOW);
  return saved;
}

/** The warning, once its rows are read. */
const theWarning = () =>
  screen.findByRole("alert", { name: "Kumbukumbu zilizokataliwa na seva" });

beforeEach(async () => {
  // The time only: the test database runs on timers that must stay real.
  vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ["Date"] });
  saveDevice(DAWA_LAPTOP);
  await theLaptopKnows(ASHA);
  await db().meta.put({ key: LAST_DEVICE_SEQ, value: 57 });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("the records the server refused", () => {
  it("shows nothing while the server refused nothing", async () => {
    await saveDocument(db(), {
      type: "clock",
      schema_version: 1,
      created_by: ASHA.id,
      payload: { kind: "in", last_server_time: "2026-11-13T04:00:00Z" },
    });
    vi.useRealTimers();

    const { container } = render(<NeedsAttention />);

    // Long enough for its read to land: still nothing.
    await new Promise((done) => setTimeout(done, 50));
    expect(container.textContent).toBe("");
  });

  it("names a refused clock-in, says why, and says to tell the manager", async () => {
    await refused("document.maker_unknown");

    render(<NeedsAttention />);

    const warning = within(await theWarning());
    expect(
      warning.getByText("Asha: Ingia kazini, saa 07:55 asubuhi"),
    ).toBeDefined();
    expect(
      warning.getByText(
        "Aliyeandika kumbukumbu hii hafanyi kazi katika duka hili.",
      ),
    ).toBeDefined();
    expect(warning.getByText("Haitatumwa tena. Mwambie meneja.")).toBeDefined();
  });

  it.each([
    ["document.type_unknown", "Seva haipokei aina hii ya kumbukumbu."],
    [
      "document.version_unknown",
      "Kumbukumbu hii ni ya toleo jingine la programu.",
    ],
    [
      "document.maker_unknown",
      "Aliyeandika kumbukumbu hii hafanyi kazi katika duka hili.",
    ],
    [
      "id.taken",
      "Seva ina kumbukumbu nyingine yenye namba hii ya utambulisho.",
    ],
  ])("gives %s words of its own, with no try again", async (code, words) => {
    // The office's sentence for id.taken says "Jaribu tena", which a refused record can't do: it is never
    // sent again.
    await refused(code);

    render(<NeedsAttention />);

    const warning = await theWarning();
    expect(within(warning).getByText(words)).toBeDefined();
    expect(warning.textContent).not.toContain("Jaribu tena");
  });

  it("names a reason it has no words for by the server's code", async () => {
    // A newer server's code, before the laptop's update brings its words.
    await refused("document.something_new");

    render(<NeedsAttention />);

    expect(
      within(await theWarning()).getByText(
        "Seva imeikataa. Msimbo: document.something_new",
      ),
    ).toBeDefined();
  });

  it("names a record of another kind by its number", async () => {
    // A later card's record (a sale, say): the counter knows only its number on this laptop.
    const saved = await refused("document.type_unknown", {
      draft: { type: "sale", payload: {} },
    });

    render(<NeedsAttention />);

    expect(
      within(await theWarning()).getByText(
        `Kumbukumbu namba ${saved.device_seq}`,
      ),
    ).toBeDefined();
  });

  it("dates a record refused on another day, so Monday's never reads as today's", async () => {
    // Refused on Monday 10 November, and still on the laptop on Thursday: nothing clears it yet.
    await refused("document.maker_unknown", { at: "2026-11-10T04:55:00Z" });
    const sale = await refused("document.type_unknown", {
      draft: { type: "sale", payload: {} },
      at: "2026-11-10T09:00:00Z",
    });

    render(<NeedsAttention />);

    const warning = within(await theWarning());
    expect(
      warning.getByText("Asha: Ingia kazini, 10/11/2026 saa 07:55 asubuhi"),
    ).toBeDefined();
    expect(
      warning.getByText(`Kumbukumbu namba ${sale.device_seq}, 10/11/2026`),
    ).toBeDefined();
  });

  it("names someone no longer on the laptop's list as an unknown worker", async () => {
    await refused("document.maker_unknown");
    await db().staff.delete(ASHA.id);

    render(<NeedsAttention />);

    expect(
      within(await theWarning()).getByText(
        "Mfanyakazi asiyejulikana: Ingia kazini, saa 07:55 asubuhi",
      ),
    ).toBeDefined();
  });

  it("speaks English, with no Swahili left", async () => {
    await refused("id.taken");
    setLanguage("en");

    const { container } = render(<NeedsAttention />);

    expect(
      await screen.findByRole("alert", { name: "Records the server refused" }),
    ).toBeDefined();
    expect(screen.getByText("Asha: Clock in, at 07:55")).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});
