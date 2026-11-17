// send-now.test.tsx — Tuma sasa on the Mahudhurio screen (SYNC-11, SYNC-9, 03 §6.5): how many records wait
// on this laptop, read live; the button asks the sync to send them now, without calling anything itself;
// and with no network it says they will go once it is back, rather than leave a seller waiting for nothing.
import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { setLanguage } from "@/i18n/language";
import { saveDocument } from "@/offline/outbox";
import { listenForAsks, type SyncAskKind } from "@/offline/sync/asks";
import { LAST_DEVICE_SEQ } from "@/offline/sync/meta";
import { shopDatabase } from "@/offline/this-shop";
import { DAWA_LAPTOP } from "@/test/devices";
import { swahiliIn } from "@/test/language";
import { theLaptopKnows } from "@/test/laptop";
import { render } from "@/test/render";
import { ASHA } from "@/test/shop-lists";

import { SendNow } from "./send-now";

const db = () => shopDatabase(DAWA_LAPTOP.shop.id);
const sendNow = () => screen.queryByRole("button", { name: "Tuma sasa" });

/** A clock-in saved on the laptop, waiting for the push. */
function aTapWaits() {
  return saveDocument(db(), {
    type: "clock",
    schema_version: 1,
    created_by: ASHA.id,
    payload: { kind: "in", last_server_time: "2026-11-13T04:00:00Z" },
  });
}

/** What the counter asked the sync, as the sync's moments hear it (triggers.tsx). */
let asked: SyncAskKind[] = [];
let stopListening: () => void = () => {};

beforeEach(async () => {
  saveDevice(DAWA_LAPTOP);
  await theLaptopKnows(ASHA);
  await db().meta.put({ key: LAST_DEVICE_SEQ, value: 57 });
  asked = [];
  stopListening = listenForAsks((kind) => asked.push(kind));
});
afterEach(() => {
  stopListening();
  vi.restoreAllMocks();
});

/** The browser says there is no network at all (navigator.onLine false), and tells the page so. */
function theNetworkGoes() {
  vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
  act(() => {
    window.dispatchEvent(new Event("offline"));
  });
}

describe("Tuma sasa", () => {
  it("says how many records wait, and asks the sync to send them now", async () => {
    await aTapWaits();
    await aTapWaits();
    render(<SendNow />);

    expect(
      await screen.findByText("Kumbukumbu 2 zinasubiri kutumwa."),
    ).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Tuma sasa" }));

    expect(asked.filter((kind) => kind === "send_now")).toHaveLength(1);
  });

  it("speaks of one record in the singular", async () => {
    await aTapWaits();

    render(<SendNow />);

    expect(
      await screen.findByText("Kumbukumbu 1 inasubiri kutumwa."),
    ).toBeDefined();
  });

  it("says all are sent once the push took them, and offers no button", async () => {
    const tap = await aTapWaits();
    render(<SendNow />);
    await screen.findByText("Kumbukumbu 1 inasubiri kutumwa.");

    // What an accepted push does to its row: it leaves the outbox (push.ts).
    await act(() => db().outbox.delete(tap.id));

    expect(await screen.findByText("Kumbukumbu zote zimetumwa.")).toBeDefined();
    expect(sendNow()).toBeNull();
  });

  it("doesn't count a record the server set aside: it reached the server already", async () => {
    // Refused as invalid: the needs-attention list shows it, and a resend would get the same no.
    const tap = await aTapWaits();
    await db().outbox.update(tap.id, {
      status: "needs_attention",
      last_error: "document.maker_unknown",
    });

    render(<SendNow />);

    expect(await screen.findByText("Kumbukumbu zote zimetumwa.")).toBeDefined();
  });

  it("with no network, says they go once it is back, and the button asks nothing", async () => {
    // A sync can't run with no network (triggers.tsx): a press would leave her waiting for nothing.
    await aTapWaits();
    render(<SendNow />);
    await screen.findByText("Kumbukumbu 1 inasubiri kutumwa.");

    theNetworkGoes();

    expect(
      await screen.findByText("Hakuna mtandao: zitatumwa mtandao ukirudi."),
    ).toBeDefined();
    const button = screen.getByRole("button", { name: "Tuma sasa" });
    fireEvent.click(button);
    expect(asked).not.toContain("send_now");
  });

  it("wakes again when the network is back", async () => {
    await aTapWaits();
    render(<SendNow />);
    await screen.findByText("Kumbukumbu 1 inasubiri kutumwa.");
    theNetworkGoes();
    await screen.findByText("Hakuna mtandao: zitatumwa mtandao ukirudi.");

    vi.restoreAllMocks();
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    fireEvent.click(screen.getByRole("button", { name: "Tuma sasa" }));

    expect(asked).toContain("send_now");
    expect(
      screen.queryByText("Hakuna mtandao: zitatumwa mtandao ukirudi."),
    ).toBeNull();
  });

  it("asks the server nothing itself: the sync sends", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    await aTapWaits();
    render(<SendNow />);

    fireEvent.click(await screen.findByRole("button", { name: "Tuma sasa" }));

    expect(fetch).not.toHaveBeenCalled();
  });

  it("speaks English, with no Swahili left", async () => {
    await aTapWaits();
    await aTapWaits();
    setLanguage("en");

    const { container } = render(<SendNow />);

    expect(
      await screen.findByText("2 records waiting to be sent."),
    ).toBeDefined();
    expect(screen.getByRole("button", { name: "Send now" })).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});
