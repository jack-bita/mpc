// worker-password.test.tsx — Nenosiri la muda on a worker's page (PPL-12): the password and Sababu sent through
// AUTH-6's route, its 204 and the line after it, with the worker's phone or without; a worker with no phone told to add
// one first; the form's own checks; where each refusal shows; the boxes emptied; nothing of the password kept in the
// store; the demo; offline; and the one form open at a time on the page.
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import type { components } from "@/api/schema";
import { MESSAGES } from "@/i18n/language";
import { DAWA } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { MANAGER, role, STAFF, worker } from "@/test/workers";

import { WorkerScreen } from "./worker-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type Worker = components["schemas"]["Staff"];

const ME = "/api/auth/me/";
const DEMO_OPEN = "/api/devices/v1/demo/open/";
/** A made-up password, as Baba would type one for Asha. */
const TEMPORARY = "Mbuzi-Kijani-42";
const WHY = "Ameanza kazi leo";

afterEach(() => {
  // A test that takes the network away puts it back after (navigator.onLine's spy).
  vi.restoreAllMocks();
});

/** Asha, a seller on Dawa, working, with a phone she logs in with. */
const ASHA = worker({
  full_name: "Asha Mfano",
  display_name: "Asha",
  phone: "+255712345678",
  started_on: "2026-11-03",
  roles: [role("seller", DAWA.id)],
});

/** Where Nenosiri la muda sends Asha's. */
const ROUTE = `${STAFF}${ASHA.id}/temporary-password/`;

/** The manager is logged in, and the server holds the worker. */
function theServerHas(held: Worker) {
  answer("GET", ME, { status: 200, body: MANAGER });
  answer("GET", `${STAFF}${held.id}/`, { status: 200, body: held });
}

/** A server error code's own sentence in Swahili, as the page shows it. */
function sentence(code: string): string {
  let found: unknown = MESSAGES.sw.errors;
  for (const part of code.split("."))
    found = (found as Record<string, unknown>)[part];
  if (typeof found !== "string") throw new Error(`no sentence for ${code}`);
  return found;
}

/** What the app sent to set a password, as the server would read it. */
async function passwordsSent(): Promise<unknown[]> {
  return Promise.all(
    sent
      .filter((request) => request.url.endsWith("/temporary-password/"))
      .map((request) => request.json()),
  );
}

/** The error beside a box: the one its aria-describedby names (field.tsx). */
function errorOf(box: HTMLElement): string {
  const ids = box.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

const button = (name: string) =>
  screen.getByRole("button", { name }) as HTMLButtonElement;
const findButton = (name: string) => screen.findByRole("button", { name });
// exact: the eye beside the box is "Onyesha nenosiri", which holds the word too.
const passwordBox = () =>
  screen.getByLabelText("Nenosiri", { exact: true }) as HTMLInputElement;
const reasonBox = () => screen.getByLabelText("Sababu") as HTMLInputElement;

/** Baba opens the form and fills both boxes. */
async function babaTypes(password: string, reason: string) {
  fireEvent.click(await findButton("Nenosiri la muda"));
  fireEvent.change(passwordBox(), { target: { value: password } });
  fireEvent.change(reasonBox(), { target: { value: reason } });
}

describe("Nenosiri la muda", () => {
  it("sets Asha's password with a reason, empties the boxes, and says she logs in with her phone (Done when #3)", async () => {
    theServerHas(ASHA);
    answer("POST", ROUTE, { status: 204 });
    render(<WorkerScreen id={ASHA.id} />);

    await babaTypes(TEMPORARY, WHY);
    // Hidden as typed, with the eye every password box has (UI-5). A box for a new password: the owner's phone never
    // fills his own saved one in, as it might with "off", which phones ignore on a password box (PPL-12's review).
    expect(passwordBox().type).toBe("password");
    expect(passwordBox().autocomplete).toBe("new-password");
    fireEvent.click(button("Hifadhi"));

    const done = await screen.findByText(
      "Nenosiri la muda la Asha limewekwa. Mwambie nenosiri hili. Ataingia kwa simu yake, 0712 345 678, au kwa barua pepe yake, kisha atachagua nenosiri lake mwenyewe.",
    );
    // The keyboard goes to the line, as after every change on the page.
    expect(done.closest("[tabindex='-1']")).toBe(document.activeElement);
    expect(await passwordsSent()).toEqual([
      { password: TEMPORARY, reason: WHY },
    ]);
    // The form is gone, its boxes with it: the password shows nowhere on the page.
    expect(screen.queryByLabelText("Nenosiri", { exact: true })).toBeNull();
    expect(document.body.innerHTML).not.toContain(TEMPORARY);
  });

  it("for a worker with no phone, says to add one with Badilisha first, and says the email after", async () => {
    // The page never sees an email (StaffSerializer), so the form only warns: one with an email still logs in.
    const noPhone = { ...ASHA, phone: null };
    theServerHas(noPhone);
    answer("POST", ROUTE, { status: 204 });
    render(<WorkerScreen id={ASHA.id} />);

    await babaTypes(TEMPORARY, WHY);
    expect(
      screen.getByText(
        "Asha hana namba ya simu. Kama hana barua pepe pia, ongeza simu yake kwa Badilisha kwanza.",
      ),
    ).toBeTruthy();
    expect(button("Hifadhi").disabled).toBe(false);
    fireEvent.click(button("Hifadhi"));

    await screen.findByText(
      "Nenosiri la muda la Asha limewekwa. Mwambie nenosiri hili. Ataingia kwa barua pepe yake, kisha atachagua nenosiri lake mwenyewe.",
    );
  });

  it("shows password.no_login_name above the boxes when she has neither phone nor email", async () => {
    theServerHas({ ...ASHA, phone: null });
    answer("POST", ROUTE, refusal(400, "password.no_login_name"));
    render(<WorkerScreen id={ASHA.id} />);

    await babaTypes(TEMPORARY, WHY);
    fireEvent.click(button("Hifadhi"));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(sentence("password.no_login_name"));
    // Above the boxes: it comes before the password box on the page.
    expect(
      alert.compareDocumentPosition(passwordBox()) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("asks for a password and a reason before anything is sent", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    await babaTypes("", "   ");
    fireEvent.click(button("Hifadhi"));

    expect(errorOf(passwordBox())).toBe(sentence("blank"));
    expect(errorOf(reasonBox())).toBe(sentence("staff.reason_required"));
    expect(await passwordsSent()).toEqual([]);
  });

  it("shows the password's own checks beside Nenosiri, and the reason's beside Sababu", async () => {
    theServerHas(ASHA);
    answer(
      "POST",
      ROUTE,
      refusal(400, "invalid", {}, { password: ["password_too_common"] }),
    );
    render(<WorkerScreen id={ASHA.id} />);

    await babaTypes("password1", WHY);
    fireEvent.click(button("Hifadhi"));

    await waitFor(() =>
      expect(errorOf(passwordBox())).toBe(sentence("password_too_common")),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it.each([
    "password.own",
    "password.superuser_only",
    "password.more_keys",
    "staff.left",
    "demo.logins_fixed",
  ])("shows who-may's %s above the buttons", async (code) => {
    theServerHas(ASHA);
    answer("POST", ROUTE, refusal(400, code));
    render(<WorkerScreen id={ASHA.id} />);

    await babaTypes(TEMPORARY, WHY);
    fireEvent.click(button("Hifadhi"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      sentence(code),
    );
  });

  it("keeps nothing of the password in the store of server answers once it is sent", async () => {
    // The store is shared by everyone on the phone (UI-4): a password kept there would outlive the form (UI-5).
    const store = makeQueryClient();
    theServerHas(ASHA);
    answer("POST", ROUTE, { status: 204 });
    render(
      <QueryClientProvider client={store}>
        <WorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );

    await babaTypes(TEMPORARY, WHY);
    fireEvent.click(button("Hifadhi"));
    await screen.findByText(/^Nenosiri la muda la Asha limewekwa\./);

    await waitFor(() =>
      expect(
        JSON.stringify(
          store
            .getMutationCache()
            .getAll()
            .map((change) => change.state.variables),
        ),
      ).not.toContain(TEMPORARY),
    );
  });

  it("switches Hifadhi off while there is no network", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    const open = await findButton("Nenosiri la muda");
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    fireEvent.click(open);

    expect(button("Hifadhi").disabled).toBe(true);
  });

  it("gives the keyboard back on Ghairi, and keeps one form open on the page at a time", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Nenosiri la muda"));
    for (const name of ["Simamisha", "Ongeza kazi", "Weka PIN"])
      expect(screen.queryByRole("button", { name })).toBeNull();
    fireEvent.click(button("Ghairi"));

    await waitFor(() =>
      expect(document.activeElement).toBe(button("Nenosiri la muda")),
    );
  });

  it("offers it as Weka PIN is offered: not to one who left", async () => {
    const left = { ...ASHA, status: "left" as const, left_on: "2026-11-10" };
    theServerHas(left);
    render(<WorkerScreen id={left.id} />);

    await findButton("Mwajiri tena");
    expect(
      screen.queryByRole("button", { name: "Nenosiri la muda" }),
    ).toBeNull();
  });
});

describe("on the demo", () => {
  it("keeps both buttons off, with one line saying why (Done when #5)", async () => {
    theServerHas(ASHA);
    answer("GET", DEMO_OPEN, { status: 200, body: { open: true } });
    render(<WorkerScreen id={ASHA.id} />);

    await waitFor(() => expect(button("Nenosiri la muda").disabled).toBe(true));
    expect(button("Weka PIN").disabled).toBe(true);
    expect(screen.getAllByText(sentence("demo.logins_fixed"))).toHaveLength(1);
  });
});
