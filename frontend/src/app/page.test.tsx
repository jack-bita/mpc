// page.test.tsx — the home page: on a new device, the Karibu welcome, the app's version and the way to
// register it (UI-3); on a registered one, the PIN login, and who is logged in (UI-4).
//
// The first Vitest test: it proves the test setup works end to end (TypeScript and JSX,
// the word books, jsdom, Testing Library). Later cards (REPO-4, OPS-1) check for
// this same word in the real browser. The English switch is checked in src/i18n/language.test.tsx.
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { saveDevice } from "@/features/devices/this-device";
import {
  DAWA,
  DAWA_LAPTOP,
  DAWA_LAPTOP_ANSWER,
  VYAKULA,
  whoIsHere,
} from "@/test/devices";
import { answer, refusal } from "@/test/fake-server";
import { render } from "@/test/render";

import HomePage from "./page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const STAFF = "/api/devices/v1/staff/";
const PIN_LOGIN = "/api/auth/pin-login/";

type WhoIsHere = components["schemas"]["WhoIsHere"];

/** What `me` answers once Neema has logged in by PIN at the Dawa laptop, holding `keys` on each side. */
function neemaAtTheLaptop(keys: Parameters<typeof whoIsHere>[0]): WhoIsHere {
  return {
    ...whoIsHere(keys),
    device: DAWA_LAPTOP_ANSWER.device,
    home_side: DAWA_LAPTOP_ANSWER.home_side,
    idle_minutes: 15,
  };
}

/**
 * The Dawa laptop, registered, with nobody logged in yet: `me` says so until a PIN login works, and
 * then answers `after`. Neema is the shop's one tile.
 */
function theLaptop(after: WhoIsHere) {
  saveDevice(DAWA_LAPTOP);
  let loggedIn = false;
  const nobody = refusal(403, "not_authenticated");
  answer("GET", ME, () =>
    loggedIn
      ? Response.json(after)
      : Response.json(nobody.body, { status: nobody.status }),
  );
  answer("GET", STAFF, {
    status: 200,
    body: [
      {
        id: after.staff.id,
        full_name: after.user.full_name,
        display_name: after.staff.display_name,
      },
    ],
  });
  answer("POST", PIN_LOGIN, () => {
    loggedIn = true;
    return new Response(null, { status: 204 });
  });
}

/** Neema taps her tile and types her PIN. */
async function neemaLogsIn() {
  fireEvent.click(
    await screen.findByRole("button", { name: "Neema Mfano Neema" }),
  );
  for (const digit of "4829")
    fireEvent.click(screen.getByRole("button", { name: digit }));
}

const bar = () => within(screen.getByRole("banner"));

describe("HomePage", () => {
  it("says Karibu", () => {
    render(<HomePage />);

    // Find it the way a user, or a screen reader, finds it: the page's main heading, by
    // its words. The word itself is checked, not the message key, so a wrong translation
    // in messages/sw.json fails here too.
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toBe("Karibu");
  });

  it("shows the version this device runs", () => {
    render(<HomePage />);

    // Tests get no NEXT_PUBLIC_APP_VERSION, like any build outside the image: "dev" (src/lib/version.ts).
    expect(screen.getByText("Toleo dev")).toBeTruthy();
  });

  it("shows a new device the way to register it", () => {
    render(<HomePage />);

    const link = screen.getByRole("link", { name: "Sajili kifaa hiki" });
    // The end slash comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(link.getAttribute("href")).toMatch(/^\/register-device\/?$/);
  });

  it("asks who you are on a registered laptop, under the shop and the laptop's side", async () => {
    theLaptop(neemaAtTheLaptop([{ side: DAWA, permissions: ["sale.make"] }]));

    render(<HomePage />);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeTruthy();
    expect(bar().getByText("MPC · Dawa")).toBeTruthy();
    expect(screen.getByText("Toleo dev")).toBeTruthy();
    expect(
      screen.queryByRole("link", { name: "Sajili kifaa hiki" }),
    ).toBeNull();
  });

  it("logs a person in by PIN, and names them in the bar", async () => {
    theLaptop(neemaAtTheLaptop([{ side: DAWA, permissions: ["sale.make"] }]));
    render(<HomePage />);

    await neemaLogsIn();

    expect(
      await screen.findByRole("heading", { level: 1, name: "Karibu, Neema" }),
    ).toBeTruthy();
    expect(bar().getByText("Neema")).toBeTruthy();
    expect(bar().getByText("MPC · Dawa")).toBeTruthy();
  });

  it("names the side the person works on, not the laptop's", async () => {
    // Neema works on Vyakula, and logs in at the Dawa laptop (UI-3's note on UI-4).
    theLaptop(
      neemaAtTheLaptop([{ side: VYAKULA, permissions: ["sale.make"] }]),
    );
    render(<HomePage />);

    await neemaLogsIn();

    await screen.findByRole("heading", { level: 1, name: "Karibu, Neema" });
    expect(bar().getByText("MPC · Vyakula")).toBeTruthy();
  });

  it("asks for a PIN again when the server ends the session, saying why", async () => {
    // Neema was suspended while logged in: `me` refuses her session (AUTH-4), until the laptop ends it.
    saveDevice(DAWA_LAPTOP);
    let ended = false;
    answer("GET", ME, () => {
      const why = refusal(403, ended ? "not_authenticated" : "staff.suspended");
      return Response.json(why.body, { status: why.status });
    });
    answer("POST", "/api/auth/logout/", () => {
      ended = true;
      return new Response(null, { status: 204 });
    });
    answer("GET", STAFF, { status: 200, body: [] });

    render(<HomePage />);

    expect(
      await screen.findByText("Umesimamishwa. Ongea na meneja au mmiliki."),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeTruthy();
    expect(bar().queryByText("Neema")).toBeNull();
  });
});
