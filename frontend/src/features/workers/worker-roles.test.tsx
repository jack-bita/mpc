// worker-roles.test.tsx — a worker's roles and extra keys on their page, and the buttons that change them (PPL-8).
// Ongeza kazi: a role on a side and a key on every side, each shown at once; the same id for a try of the same choices
// and a new one for a change; only what the person may give, never Mmiliki; a side narrowing the lists; what the form
// says itself; each refusal of the server's; who sees the button; offline; Ghairi. Ondoa: a role and a key taken away
// with a reason; an end sent again after a lost answer taken as done; no reason, no send; each refusal; never beside
// Mmiliki.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { MESSAGES } from "@/i18n/language";
import { DAWA, VYAKULA } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import {
  BABA,
  NEEMA_ON_DAWA,
  role,
  ROLES_ROUTE,
  rolesPage,
  SELLER_ROLE,
  SHOP_ROLES,
  STAFF,
  worker,
} from "@/test/workers";

import { WorkerScreen } from "./worker-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

afterEach(() => {
  // A test that takes the network away puts it back after (navigator.onLine's spy).
  vi.restoreAllMocks();
});

type Worker = components["schemas"]["Staff"];
type WhoIsHere = components["schemas"]["WhoIsHere"];

const ME = "/api/auth/me/";

/** Juma, working, with no role and no key yet. */
const JUMA = worker();

/** The server's sentence for a code, from the Swahili book, as the page shows it. */
function sentence(code: string): string {
  let found: unknown = MESSAGES.sw.errors;
  for (const part of code.split("."))
    found = (found as Record<string, unknown>)[part];
  if (typeof found !== "string") throw new Error(`no sentence for ${code}`);
  return found;
}

/** `me` is the person giving, and the server holds `start`; `now` changes what it answers from then on. */
function theServerHas(start: Worker, me: WhoIsHere = BABA) {
  let held = start;
  answer("GET", ME, { status: 200, body: me });
  answer("GET", `${STAFF}${start.id}/`, () => Response.json(held));
  answer("GET", ROLES_ROUTE, { status: 200, body: rolesPage(SHOP_ROLES) });
  return {
    now(changed: Worker) {
      held = changed;
    },
  };
}

/** The give routes answer as the server would: Juma with what was given, kept for the reads after. */
function givesAreSaved(server: ReturnType<typeof theServerHas>) {
  answer("POST", `${STAFF}${JUMA.id}/give-role/`, async (request) => {
    const body = (await request.json()) as {
      id: string;
      role: string;
      side: string | null;
    };
    const given = SHOP_ROLES.find((each) => each.id === body.role);
    const changed = {
      ...JUMA,
      roles: [
        role(given?.template ?? "", body.side, {
          id: body.id,
          role: body.role,
        }),
      ],
    };
    server.now(changed);
    return Response.json(changed);
  });
  answer("POST", `${STAFF}${JUMA.id}/give-key/`, async (request) => {
    const body = (await request.json()) as {
      id: string;
      permission: string;
      side: string | null;
    };
    const changed = {
      ...JUMA,
      keys: [{ id: body.id, permission: body.permission, side: body.side }],
    };
    server.now(changed);
    return Response.json(changed);
  });
}

/** What the app sent to the give routes, as the server would read it. */
async function gives(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map((request) => request.json() as Promise<Record<string, unknown>>),
  );
}

const button = (name: string) => screen.getByRole("button", { name });
const radio = (name: string) => screen.getByRole("radio", { name });
const radios = (group: string) =>
  within(screen.getByRole("radiogroup", { name: group }))
    .getAllByRole("radio")
    .map(
      (each) =>
        each.getAttribute("aria-label") ??
        each.closest("label")?.textContent ??
        "",
    );

/** Picks a row of a Choice, as a tap on its words does. */
function pick(name: string) {
  fireEvent.click(radio(name));
}

/** The lines under one of the card's headings (worker-page.test.tsx). */
function linesUnder(heading: string): string[] {
  const section = screen.getByRole("region", { name: heading });
  return (
    within(section)
      .queryAllByRole("listitem")
      // The words alone: the item's first part, before its Ondoa (worker-roles.tsx).
      .map((item) => item.firstElementChild?.textContent ?? "")
  );
}

/** Opens Ongeza kazi once the page has drawn. */
async function openTheGive() {
  fireEvent.click(await screen.findByRole("button", { name: "Ongeza kazi" }));
  await screen.findByRole("heading", { name: "Ongeza kazi kwa Juma" });
}

/** Picks a role, waiting for the shop's roles, asked as the form opened. */
async function pickRole(name: string) {
  pick("Cheo");
  fireEvent.click(await screen.findByRole("radio", { name }));
}

describe("Ongeza kazi", () => {
  it("gives Juma the Seller role on Dawa, shown at once (the card's second Done when)", async () => {
    const server = theServerHas(JUMA);
    givesAreSaved(server);

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    // The form's title takes the keyboard, where the button was.
    expect(document.activeElement?.textContent).toBe("Ongeza kazi kwa Juma");
    await pickRole("Muuzaji");
    pick("Dawa");
    fireEvent.click(button("Hifadhi"));

    const line =
      "Juma amepewa Muuzaji (Dawa). Kompyuta za duka zitajua baada ya kusawazisha.";
    await waitFor(() => expect(document.activeElement?.textContent).toBe(line));
    const [sentOnce] = await gives();
    expect(sentOnce).toEqual({
      id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      role: SELLER_ROLE.id,
      side: DAWA.id,
    });
    expect(linesUnder("Cheo")).toEqual(["Muuzaji (Dawa)"]);
    // The form closed; Ongeza kazi is back for the next.
    expect(button("Ongeza kazi")).toBeTruthy();
  });

  it("gives one extra key on every side, shown at once", async () => {
    const server = theServerHas(JUMA);
    givesAreSaved(server);

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    pick("Ruhusa moja ya ziada");
    // Under its group's heading.
    expect(
      within(screen.getByRole("radiogroup", { name: "Mzigo" })).getByRole(
        "radio",
        { name: "Kuhesabu mzigo" },
      ),
    ).toBeTruthy();
    pick("Kuhesabu mzigo");
    pick("Pande zote");
    fireEvent.click(button("Hifadhi"));

    await screen.findByText(
      "Juma amepewa Kuhesabu mzigo (Pande zote). Kompyuta za duka zitajua baada ya kusawazisha.",
    );
    const [sentOnce] = await gives();
    expect(sentOnce).toEqual({
      id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      permission: "stock.count",
      side: null,
    });
    expect(linesUnder("Ruhusa za ziada")).toEqual([
      "Kuhesabu mzigo (Pande zote)",
    ]);
  });

  it("sends the same id for a try of the same choices, and a new one once a choice changed", async () => {
    // The network loses each answer: the manager taps Hifadhi again, then picks another side.
    theServerHas(JUMA);
    answer("POST", `${STAFF}${JUMA.id}/give-role/`, () => {
      throw new TypeError("Failed to fetch");
    });

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    await pickRole("Muuzaji");
    pick("Dawa");
    fireEvent.click(button("Hifadhi"));
    await screen.findByRole("alert");
    fireEvent.click(button("Hifadhi"));
    await waitFor(() =>
      expect(sent.filter((request) => request.method === "POST")).toHaveLength(
        2,
      ),
    );
    await waitFor(() =>
      expect(button("Hifadhi").hasAttribute("disabled")).toBe(false),
    );
    pick("Vyakula");
    fireEvent.click(button("Hifadhi"));
    await waitFor(() =>
      expect(sent.filter((request) => request.method === "POST")).toHaveLength(
        3,
      ),
    );

    const [first, again, changed] = await gives();
    // A give whose answer was lost, sent again, finds the row the first made (ADR-0007).
    expect(again?.id).toBe(first?.id);
    // Another side is another give: an old id with new choices would be id.taken (PPL-7's review).
    expect(changed?.id).not.toBe(first?.id);
    expect(changed?.side).toBe(VYAKULA.id);
  });

  it("asks the shop's roles only once the form opens", async () => {
    theServerHas(JUMA);

    render(<WorkerScreen id={JUMA.id} />);
    await screen.findByRole("button", { name: "Ongeza kazi" });
    expect(sent.some((request) => request.url.includes(ROLES_ROUTE))).toBe(
      false,
    );
    await openTheGive();
    await pickRole("Muuzaji");
    expect(
      sent.filter((request) => request.url.includes(ROLES_ROUTE)),
    ).toHaveLength(1);
  });

  it("offers the owner every role but Mmiliki, as the templates come (the card's third Done when)", async () => {
    theServerHas(JUMA);

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    await pickRole("Muuzaji");

    // The server sends them newest first; the form sorts them, and never offers the Owner role, even to the owner.
    expect(radios("Cheo gani?")).toEqual([
      "Meneja",
      "Muuzaji",
      "Keshia",
      "Mbeba mizigo",
    ]);
    expect(screen.queryByRole("radio", { name: "Mmiliki" })).toBeNull();
  });

  it("offers Neema only what she may give, and only where (the card's third Done when)", async () => {
    // A Dawa seller trusted with staff.manage on Dawa alone.
    theServerHas(JUMA, NEEMA_ON_DAWA);

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    await pickRole("Muuzaji");

    // Roles whose every code she holds on a side: not the Manager's.
    expect(radios("Cheo gani?")).toEqual(["Muuzaji", "Keshia", "Mbeba mizigo"]);
    // The Seller only where she holds its codes: Dawa, not every side, which would open Vyakula too.
    expect(radios("Upande")).toEqual(["Dawa"]);
    // Her keys: the Seller's and staff.manage, none of the money's or the shop's.
    pick("Ruhusa moja ya ziada");
    expect(screen.queryByRole("radio", { name: "Kulipa matumizi" })).toBeNull();
    expect(
      screen.queryByRole("radiogroup", { name: "Duka lenyewe" }),
    ).toBeNull();
    expect(radio("Kuhesabu mzigo")).toBeTruthy();
  });

  it("narrows the roles and keys to the side picked", async () => {
    theServerHas(JUMA, NEEMA_ON_DAWA);

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    // Vyakula first: Neema holds nothing there, so there is nothing to give her worker there.
    pick("Vyakula");
    pick("Cheo");
    expect(
      await screen.findByText("Hakuna cheo unachoweza kumpa."),
    ).toBeTruthy();
    pick("Ruhusa moja ya ziada");
    expect(screen.getByText("Hakuna ruhusa unayoweza kumpa.")).toBeTruthy();
    // Dawa: the lists come back.
    pick("Dawa");
    expect(radio("Kuhesabu mzigo")).toBeTruthy();
  });

  it("leaves out the side where the worker already holds the pick", async () => {
    theServerHas({
      ...JUMA,
      roles: [role("seller", DAWA.id, { role: SELLER_ROLE.id })],
    });

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    await pickRole("Muuzaji");

    expect(radios("Upande")).toEqual(["Pande zote", "Vyakula"]);
  });

  it("says at once what is missing, and sends nothing", async () => {
    theServerHas(JUMA);

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    fireEvent.click(button("Hifadhi"));
    // Anapewa nini? and Upande, each beside its question.
    expect(screen.getAllByText("Jaza sehemu hii.")).toHaveLength(2);
    pick("Cheo");
    await screen.findByRole("radio", { name: "Muuzaji" });
    fireEvent.click(button("Hifadhi"));
    // Cheo gani? and Upande.
    expect(screen.getAllByText("Jaza sehemu hii.")).toHaveLength(2);
    expect(sent.filter((request) => request.method === "POST")).toHaveLength(0);
  });

  it.each([
    ["role.already_given", "give-role"],
    ["role.superuser_only", "give-role"],
    ["staff.temporary_password_open", "give-role"],
    ["demo.people_fixed", "give-role"],
    ["permission_denied", "give-role"],
    ["permission.already_given", "give-key"],
  ])("shows %s above the buttons, and keeps the form", async (code, route) => {
    theServerHas(JUMA);
    answer(
      "POST",
      `${STAFF}${JUMA.id}/${route}/`,
      refusal(code === "permission_denied" ? 403 : 400, code),
    );

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    if (route === "give-role") await pickRole("Muuzaji");
    else {
      pick("Ruhusa moja ya ziada");
      pick("Kuhesabu mzigo");
    }
    pick("Dawa");
    fireEvent.click(button("Hifadhi"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      sentence(code),
    );
    expect(button("Hifadhi")).toBeTruthy();
  });

  it("shows id.taken above the buttons, though the server names the id's field", async () => {
    // The give has no box for its id: the field's code is about the whole give.
    theServerHas(JUMA);
    answer(
      "POST",
      `${STAFF}${JUMA.id}/give-role/`,
      refusal(400, "invalid", {}, { id: ["id.taken"] }),
    );

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    await pickRole("Muuzaji");
    pick("Dawa");
    fireEvent.click(button("Hifadhi"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      sentence("id.taken"),
    );
  });

  it("closes the form on staff.left, says so, and reads the worker again", async () => {
    // Another manager marked Juma left since the page read him.
    const server = theServerHas(JUMA);
    answer("POST", `${STAFF}${JUMA.id}/give-role/`, () => {
      server.now({ ...JUMA, status: "left", left_on: "2026-11-18" });
      return Response.json(
        { code: "staff.left", message: "", fields: {}, params: {} },
        { status: 400 },
      );
    });

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    await pickRole("Muuzaji");
    pick("Dawa");
    fireEvent.click(button("Hifadhi"));

    await waitFor(() =>
      expect(document.activeElement?.textContent).toBe(sentence("staff.left")),
    );
    // Read again: a worker who left keeps their roles as history, with no button.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Ongeza kazi" })).toBeNull(),
    );
  });

  it("switches Hifadhi off offline", async () => {
    theServerHas(JUMA);

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    // The network gone as the form draws again (useOnline reads it as it draws): no "offline" event, which would leave
    // TanStack's own watcher offline for the tests after (PPL-6's lesson).
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    pick("Cheo");

    await waitFor(() =>
      expect(button("Hifadhi").hasAttribute("disabled")).toBe(true),
    );
  });

  it("gives the keyboard back to Ongeza kazi on Ghairi, and reads the worker again", async () => {
    theServerHas(JUMA);

    render(<WorkerScreen id={JUMA.id} />);
    await openTheGive();
    const readsBefore = sent.filter((request) =>
      request.url.endsWith(`${JUMA.id}/`),
    ).length;
    fireEvent.click(button("Ghairi"));

    await waitFor(() =>
      expect(document.activeElement).toBe(button("Ongeza kazi")),
    );
    await waitFor(() =>
      expect(
        sent.filter((request) => request.url.endsWith(`${JUMA.id}/`)).length,
      ).toBeGreaterThan(readsBefore),
    );
  });
});

/** Juma as a seller on Dawa, with the stock count on Vyakula: something to take away. */
const SELLER_ON_DAWA = role("seller", DAWA.id, { role: SELLER_ROLE.id });
const COUNT_ON_VYAKULA = {
  id: "019a8303-0000-7000-8000-000000000101",
  permission: "stock.count",
  side: VYAKULA.id,
};
const JUMA_WITH_BOTH = {
  ...JUMA,
  roles: [SELLER_ON_DAWA],
  keys: [COUNT_ON_VYAKULA],
};

/** What the app sent to the end routes, as the server would read it. */
async function ends(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map((request) => request.json() as Promise<Record<string, unknown>>),
  );
}

describe("Ondoa", () => {
  it("takes Juma's role away with a reason, and it is gone from the page (the card's fourth Done when)", async () => {
    const server = theServerHas(JUMA_WITH_BOTH);
    answer("POST", `${STAFF}${JUMA.id}/end-role/`, () => {
      const changed = { ...JUMA_WITH_BOTH, roles: [] };
      server.now(changed);
      return Response.json(changed);
    });

    render(<WorkerScreen id={JUMA.id} />);
    // Its name says what goes, as every row's button reads Ondoa.
    fireEvent.click(
      await screen.findByRole("button", { name: "Ondoa Muuzaji (Dawa)" }),
    );
    expect(
      screen.getByRole("heading", { name: "Ondoa Muuzaji (Dawa) kwa Juma" }),
    ).toBeTruthy();
    // The keyboard starts in Sababu.
    expect(document.activeElement).toBe(screen.getByLabelText("Sababu"));
    fireEvent.change(screen.getByLabelText("Sababu"), {
      target: { value: "  Amehamia Vyakula  " },
    });
    fireEvent.click(button("Hifadhi"));

    const line =
      "Umemwondolea Juma Muuzaji (Dawa). Kompyuta za duka zitajua baada ya kusawazisha.";
    await waitFor(() => expect(document.activeElement?.textContent).toBe(line));
    expect(await ends()).toEqual([
      { role_given: SELLER_ON_DAWA.id, reason: "Amehamia Vyakula" },
    ]);
    expect(linesUnder("Cheo")).toEqual([]);
    expect(screen.getByText("Hana cheo bado")).toBeTruthy();
  });

  it("takes an extra key away with a reason", async () => {
    const server = theServerHas(JUMA_WITH_BOTH);
    answer("POST", `${STAFF}${JUMA.id}/end-key/`, () => {
      const changed = { ...JUMA_WITH_BOTH, keys: [] };
      server.now(changed);
      return Response.json(changed);
    });

    render(<WorkerScreen id={JUMA.id} />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Ondoa Kuhesabu mzigo (Vyakula)",
      }),
    );
    fireEvent.change(screen.getByLabelText("Sababu"), {
      target: { value: "Hesabu imeisha" },
    });
    fireEvent.click(button("Hifadhi"));

    await screen.findByText(
      "Umemwondolea Juma Kuhesabu mzigo (Vyakula). Kompyuta za duka zitajua baada ya kusawazisha.",
    );
    expect(await ends()).toEqual([
      { key: COUNT_ON_VYAKULA.id, reason: "Hesabu imeisha" },
    ]);
    expect(screen.getByText("Hana ruhusa za ziada")).toBeTruthy();
  });

  it.each([
    [
      "role.already_ended",
      "end-role",
      "Ondoa Muuzaji (Dawa)",
      "Muuzaji (Dawa)",
    ],
    [
      "permission.already_ended",
      "end-key",
      "Ondoa Kuhesabu mzigo (Vyakula)",
      "Kuhesabu mzigo (Vyakula)",
    ],
  ])(
    "takes %s as done: it reads Juma again and says the done line (the card's fourth Done when)",
    async (code, route, buttonName, what) => {
      // The first end reached the server, its answer lost; the one sent again hears that it is ended already.
      const server = theServerHas(JUMA_WITH_BOTH);
      answer("POST", `${STAFF}${JUMA.id}/${route}/`, () => {
        server.now(
          route === "end-role"
            ? { ...JUMA_WITH_BOTH, roles: [] }
            : { ...JUMA_WITH_BOTH, keys: [] },
        );
        return Response.json(
          { code, message: code, fields: {}, params: {} },
          { status: 400 },
        );
      });

      render(<WorkerScreen id={JUMA.id} />);
      fireEvent.click(await screen.findByRole("button", { name: buttonName }));
      fireEvent.change(screen.getByLabelText("Sababu"), {
        target: { value: "Amehamia Vyakula" },
      });
      fireEvent.click(button("Hifadhi"));

      await screen.findByText(
        `Umemwondolea Juma ${what}. Kompyuta za duka zitajua baada ya kusawazisha.`,
      );
      // No refusal on show: it is done.
      expect(screen.queryByRole("alert")).toBeNull();
      // Read again: gone from the page.
      await waitFor(() =>
        expect(screen.queryByRole("button", { name: buttonName })).toBeNull(),
      );
      expect(screen.queryByText(what, { selector: "span" })).toBeNull();
    },
  );

  it("says at once that Sababu is needed, and sends nothing", async () => {
    theServerHas(JUMA_WITH_BOTH);

    render(<WorkerScreen id={JUMA.id} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Ondoa Muuzaji (Dawa)" }),
    );
    // Spaces alone are no reason.
    fireEvent.change(screen.getByLabelText("Sababu"), {
      target: { value: "   " },
    });
    fireEvent.click(button("Hifadhi"));

    // The server's own sentence for it, staff.reason_required, as it never sends `blank` here (StaffReasonSerializer).
    expect(screen.getByText(sentence("staff.reason_required"))).toBeTruthy();
    expect(sent.filter((request) => request.method === "POST")).toHaveLength(0);
  });

  it("shows the server's staff.reason_required beside Sababu", async () => {
    theServerHas(JUMA_WITH_BOTH);
    answer(
      "POST",
      `${STAFF}${JUMA.id}/end-role/`,
      refusal(400, "staff.reason_required"),
    );

    render(<WorkerScreen id={JUMA.id} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Ondoa Muuzaji (Dawa)" }),
    );
    fireEvent.change(screen.getByLabelText("Sababu"), {
      target: { value: "x" },
    });
    fireEvent.click(button("Hifadhi"));

    const box = screen.getByLabelText("Sababu");
    await waitFor(() => expect(box.getAttribute("aria-invalid")).toBe("true"));
    expect(screen.getByText(sentence("staff.reason_required"))).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it.each([
    ["staff.own", 400],
    ["staff.superuser_only", 400],
    ["staff.more_keys", 400],
    ["demo.people_fixed", 400],
    ["permission_denied", 403],
  ])(
    "shows %s above the buttons, and keeps the form (the card's fifth Done when)",
    async (code, status) => {
      theServerHas(JUMA_WITH_BOTH);
      answer("POST", `${STAFF}${JUMA.id}/end-role/`, refusal(status, code));

      render(<WorkerScreen id={JUMA.id} />);
      fireEvent.click(
        await screen.findByRole("button", { name: "Ondoa Muuzaji (Dawa)" }),
      );
      fireEvent.change(screen.getByLabelText("Sababu"), {
        target: { value: "Amehamia Vyakula" },
      });
      fireEvent.click(button("Hifadhi"));

      expect((await screen.findByRole("alert")).textContent).toContain(
        sentence(code),
      );
      expect(screen.getByLabelText("Sababu")).toBeTruthy();
    },
  );

  it("names roles and keys in the three who-may sentences (PPL-7's note)", () => {
    for (const code of ["staff.own", "staff.superuser_only", "staff.more_keys"])
      expect(sentence(code), code).toContain("vyeo na ruhusa");
  });

  it("closes on staff.left, says so, and reads Juma again", async () => {
    const server = theServerHas(JUMA_WITH_BOTH);
    answer("POST", `${STAFF}${JUMA.id}/end-role/`, () => {
      server.now({ ...JUMA_WITH_BOTH, status: "left", left_on: "2026-11-18" });
      return Response.json(
        { code: "staff.left", message: "", fields: {}, params: {} },
        { status: 400 },
      );
    });

    render(<WorkerScreen id={JUMA.id} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Ondoa Muuzaji (Dawa)" }),
    );
    fireEvent.change(screen.getByLabelText("Sababu"), {
      target: { value: "Amehamia Vyakula" },
    });
    fireEvent.click(button("Hifadhi"));

    await waitFor(() =>
      expect(document.activeElement?.textContent).toBe(sentence("staff.left")),
    );
    // A worker who left keeps the role as history, with no Ondoa beside it.
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Ondoa Muuzaji (Dawa)" }),
      ).toBeNull(),
    );
    expect(linesUnder("Cheo")).toEqual(["Muuzaji (Dawa)"]);
  });

  it("switches Hifadhi off offline", async () => {
    theServerHas(JUMA_WITH_BOTH);
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    render(<WorkerScreen id={JUMA.id} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Ondoa Muuzaji (Dawa)" }),
    );

    expect(button("Hifadhi").hasAttribute("disabled")).toBe(true);
  });

  it("gives the keyboard back to its Ondoa on Ghairi, and shows the other buttons again", async () => {
    theServerHas(JUMA_WITH_BOTH);

    render(<WorkerScreen id={JUMA.id} />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Ondoa Kuhesabu mzigo (Vyakula)",
      }),
    );
    // One change at a time: no other button while the form is open.
    expect(screen.queryByRole("button", { name: "Ongeza kazi" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Ondoa Muuzaji (Dawa)" }),
    ).toBeNull();
    fireEvent.click(button("Ghairi"));

    await waitFor(() =>
      expect(document.activeElement).toBe(
        button("Ondoa Kuhesabu mzigo (Vyakula)"),
      ),
    );
    expect(button("Ongeza kazi")).toBeTruthy();
  });

  it("never shows Ondoa beside Mmiliki, which only the superuser takes away", async () => {
    // Asha holds the Owner role and a seller's on Vyakula: Ondoa beside the second only.
    const asha = {
      ...JUMA,
      display_name: "Asha",
      roles: [
        role("owner", null),
        role("seller", VYAKULA.id, { role: SELLER_ROLE.id }),
      ],
    };
    theServerHas(asha);

    render(<WorkerScreen id={asha.id} />);

    expect(
      await screen.findByRole("button", { name: "Ondoa Muuzaji (Vyakula)" }),
    ).toBeTruthy();
    expect(linesUnder("Cheo")[0]).toBe("Mmiliki (Pande zote)");
    expect(
      screen.queryByRole("button", { name: "Ondoa Mmiliki (Pande zote)" }),
    ).toBeNull();
  });
});

describe("a move to another worker", () => {
  it("closes a give open on Juma when the page moves to Baraka, so his choices never go to Baraka", async () => {
    // The browser's back and forward move the address while the page stays: the same screen, another worker
    // (worker-details.test.tsx). The roles card has a key of its own, beside the status buttons' (worker-page.tsx).
    theServerHas(JUMA);
    const baraka = worker({
      full_name: "Baraka Mfano",
      display_name: "Baraka",
    });
    answer("GET", `${STAFF}${baraka.id}/`, { status: 200, body: baraka });
    const { rerender } = render(<WorkerScreen id={baraka.id} />);
    expect(await screen.findByText("Baraka Mfano")).toBeTruthy();
    rerender(<WorkerScreen id={JUMA.id} />);
    await openTheGive();

    rerender(<WorkerScreen id={baraka.id} />);

    expect(await screen.findByText("Baraka Mfano")).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Ongeza kazi kwa Juma" }),
    ).toBeNull();
    expect(button("Ongeza kazi")).toBeTruthy();
    // Both cards drew: the status buttons' and the roles'.
    expect(button("Simamisha")).toBeTruthy();
  });
});

describe("who sees the buttons", () => {
  it("offers Ongeza kazi for a suspended worker, whose role counts once they are back", async () => {
    theServerHas({ ...JUMA, status: "suspended" });

    render(<WorkerScreen id={JUMA.id} />);

    expect(
      await screen.findByRole("button", { name: "Ongeza kazi" }),
    ).toBeTruthy();
  });

  it("offers nothing for a worker who left, whose roles stay as history", async () => {
    theServerHas({
      ...JUMA,
      status: "left",
      left_on: "2026-11-10",
      roles: [role("seller", DAWA.id)],
    });

    render(<WorkerScreen id={JUMA.id} />);

    await screen.findByRole("button", { name: "Mwajiri tena" });
    expect(linesUnder("Cheo")).toEqual(["Muuzaji (Dawa)"]);
    expect(screen.queryByRole("button", { name: "Ongeza kazi" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Ondoa Muuzaji (Dawa)" }),
    ).toBeNull();
  });

  it("offers nothing on one's own page, where staff.own's line says why", async () => {
    // With a role on show, so no Ondoa beside it proves something.
    const own = {
      ...JUMA,
      id: BABA.staff.id,
      display_name: "Neema",
      roles: [role("manager", null)],
    };
    theServerHas(own);

    render(<WorkerScreen id={own.id} />);

    await screen.findByText(sentence("staff.own"));
    expect(screen.queryByRole("button", { name: "Ongeza kazi" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Ondoa/ })).toBeNull();
  });
});
