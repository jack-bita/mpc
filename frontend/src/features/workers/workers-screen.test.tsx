// workers-screen.test.tsx — Wafanyakazi lists the shop's workers, each with their names, roles, sides and status,
// newest first, those who left under their own heading (PPL-6).
import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { MANAGER, role, STAFF, staffPage, worker } from "@/test/workers";

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

  it("says to wait while it asks, so the page is never a title alone", () => {
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("GET", STAFF, () => new Promise<Response>(() => undefined));

    render(<WorkersScreen />);

    const line = screen.getByText("Subiri kidogo…");
    expect(line.getAttribute("role")).toBe("status");
  });
});
