// demo-pins.test.ts — what one tap on Jaribu demo keeps on the laptop (OPS-3, OPS-13): the sellers' PINs
// and the manager's login, by staff id, read back by the PIN screen's tiles and the login page.
//
// Fake people and the demo's public PIN and password only: the repo is public.
import { afterEach, describe, expect, it } from "vitest";

import {
  DEMO_LOGINS_KEY,
  DEMO_PINS_KEY,
  demoLogin,
  demoPin,
  keepsDemoLogins,
  saveLogins,
  savePins,
} from "./demo-pins";

const ASHA = "019a5e00-0000-7000-8000-0000000000c2";
const MENEJA = "019a5e00-0000-7000-8000-0000000000c1";
const MENEJA_LOGIN = {
  staff_id: MENEJA,
  login: "meneja@example.com",
  password: "jaribu-demo",
};

afterEach(() => {
  window.localStorage.removeItem(DEMO_PINS_KEY);
  window.localStorage.removeItem(DEMO_LOGINS_KEY);
});

describe("the demo's kept PINs", () => {
  it("gives back the PIN kept for a seller, and none for anyone else", () => {
    savePins([{ staff_id: ASHA, pin: "2580" }]);

    expect(demoPin(ASHA)).toBe("2580");
    expect(demoPin(MENEJA)).toBeUndefined();
  });

  it("reads a kept copy it can't trust as no PIN", () => {
    // Moved here from try-the-demo.test.tsx, beside the logins' own (OPS-13).
    window.localStorage.setItem(DEMO_PINS_KEY, "not json");
    expect(demoPin(ASHA)).toBeUndefined();
    window.localStorage.setItem(DEMO_PINS_KEY, JSON.stringify([ASHA]));
    expect(demoPin(ASHA)).toBeUndefined();
    window.localStorage.setItem(
      DEMO_PINS_KEY,
      JSON.stringify({ [ASHA]: 2580 }),
    );
    expect(demoPin(ASHA)).toBeUndefined();
  });
});

describe("the demo's kept logins", () => {
  it("gives back the login kept for the manager, and none for anyone else", () => {
    saveLogins([MENEJA_LOGIN]);

    expect(demoLogin(MENEJA)).toEqual({
      login: "meneja@example.com",
      password: "jaribu-demo",
    });
    // A seller logs in with her PIN: the tap hands over no login of hers.
    expect(demoLogin(ASHA)).toBeUndefined();
  });

  it("keeps none on a laptop that never tried the demo", () => {
    // A real shop's laptop: its tiles stay as PPL-4 made them, a tile only for someone with a PIN.
    expect(demoLogin(MENEJA)).toBeUndefined();
    expect(keepsDemoLogins()).toBe(false);
  });

  it("says whether this laptop keeps any demo login", () => {
    // The PIN screen asks it before the first sync, when there are no tiles to look at yet.
    saveLogins([MENEJA_LOGIN]);
    expect(keepsDemoLogins()).toBe(true);
    // A tap whose answer had no login: none kept.
    saveLogins([]);
    expect(keepsDemoLogins()).toBe(false);
  });

  it("puts a new tap's logins in place of yesterday's", () => {
    // Yesterday's Meneja had another id: the daily reset made everyone again.
    saveLogins([{ ...MENEJA_LOGIN, staff_id: ASHA }]);
    saveLogins([MENEJA_LOGIN]);

    expect(demoLogin(ASHA)).toBeUndefined();
    expect(demoLogin(MENEJA)).toBeDefined();
  });

  it("keeps the logins apart from the PINs", () => {
    // Each under its own key: a version of the app that knows only the PINs still reads them as before.
    savePins([{ staff_id: ASHA, pin: "2580" }]);
    saveLogins([MENEJA_LOGIN]);

    expect(demoPin(ASHA)).toBe("2580");
    expect(demoLogin(MENEJA)).toBeDefined();
  });

  it("answers no built-in name of JavaScript's objects as a kept login or PIN", () => {
    // Any object answers "constructor" or "__proto__" with one of its own: a link to /login/?as=constructor
    // made a real shop's login page say it held the demo's public login (OPS-13's review).
    expect(demoLogin("constructor")).toBeUndefined();
    expect(demoLogin("__proto__")).toBeUndefined();
    expect(demoLogin("toString")).toBeUndefined();
    expect(demoPin("constructor")).toBeUndefined();

    saveLogins([MENEJA_LOGIN]);
    savePins([{ staff_id: ASHA, pin: "2580" }]);
    expect(demoLogin("constructor")).toBeUndefined();
    expect(demoPin("hasOwnProperty")).toBeUndefined();
  });

  it("reads anything it can't make sense of as none", () => {
    // Written by hand, or by another version of the app: a tile with no login is the worst that follows.
    window.localStorage.setItem(
      DEMO_LOGINS_KEY,
      JSON.stringify({ [MENEJA]: { login: "meneja@example.com" } }),
    );
    expect(demoLogin(MENEJA)).toBeUndefined();

    window.localStorage.setItem(DEMO_LOGINS_KEY, "not json");
    expect(demoLogin(MENEJA)).toBeUndefined();
  });
});
