// workers-screen.test.tsx — Wafanyakazi lists the shop's workers, each with their names, roles, sides and status,
// newest first, those who left under their own heading (PPL-6); and Ongeza, whose worker comes at the top.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
    // Their names come with PPL-8, which gives them; until then the owner sees there are some.
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
    const gone = screen.getByRole("region", { name: "Walioondoka" });
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
    const gone = screen.getByRole("region", { name: "Walioondoka" });
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

    const gone = await screen.findByRole("region", { name: "Walioondoka" });
    expect(within(gone).getByText("Hakuna.")).toBeTruthy();
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
  const asha = worker({ display_name: "Asha", full_name: "Asha Mfano" });
  const juma = worker({ display_name: "Juma", full_name: "Juma Mfano" });

  /** Opens the form and types Juma's names. */
  async function typeJuma() {
    fireEvent.click(await screen.findByRole("button", { name: "Ongeza" }));
    fireEvent.change(screen.getByLabelText("Jina kamili"), {
      target: { value: "Juma Mfano" },
    });
    fireEvent.change(screen.getByLabelText("Jina la kuitwa"), {
      target: { value: "Juma" },
    });
  }

  it("adds Juma at the top of the list, says he gets a tile with a PIN, and gives the keyboard back to Ongeza", async () => {
    theShopHas([asha]);
    answer("POST", STAFF, { status: 201, body: juma });
    render(<WorkersScreen />);

    await typeJuma();
    // The list asked again after the add answers with Juma in it.
    answer("GET", STAFF, { status: 200, body: staffPage([juma, asha]) });
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    expect(
      await screen.findByText(
        "Juma ameongezwa. Jina lake litaonekana kwenye kompyuta za duka baada ya kupewa PIN.",
      ),
    ).toBeTruthy();
    const [first] = await rowsHere();
    expect(within(first!).getByText("Juma · Juma Mfano")).toBeTruthy();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Ongeza" }),
    );
  });

  it("keeps Juma on the list when the read after the add fails", async () => {
    // The server's answer is put in the list at once (keepWorker), so a failed read never hides him.
    theShopHas([asha]);
    answer("POST", STAFF, { status: 201, body: juma });
    render(<WorkersScreen />);

    await typeJuma();
    answer("GET", STAFF, refusal(403, "staff.suspended"));
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    await screen.findByRole("alert");
    const rows = await rowsHere();
    expect(rows.map((row) => row.querySelector("p")?.textContent)).toEqual([
      "Juma · Juma Mfano",
      "Asha · Asha Mfano",
    ]);
  });

  it("starts the first day at the shop's today", async () => {
    theShopHas([asha]);
    vi.useFakeTimers({
      now: Date.parse("2026-11-18T21:30:00Z"),
      toFake: ["Date"],
    });
    render(<WorkersScreen />);

    fireEvent.click(await screen.findByRole("button", { name: "Ongeza" }));

    // 21:30 UTC is 00:30 on the 19th in Dar es Salaam: the shop's day, whatever the phone's zone.
    expect(
      (screen.getByLabelText("Siku ya kwanza") as HTMLInputElement).value,
    ).toBe("2026-11-19");
    vi.useRealTimers();
  });

  it("asks the list again on Ghairi, as a send whose answer was lost may have added the worker", async () => {
    theShopHas([asha]);
    render(<WorkersScreen />);

    await typeJuma();
    const reads = () =>
      sent.filter(
        (request) => request.method === "GET" && request.url.endsWith(STAFF),
      ).length;
    const before = reads();
    fireEvent.click(screen.getByRole("button", { name: "Ghairi" }));

    await waitFor(() => expect(reads()).toBe(before + 1));
    expect(screen.queryByLabelText("Jina kamili")).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Ongeza" }),
    );
  });

  it("keeps Ongeza's form, and what was typed, when a list that never answered is asked again (PPL-6's review)", async () => {
    // The list's first read found no network; the owner opens Ongeza, types Juma, switches to WhatsApp to check his
    // spelling, and comes back: the page asks the list again, and goes back to waiting for it. The form stays.
    // Retries off, so the test needn't wait for the store's own tries after the first failure.
    const store = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("GET", STAFF, () => {
      throw new TypeError("Failed to fetch");
    });
    render(
      <QueryClientProvider client={store}>
        <WorkersScreen />
      </QueryClientProvider>,
    );
    await typeJuma();

    // The read again, which never answers: the list waits once more.
    answer("GET", STAFF, () => new Promise<Response>(() => undefined));
    await act(() => {
      void store.invalidateQueries({ queryKey: WORKERS });
    });

    await screen.findByText("Subiri kidogo…");
    expect(
      (screen.getByLabelText("Jina la kuitwa") as HTMLInputElement).value,
    ).toBe("Juma");
  });

  it("offers no Ongeza to someone without staff.manage on the whole shop", async () => {
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["staff.manage"] }]),
    });
    answer("GET", STAFF, refusal(403, "permission_denied"));
    render(<WorkersScreen />);

    await screen.findByRole("alert");
    expect(screen.queryByRole("button", { name: "Ongeza" })).toBeNull();
  });

  it("keeps Simu off on the demo, and says why (PPL-10, PPL-11: no phone there)", async () => {
    theShopHas([asha]);
    answer("GET", "/api/devices/v1/demo/open/", {
      status: 200,
      body: { open: true },
    });
    render(<WorkersScreen />);

    fireEvent.click(await screen.findByRole("button", { name: "Ongeza" }));

    await waitFor(() =>
      expect((screen.getByLabelText("Simu") as HTMLInputElement).disabled).toBe(
        true,
      ),
    );
    expect(
      screen.getByText(/Kwenye demo, wafanyakazi hawawekewi namba/),
    ).toBeTruthy();
  });
});
