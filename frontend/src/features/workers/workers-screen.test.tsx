// workers-screen.test.tsx — Wafanyakazi lists the shop's workers, each with their names, roles, sides and status,
// newest first, those who left under their own heading (PPL-6), each group counted in its heading (UI-11); and Ongeza,
// on the title's row, which opens Mfanyakazi mpya (UI-11, new-worker-screen.test.tsx).
import { QueryClientProvider } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { MANAGER, role, STAFF, staffPage, worker } from "@/test/workers";

import { WORKERS } from "./workers";
import { WorkersScreen } from "./workers-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";

type Worker = components["schemas"]["Staff"];

/** The manager is logged in, and the list answers with `workers`, one page. */
function theShopHas(workers: Worker[]) {
  answer("GET", ME, { status: 200, body: MANAGER });
  answer("GET", STAFF, { status: 200, body: staffPage(workers) });
}

/** The rows of the workers still at the shop: the first list on the page. */
async function rowsHere(): Promise<HTMLElement[]> {
  const [here] = await screen.findAllByRole("list");
  return within(here as HTMLElement).getAllByRole("listitem");
}

describe("the workers' page", () => {
  it("shows each worker's names, roles with their sides, and status, in the server's order", async () => {
    // Newest first, as the server sends them: Juma, added today, is where the owner who added him looks.
    theShopHas([
      worker({ display_name: "Juma", full_name: "Juma Mfano" }),
      worker({
        display_name: "Baraka",
        full_name: "Baraka Mfano",
        roles: [role("seller", VYAKULA.id)],
      }),
      worker({
        display_name: "Asha",
        full_name: "Asha Mfano",
        status: "suspended",
        roles: [role("seller", DAWA.id)],
      }),
      worker({
        display_name: "Neema",
        full_name: "Neema Mfano",
        roles: [role("manager", null)],
      }),
    ]);

    render(<WorkersScreen />);

    const [juma, baraka, asha, neema] = await rowsHere();
    expect(within(juma!).getByText("Juma · Juma Mfano")).toBeTruthy();
    expect(within(juma!).getByText("Hana cheo bado")).toBeTruthy();
    expect(within(juma!).getByText("Anafanya kazi")).toBeTruthy();
    expect(within(baraka!).getByText("Baraka · Baraka Mfano")).toBeTruthy();
    expect(within(baraka!).getByText("Muuzaji (Vyakula)")).toBeTruthy();
    expect(within(asha!).getByText("Muuzaji (Dawa)")).toBeTruthy();
    expect(within(asha!).getByText("Amesimamishwa")).toBeTruthy();
    // A role with no side is on every side.
    expect(within(neema!).getByText("Meneja (Pande zote)")).toBeTruthy();
  });

  it("opens each worker's own page from their name", async () => {
    // Jack's picture: tap a worker's name and see everything of theirs.
    const asha = worker({ display_name: "Asha", full_name: "Asha Mfano" });
    theShopHas([asha]);

    render(<WorkersScreen />);

    const link = await screen.findByRole("link", { name: "Asha · Asha Mfano" });
    // The slash before "?" comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(link.getAttribute("href")).toMatch(
      new RegExp(`^/workers/view/?\\?id=${asha.id}$`),
    );
  });

  it("joins two roles the language's way, and names a role the owner made by its own name", async () => {
    theShopHas([
      worker({
        roles: [role("seller", DAWA.id), role("cashier", VYAKULA.id)],
      }),
      // A role of no template: the shop's own, with the name the owner gave it.
      worker({
        display_name: "Hamisi",
        roles: [role("", DAWA.id, { name: "Mlinzi" })],
      }),
    ]);

    render(<WorkersScreen />);

    const [two, own] = await rowsHere();
    expect(
      within(two!).getByText("Muuzaji (Dawa) na Keshia (Vyakula)"),
    ).toBeTruthy();
    expect(within(own!).getByText("Mlinzi (Dawa)")).toBeTruthy();
  });

  it("counts the keys given apart from any role", async () => {
    // Counted on the list, so a row stays short; the worker's own page names each (PPL-8).
    let given = 0;
    const key = (permission: string) => {
      given += 1;
      return {
        id: `019a8303-0000-7000-8000-${String(given).padStart(12, "0")}`,
        permission,
        side: null,
      };
    };
    theShopHas([
      worker({ keys: [key("staff.manage"), key("settings.manage")] }),
      worker({ display_name: "Asha", keys: [key("flag.review")] }),
      worker({ display_name: "Baraka" }),
    ]);

    render(<WorkersScreen />);

    const [two, one, none] = await rowsHere();
    expect(within(two!).getByText("Ruhusa 2 za ziada")).toBeTruthy();
    expect(within(one!).getByText("Ruhusa 1 ya ziada")).toBeTruthy();
    expect(within(none!).queryByText(/ziada/)).toBeNull();
  });

  it("puts those who left under their own heading, at the bottom", async () => {
    theShopHas([
      worker({ display_name: "Juma" }),
      worker({
        display_name: "Hamisi",
        full_name: "Hamisi Mfano",
        status: "left",
        left_on: "2026-11-10",
      }),
    ]);

    render(<WorkersScreen />);

    const here = await rowsHere();
    expect(here).toHaveLength(1);
    expect(within(here[0]!).queryByText(/Hamisi/)).toBeNull();
    const gone = screen.getByRole("region", { name: "Walioondoka (1)" });
    expect(within(gone).getByText("Hamisi · Hamisi Mfano")).toBeTruthy();
    expect(within(gone).getByText("Ameondoka")).toBeTruthy();
  });

  it("shows a worker hired again with those working, and his old job still under Walioondoka (PPL-11, Jack: A)", async () => {
    // Baraka left on 12 Mar and came back: his new job is at the top, newest first, and the old one stays as the
    // history it is, each linking to its own page.
    const back = worker({ display_name: "Baraka", full_name: "Baraka Mfano" });
    const old = worker({
      display_name: "Baraka",
      full_name: "Baraka Mfano",
      started_on: "2025-01-02",
      status: "left",
      left_on: "2026-03-12",
      hired_again_as: back.id,
    });
    theShopHas([back, old]);

    render(<WorkersScreen />);

    const [here] = await rowsHere();
    const gone = screen.getByRole("region", { name: "Walioondoka (1)" });
    const now = within(here!).getByRole("link", {
      name: "Baraka · Baraka Mfano",
    });
    const then = within(gone).getByRole("link", {
      name: "Baraka · Baraka Mfano",
    });
    // The app is built with trailing slashes; Next.js's Link in a test drops them (text-link.test.tsx).
    expect(now.getAttribute("href")).toMatch(
      new RegExp(`^/workers/view/?\\?id=${back.id}$`),
    );
    expect(then.getAttribute("href")).toMatch(
      new RegExp(`^/workers/view/?\\?id=${old.id}$`),
    );
  });

  it("says nobody left, when nobody has", async () => {
    theShopHas([worker()]);

    render(<WorkersScreen />);

    const gone = await screen.findByRole("region", {
      name: "Walioondoka (0)",
    });
    expect(within(gone).getByText("Hakuna.")).toBeTruthy();
  });

  it("says nobody works here, when everyone has left", async () => {
    // A heading alone over nothing would look like a list still on its way.
    theShopHas([worker({ status: "left", left_on: "2026-11-10" })]);

    render(<WorkersScreen />);

    const here = await screen.findByRole("region", {
      name: "Wanaofanya kazi (0)",
    });
    expect(within(here).getByText("Hakuna.")).toBeTruthy();
    expect(within(here).queryByRole("list")).toBeNull();
  });

  it("counts each group in its heading, the suspended among those working (UI-11, as Jack pictured it)", async () => {
    // Five at the shop, Juma suspended among them, as he comes back; two who left.
    theShopHas([
      worker({ display_name: "Neema" }),
      worker({ display_name: "Juma", status: "suspended" }),
      worker({ display_name: "Baraka" }),
      worker({ display_name: "Asha" }),
      worker({ display_name: "Meneja" }),
      worker({ display_name: "Halima", status: "left", left_on: "2026-10-01" }),
      worker({ display_name: "Musa", status: "left", left_on: "2026-09-15" }),
    ]);

    render(<WorkersScreen />);

    const here = await screen.findByRole("region", {
      name: "Wanaofanya kazi (5)",
    });
    expect(within(here).getAllByRole("listitem")).toHaveLength(5);
    const gone = screen.getByRole("region", { name: "Walioondoka (2)" });
    expect(within(gone).getAllByRole("listitem")).toHaveLength(2);
    // Each a heading under the page's title, so a screen reader can jump between the two.
    expect(
      screen
        .getAllByRole("heading", { level: 2 })
        .map((heading) => heading.textContent),
    ).toEqual(["Wanaofanya kazi (5)", "Walioondoka (2)"]);
  });

  it("says who the superuser switched off, apart from the job's status", async () => {
    // Still working here, as far as the shop knows; but the admin switched the person off, so they can't log in
    // (PPL-4's review).
    theShopHas([worker({ switched_off: true })]);

    render(<WorkersScreen />);

    const [juma] = await rowsHere();
    expect(within(juma!).getByText("Anafanya kazi")).toBeTruthy();
    expect(
      within(juma!).getByText(
        "Amezimwa na msimamizi wa mfumo. Hawezi kuingia.",
      ),
    ).toBeTruthy();
  });

  it("reads every page of the list", async () => {
    // 50 a page: a shop with years of workers fills more than one.
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("GET", STAFF, (request) => {
      const cursor = new URL(request.url).searchParams.get("cursor");
      return Response.json(
        cursor === "page2"
          ? staffPage([
              worker({ display_name: "Asha", full_name: "Asha Mfano" }),
            ])
          : staffPage(
              [worker({ display_name: "Juma", full_name: "Juma Mfano" })],
              `http://shop.test${STAFF}?cursor=page2`,
            ),
      );
    });

    render(<WorkersScreen />);

    const rows = await rowsHere();
    expect(rows.map((row) => row.querySelector("p")?.textContent)).toEqual([
      "Juma · Juma Mfano",
      "Asha · Asha Mfano",
    ]);
  });

  it("shows the server's refusal to someone without staff.manage on the whole shop", async () => {
    // Opened by its address, as no button leads a seller here: the server says no, and the page says why.
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["sale.create"] }]),
    });
    answer("GET", STAFF, refusal(403, "permission_denied"));

    render(<WorkersScreen />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Huna ruhusa ya kufanya hili.",
    );
    expect(screen.queryByRole("list")).toBeNull();
    // Asked once, not round and round: the part that shows the list doesn't ask it again as it mounts.
    await new Promise((settle) => setTimeout(settle, 50));
    expect(sent.filter((request) => request.url.endsWith(STAFF))).toHaveLength(
      1,
    );
  });

  it("says to wait through the store's own tries, so the page is never empty (PPL-6's review)", async () => {
    // The first read finds no network: the store asks again for some 3 seconds, with no answer and no error yet.
    const store = makeQueryClient();
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("GET", STAFF, () => {
      throw new TypeError("Failed to fetch");
    });
    render(
      <QueryClientProvider client={store}>
        <WorkersScreen />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(store.getQueryState(WORKERS)?.fetchFailureCount).toBe(1),
    );
    expect(screen.getByText("Subiri kidogo…").getAttribute("role")).toBe(
      "status",
    );
    // The store's tries stop here, so none goes on after the test.
    await store.cancelQueries();
  });

  it("says to wait while it asks, so the page is never a title alone", () => {
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("GET", STAFF, () => new Promise<Response>(() => undefined));

    render(<WorkersScreen />);

    const line = screen.getByText("Subiri kidogo…");
    expect(line.getAttribute("role")).toBe("status");
  });
});

describe("Ongeza on the workers' page", () => {
  it("sits on the title's row, a link to Mfanyakazi mpya (UI-11)", async () => {
    theShopHas([worker({ display_name: "Asha" })]);
    render(<WorkersScreen />);

    const ongeza = await screen.findByRole("link", { name: "Ongeza" });
    // A page of its own, as a long form keeps one (UI-11). The app is built with trailing slashes; Next.js's Link in a
    // test drops them (text-link.test.tsx).
    expect(ongeza.getAttribute("href")).toMatch(/^\/workers\/new\/?$/);
    // Beside the title, at the top, however long the list grows.
    const title = screen.getByRole("heading", { level: 1 });
    expect(title.parentElement?.contains(ongeza)).toBe(true);
    // No form on the list itself any more.
    expect(screen.queryByLabelText("Jina kamili")).toBeNull();
  });

  it("shows as soon as the page knows who is here, never waiting for the list", async () => {
    // A list that never answers keeps the page waiting; Ongeza is there all the same (PPL-6's review).
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("GET", STAFF, () => new Promise<Response>(() => undefined));
    render(<WorkersScreen />);

    expect(await screen.findByRole("link", { name: "Ongeza" })).toBeTruthy();
    expect(screen.getByText("Subiri kidogo…")).toBeTruthy();
  });

  it("is offered to nobody without staff.manage on the whole shop", async () => {
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["staff.manage"] }]),
    });
    answer("GET", STAFF, refusal(403, "permission_denied"));
    render(<WorkersScreen />);

    await screen.findByRole("alert");
    expect(screen.queryByRole("link", { name: "Ongeza" })).toBeNull();
  });
});
