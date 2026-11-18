// try-the-demo.test.tsx — Jaribu demo: it shows only where the server says the demo is open, one tap
// makes this browser a device and keeps the sellers' PINs and the manager's login (OPS-13), a refusal
// says why, and yesterday's demo copies are deleted from the laptop (OPS-3).
import { fireEvent, screen, waitFor } from "@testing-library/react";
import Dexie from "dexie";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { databaseName } from "@/offline/db";
import { giveCsrfToken } from "@/test/csrf";
import { DAWA_LAPTOP, DAWA_LAPTOP_ANSWER } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import { forgetOtherShops } from "./demo";
import {
  DEMO_LOGINS_KEY,
  DEMO_PINS_KEY,
  demoLogin,
  demoPin,
} from "./demo-pins";
import { savedDevice } from "./this-device";
import { TryTheDemo } from "./try-the-demo";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/devices/v1/me/";
const DEMO = "/api/devices/v1/demo/";
const DEMO_OPEN = "/api/devices/v1/demo/open/";

// Made-up staff ids for the demo's two sellers, and their public PINs.
const ASHA = "019a5e00-0000-7000-8000-0000000000e1";
const BARAKA = "019a5e00-0000-7000-8000-0000000000e2";
const PINS = [
  { staff_id: ASHA, pin: "2580" },
  { staff_id: BARAKA, pin: "1470" },
];
// And the demo's manager, with his public login (OPS-13).
const MENEJA = "019a5e00-0000-7000-8000-0000000000e0";
const LOGINS = [
  { staff_id: MENEJA, login: "meneja@example.com", password: "jaribu-demo" },
];

beforeEach(() => {
  // A CSRF token, as the device's check gives the browser when the app opens.
  giveCsrfToken();
  // Not a device yet, until the tap.
  answer("GET", ME, refusal(401, "not_authenticated"));
});

afterEach(() => {
  window.localStorage.removeItem(DEMO_PINS_KEY);
  window.localStorage.removeItem(DEMO_LOGINS_KEY);
});

const theDemoIsOpen = () =>
  answer("GET", DEMO_OPEN, { status: 200, body: { open: true } });

const tap = async () =>
  fireEvent.click(await screen.findByRole("button", { name: "Jaribu demo" }));

/** A shop's copy on this laptop, with one row in it, closed again as a tab that left it would. */
async function aCopyOf(shopId: string): Promise<void> {
  const db = new Dexie(databaseName(shopId));
  db.version(1).stores({ meta: "key" });
  await db.table("meta").put({ key: "cursor", value: 41 });
  db.close();
}

describe("Jaribu demo", () => {
  it("shows where the server says the demo is open, saying what it does", async () => {
    theDemoIsOpen();
    render(<TryTheDemo />);

    expect(
      await screen.findByRole("button", { name: "Jaribu demo" }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Kifaa hiki kitakuwa kompyuta ya Duka la Mfano, duka la kubuni. Hakuna data halisi.",
      ),
    ).toBeTruthy();
  });

  it("stays hidden where the demo is closed", async () => {
    answer("GET", DEMO_OPEN, { status: 200, body: { open: false } });
    render(<TryTheDemo />);

    await waitFor(() =>
      expect(sent.some((r) => r.url.endsWith(DEMO_OPEN))).toBe(true),
    );
    expect(screen.queryByRole("button", { name: "Jaribu demo" })).toBeNull();
  });

  it("stays hidden on a server with no demo at all", async () => {
    // An older server, or no answer: the fake server answers 404 for a route a test didn't set.
    render(<TryTheDemo />);

    await waitFor(() =>
      expect(sent.some((r) => r.url.endsWith(DEMO_OPEN))).toBe(true),
    );
    expect(screen.queryByRole("button", { name: "Jaribu demo" })).toBeNull();
  });

  it("makes this browser a device with one tap, and keeps the sellers' PINs and the manager's login", async () => {
    theDemoIsOpen();
    answer("POST", DEMO, () => {
      // From now on the browser holds the new device's key, so `me` names it.
      answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
      return Response.json({ pins: PINS, logins: LOGINS }, { status: 201 });
    });
    render(<TryTheDemo />);

    await tap();

    await waitFor(() => expect(savedDevice()).toEqual(DAWA_LAPTOP));
    expect(demoPin(ASHA)).toBe("2580");
    expect(demoPin(BARAKA)).toBe("1470");
    expect(demoLogin(MENEJA)).toEqual({
      login: "meneja@example.com",
      password: "jaribu-demo",
    });
    // The tap is a change, sent with the CSRF token, as a pairing's start is.
    const tapped = sent.find((r) => r.method === "POST");
    expect(tapped?.headers.get("X-CSRFToken")).toBe("token-from-django");
  });

  it("deletes yesterday's demo copies from the laptop once it is a device of today's", async () => {
    await aCopyOf("yesterdays-demo-shop");
    await aCopyOf(DAWA_LAPTOP.shop.id);
    theDemoIsOpen();
    answer("POST", DEMO, () => {
      answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
      return Response.json({ pins: PINS, logins: LOGINS }, { status: 201 });
    });
    render(<TryTheDemo />);

    await tap();

    await waitFor(async () =>
      expect(await Dexie.exists(databaseName("yesterdays-demo-shop"))).toBe(
        false,
      ),
    );
    expect(await Dexie.exists(databaseName(DAWA_LAPTOP.shop.id))).toBe(true);
  });

  it("goes on to the PIN screen when a second tap finds the first one's device", async () => {
    // The first tap made the device, then its check got no answer: the network dropped for a second.
    theDemoIsOpen();
    answer("POST", DEMO, () => {
      answer("GET", ME, () => {
        throw new TypeError("Failed to fetch");
      });
      return Response.json({ pins: PINS, logins: LOGINS }, { status: 201 });
    });
    render(<TryTheDemo />);
    await tap();
    await screen.findByRole("alert");
    expect(savedDevice()).toBeNull();

    // The second tap: the server knows this browser's key now, and the network is back.
    answer("POST", DEMO, refusal(400, "pairing.already_paired"));
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
    await tap();

    await waitFor(() => expect(savedDevice()).toEqual(DAWA_LAPTOP));
    // The PINs the first tap's answer brought are still kept.
    expect(demoPin(ASHA)).toBe("2580");
  });

  it("says so when the browser didn't keep the new device's key", async () => {
    // A browser set to block every site's cookies: the server made the device, yet `me` knows no key. Said
    // with an alert, never a welcome screen that does nothing, and no device saved.
    theDemoIsOpen();
    answer("POST", DEMO, { status: 201, body: { pins: PINS, logins: LOGINS } });
    render(<TryTheDemo />);

    await tap();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(savedDevice()).toBeNull();
    expect(screen.getByRole("button", { name: "Jaribu demo" })).toBeTruthy();
  });

  it("says why a tap was refused", async () => {
    // The demo closed between the look and the tap: a live shop was made in between, say.
    theDemoIsOpen();
    answer("POST", DEMO, refusal(400, "demo.closed"));
    render(<TryTheDemo />);

    await tap();

    expect(await screen.findByText("Demo haipo wazi hapa.")).toBeTruthy();
    expect(savedDevice()).toBeNull();
    expect(demoPin(ASHA)).toBeUndefined();
  });
});

describe("forgetOtherShops", () => {
  it("keeps the app's other databases", async () => {
    // Only shops' copies go: anything else the browser keeps on this address stays.
    const other = new Dexie("not-a-shop");
    other.version(1).stores({ notes: "id" });
    await other.open();
    other.close();
    await aCopyOf("old-shop");

    await forgetOtherShops("new-shop");

    expect(await Dexie.exists("not-a-shop")).toBe(true);
    expect(await Dexie.exists(databaseName("old-shop"))).toBe(false);
  });
});
