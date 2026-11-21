// worker-page.test.tsx — one worker's own page (PPL-6): everything of theirs, the list's copy at once, the server's
// answer after, and what it says with no worker or an unknown one. Their roles and extra keys, each by its name and
// side, in a card of their own (PPL-8). The line a long form's own page left as it landed here, shown once, on the
// card and the worker it names (UI-11).
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { forgetTheLastPerson, makeQueryClient } from "@/api/query-client";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { PAY_RATES_ROUTE, payRate, payRates } from "@/test/pay-rates";
import { render } from "@/test/render";
import { router } from "@/test/router";
import { BABA, MANAGER, role, STAFF, worker } from "@/test/workers";

import { forgetNews, leaveNews, peekNews } from "./page-news";
import { WorkerScreen } from "./worker-page";
import { workerKey, WORKERS } from "./workers";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";

afterEach(() => {
  // A note left by a test is never read by the next one's page.
  forgetNews();
});

/** Asha, as the server answers her: a seller on Dawa and a cashier on Vyakula, suspended. */
const ASHA = worker({
  full_name: "Asha Mfano",
  display_name: "Asha",
  job_title: "Muuzaji wa dawa",
  started_on: "2026-11-03",
  status: "suspended",
  roles: [role("seller", DAWA.id), role("cashier", VYAKULA.id)],
});

/** The value beside a label: the <dd> after its <dt>. */
function valueOf(label: string): string {
  const term = screen.getByText(label, { selector: "dt" });
  return term.nextElementSibling?.textContent ?? "";
}

/** The lines under one of the roles card's headings, Cheo or Ruhusa za ziada: each item's words, or the one line that
 * says there is none. */
function linesUnder(heading: string): string[] {
  const section = screen.getByRole("region", { name: heading });
  const items = within(section).queryAllByRole("listitem");
  return items.length > 0
    ? // The words alone: the item's first part, before its Ondoa (PPL-8).
      items.map((item) => item.firstElementChild?.textContent ?? "")
    : within(section)
        .getAllByText(/.+/, { selector: "p" })
        .map((line) => line.textContent ?? "");
}

/** Waits until the worker's details show: after both `me` and the worker answered. The title alone can come
 * sooner, from the list's copy. */
async function detailsShown() {
  await screen.findByText("Jina kamili", { selector: "dt" });
}

/** The manager is logged in, and the worker's route answers with `who`. */
function theServerHas(who: typeof ASHA) {
  answer("GET", ME, { status: 200, body: MANAGER });
  answer("GET", `${STAFF}${who.id}/`, { status: 200, body: who });
}

describe("a worker's own page", () => {
  it("shows everything of the worker's (the card's third Done when)", async () => {
    theServerHas(ASHA);

    render(<WorkerScreen id={ASHA.id} />);

    await detailsShown();
    // The nickname as the title, the name the shop calls her by.
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Asha");
    expect(valueOf("Jina kamili")).toBe("Asha Mfano");
    expect(valueOf("Jina la kuitwa")).toBe("Asha");
    expect(valueOf("Kazi")).toBe("Muuzaji wa dawa");
    expect(valueOf("Siku ya kwanza")).toBe("03/11/2026");
    expect(valueOf("Hali")).toBe("Amesimamishwa");
    // One role a line, each with its side, in a card of their own (PPL-8).
    expect(linesUnder("Cheo")).toEqual(["Muuzaji (Dawa)", "Keshia (Vyakula)"]);
    // Still working here: no last day.
    expect(screen.queryByText("Siku ya mwisho")).toBeNull();
  });

  it("cuts the page into four headed cards, each button on its heading's row (UI-10)", async () => {
    // Baba sees Juma's pay too (maySeePay), so all four cards show: Juma works, with a rate in force.
    const juma = worker({ started_on: "2026-11-10" });
    const rate = payRate({ staff: juma.id });
    answer("GET", ME, { status: 200, body: BABA });
    answer("GET", `${STAFF}${juma.id}/`, { status: 200, body: juma });
    answer("GET", PAY_RATES_ROUTE, {
      status: 200,
      body: payRates([rate], rate),
    });

    render(<WorkerScreen id={juma.id} />);

    await screen.findByRole("button", { name: "Badilisha malipo" });
    // One <h2> a card, in the page's order, under the nickname's <h1>; Ruhusa za ziada is Cheo's own, a level down.
    expect(
      screen
        .getAllByRole("heading", { level: 2 })
        .map((heading) => heading.textContent),
    ).toEqual(["Taarifa zake", "Kuingia", "Cheo", "Malipo kwa siku"]);
    expect(
      screen.getByRole("heading", { level: 3, name: "Ruhusa za ziada" }),
    ).toBeDefined();
    // The button that changes a card's whole subject sits beside its heading, on one row (its parent).
    const besideHeading = (
      heading: string,
      name: string,
      role: "button" | "link" = "button",
    ) =>
      within(
        screen.getByRole("heading", { level: 2, name: heading })
          .parentElement as HTMLElement,
      ).getByRole(role, { name });
    // Badilisha and Ongeza kazi links, as each opens a page of its own (UI-11).
    expect(besideHeading("Taarifa zake", "Badilisha", "link")).toBeDefined();
    expect(besideHeading("Cheo", "Ongeza kazi", "link")).toBeDefined();
    expect(besideHeading("Malipo kwa siku", "Badilisha malipo")).toBeDefined();
    // Simamisha and Ameondoka under the details, inside Taarifa zake; Kuingia's two buttons in its own card.
    const details = screen.getByRole("region", { name: "Taarifa zake" });
    expect(within(details).getByText("Jina kamili")).toBeDefined();
    for (const name of ["Simamisha", "Ameondoka"])
      expect(within(details).getByRole("button", { name })).toBeDefined();
    const logins = screen.getByRole("region", { name: "Kuingia" });
    for (const name of ["Weka PIN", "Nenosiri la muda"])
      expect(within(logins).getByRole("button", { name })).toBeDefined();
  });

  it("shows a last day for one who left, and says when there is no title, role or key", async () => {
    const hamisi = worker({
      display_name: "Hamisi",
      status: "left",
      left_on: "2026-11-10",
    });
    theServerHas(hamisi);

    render(<WorkerScreen id={hamisi.id} />);

    await detailsShown();
    expect(valueOf("Hali")).toBe("Ameondoka");
    expect(valueOf("Siku ya mwisho")).toBe("10/11/2026");
    expect(valueOf("Kazi")).toBe("Hakuna");
    // Roles and keys stay on the page of one who left, as history (PPL-8): here, none of either.
    expect(linesUnder("Cheo")).toEqual(["Hana cheo bado"]);
    expect(linesUnder("Ruhusa za ziada")).toEqual(["Hana ruhusa za ziada"]);
  });

  it("shows each extra key by its name and side, in the server's order (the card's first Done when)", async () => {
    // Given in another order than permissions.py's: settings first, the stock count on Vyakula, staff on every side.
    const neema = worker({
      display_name: "Neema",
      roles: [role("manager", null)],
      keys: [
        {
          id: "019a8303-0000-7000-8000-000000000001",
          permission: "settings.manage",
          side: null,
        },
        {
          id: "019a8303-0000-7000-8000-000000000002",
          permission: "stock.count",
          side: VYAKULA.id,
        },
        {
          id: "019a8303-0000-7000-8000-000000000003",
          permission: "staff.manage",
          side: null,
        },
      ],
    });
    theServerHas(neema);

    render(<WorkerScreen id={neema.id} />);

    await detailsShown();
    expect(linesUnder("Cheo")).toEqual(["Meneja (Pande zote)"]);
    // By name, no longer a count (PPL-6's default): stock, then staff, then the shop itself, as permissions.py.
    expect(linesUnder("Ruhusa za ziada")).toEqual([
      "Kuhesabu mzigo (Vyakula)",
      "Kuongeza wafanyakazi na kuwapa vyeo (Pande zote)",
      "Kubadilisha sheria na viwango vya duka (Pande zote)",
    ]);
  });

  it("shows a key this app doesn't know yet by its code, last", async () => {
    // A newer server, a newer code: readable, never blank.
    const neema = worker({
      display_name: "Neema",
      keys: [
        {
          id: "019a8303-0000-7000-8000-000000000004",
          permission: "seed.sow",
          side: null,
        },
        {
          id: "019a8303-0000-7000-8000-000000000005",
          permission: "sale.refund",
          side: DAWA.id,
        },
      ],
    });
    theServerHas(neema);

    render(<WorkerScreen id={neema.id} />);

    await detailsShown();
    expect(linesUnder("Ruhusa za ziada")).toEqual([
      "Kurudisha pesa ya mauzo (Dawa)",
      "seed.sow (Pande zote)",
    ]);
  });

  it("says who the superuser switched off", async () => {
    const neema = worker({ display_name: "Neema", switched_off: true });
    theServerHas(neema);

    render(<WorkerScreen id={neema.id} />);

    await detailsShown();
    expect(
      screen.getByText("Amezimwa na msimamizi wa mfumo. Hawezi kuingia."),
    ).toBeTruthy();
  });

  it("shows the list's copy at once, as the person came from the list, then the server's", async () => {
    // The server's answer is slow: the page doesn't wait for it to show Asha.
    const store = makeQueryClient();
    store.setQueryData(WORKERS, [ASHA]);
    answer("GET", ME, { status: 200, body: MANAGER });
    let answerAsha: (response: Response) => void = () => undefined;
    answer(
      "GET",
      `${STAFF}${ASHA.id}/`,
      () => new Promise<Response>((settle) => (answerAsha = settle)),
    );

    render(
      <QueryClientProvider client={store}>
        <WorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );

    await detailsShown();
    expect(valueOf("Hali")).toBe("Amesimamishwa");
    // Someone brought her back meanwhile: the server's answer wins.
    await waitFor(() =>
      expect(sent.some((request) => request.url.endsWith(`${ASHA.id}/`))).toBe(
        true,
      ),
    );
    answerAsha(Response.json({ ...ASHA, status: "active" }));
    await waitFor(() => expect(valueOf("Hali")).toBe("Anafanya kazi"));
  });

  it("shows the next person nothing of the last one's copy, after a logout (PPL-6's review)", async () => {
    // On the Dawa laptop, Neema opens Asha's page from the list, then taps Toka. Juma, a seller, logs in with his PIN
    // and opens Asha's page from the browser's history: the server refuses him, and the page shows no Asha.
    const store = makeQueryClient();
    store.setQueryData(WORKERS, [ASHA]);
    theServerHas(ASHA);
    const neema = render(
      <QueryClientProvider client={store}>
        <WorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );
    await detailsShown();
    neema.unmount();

    // The logout, as every login, logout and quick switch does (UI-4).
    await forgetTheLastPerson(store);
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["sale.create"] }]),
    });
    answer("GET", `${STAFF}${ASHA.id}/`, refusal(403, "permission_denied"));
    render(
      <QueryClientProvider client={store}>
        <WorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Huna ruhusa ya kufanya hili.",
    );
    expect(screen.queryByText("Jina kamili")).toBeNull();
    expect(screen.queryByRole("button", { name: "Simamisha" })).toBeNull();
  });

  it("says when the server knows no such worker, asking once", async () => {
    // A link from another shop, or a worker's id typed wrong.
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("GET", `${STAFF}${ASHA.id}/`, refusal(404, "not_found"));

    render(<WorkerScreen id={ASHA.id} />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Hakijapatikana.",
    );
    expect(screen.queryByText("Jina kamili")).toBeNull();
    // Asked once, not round and round (workers-screen.tsx).
    await new Promise((settle) => setTimeout(settle, 50));
    expect(
      sent.filter((request) => request.url.endsWith(`${ASHA.id}/`)),
    ).toHaveLength(1);
  });

  it("says to wait through the store's own tries, so the page is never a title alone (PPL-6's review)", async () => {
    // Opened from a link, with no list's copy: the first read finds no network, and the store asks again.
    const store = makeQueryClient();
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("GET", `${STAFF}${ASHA.id}/`, () => {
      throw new TypeError("Failed to fetch");
    });
    render(
      <QueryClientProvider client={store}>
        <WorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(store.getQueryState(workerKey(ASHA.id))?.fetchFailureCount).toBe(
        1,
      ),
    );
    expect(screen.getByText("Subiri kidogo…").getAttribute("role")).toBe(
      "status",
    );
    // The store's tries stop here, so none goes on after the test.
    await store.cancelQueries();
  });

  it("says no worker was chosen, and asks nothing, with no id in the address", async () => {
    answer("GET", ME, { status: 200, body: MANAGER });

    render(<WorkerScreen id={null} />);

    expect(
      await screen.findByText(
        "Hakuna mfanyakazi aliyechaguliwa. Rudi kwenye orodha ya wafanyakazi.",
      ),
    ).toBeTruthy();
    expect(sent.filter((request) => request.url.includes(STAFF))).toHaveLength(
      0,
    );
  });

  it("goes back to the list when opened from outside the app", async () => {
    // From a link in a message: no page of the app to go back to (in-app-moves.tsx).
    theServerHas(ASHA);

    render(<WorkerScreen id={ASHA.id} />);

    await detailsShown();
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(router.push).toHaveBeenCalledWith("/workers/");
  });
});

describe("the line a form's own page left (UI-11)", () => {
  /** What Mfanyakazi mpya leaves for Asha's page as it lands there. */
  const ADDED =
    "Asha ameongezwa. Jina lake litaonekana kwenye kompyuta za duka baada ya kupewa PIN.";

  it("shows on Taarifa zake, with the keyboard on it, as after a change made on the page", async () => {
    leaveNews({ worker: ASHA.id, card: "details", sentence: ADDED });
    theServerHas(ASHA);

    render(<WorkerScreen id={ASHA.id} />);

    const line = await screen.findByText(ADDED);
    const details = screen.getByRole("region", { name: "Taarifa zake" });
    expect(details.contains(line)).toBe(true);
    // Read by a screen reader as its words come (role="status"), and where the keyboard goes.
    await waitFor(() =>
      expect(document.activeElement?.contains(line)).toBe(true),
    );
  });

  it("shows once when React draws the page twice, as it does in development, and is spent after (UI-11's review)", async () => {
    // StrictMode draws each part twice and runs each effect twice: whichever draw and effect come last, the line shows
    // once, and the note is spent after (page-news.ts).
    leaveNews({ worker: ASHA.id, card: "details", sentence: ADDED });
    theServerHas(ASHA);

    render(
      <StrictMode>
        <WorkerScreen id={ASHA.id} />
      </StrictMode>,
    );

    expect(await screen.findAllByText(ADDED)).toHaveLength(1);
    await waitFor(() =>
      expect(document.activeElement?.textContent).toBe(ADDED),
    );
    expect(peekNews()).toBeNull();
  });

  it("shows once: gone after a move to another worker's page and back", async () => {
    const baraka = worker({ display_name: "Baraka" });
    leaveNews({ worker: ASHA.id, card: "details", sentence: ADDED });
    theServerHas(ASHA);
    answer("GET", `${STAFF}${baraka.id}/`, { status: 200, body: baraka });

    const { rerender } = render(<WorkerScreen id={ASHA.id} />);
    await screen.findByText(ADDED);

    // The browser's back and forward move the address's id with the page still on the screen.
    rerender(<WorkerScreen id={baraka.id} />);
    await screen.findByRole("heading", { level: 1, name: "Baraka" });
    expect(screen.queryByText(ADDED)).toBeNull();
    rerender(<WorkerScreen id={ASHA.id} />);
    await screen.findByRole("heading", { level: 1, name: "Asha" });
    await detailsShown();
    expect(screen.queryByText(ADDED)).toBeNull();
  });

  it("drops a line left for another worker, so it never shows on theirs later", async () => {
    // Juma's page never came: the person left Mfanyakazi mpya's move by another way, and opened Asha's.
    leaveNews({
      worker: "019a8302-0000-7000-8000-0000000000ff",
      card: "details",
      sentence: "Juma ameongezwa.",
    });
    theServerHas(ASHA);

    render(<WorkerScreen id={ASHA.id} />);

    await detailsShown();
    expect(screen.queryByText("Juma ameongezwa.")).toBeNull();
    // Forgotten, all the same: nobody's page shows it now.
    expect(peekNews()).toBeNull();
  });
});
