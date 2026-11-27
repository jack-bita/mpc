// flag-filter.test.tsx — Chuja keeps Tofauti to a side and a kind, from a sheet, and the address keeps what was chosen
// (CTRL-4).
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, sent } from "@/test/fake-server";
import { flagLine, flagsPage, FLAGS_ROUTE, REVIEWER } from "@/test/flags";
import { render } from "@/test/render";

import { FlagsScreen } from "./flags-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";

beforeEach(() => {
  window.history.replaceState(null, "", "/flags/");
});

/** The list answers one flag, whatever is asked, to `me`. */
function theShopHas(
  me: components["schemas"]["WhoIsHere"] = REVIEWER,
  page = flagsPage([flagLine()]),
) {
  answer("GET", ME, { status: 200, body: me });
  answer("GET", FLAGS_ROUTE, { status: 200, body: page });
}

/** What the list was last asked for, its state and its filters. */
function lastAsked(): Record<string, string> {
  const last = sent
    .map((request) => new URL(request.url))
    .filter((url) => url.pathname === FLAGS_ROUTE)
    .at(-1);
  return Object.fromEntries(last?.searchParams ?? []);
}

async function openTheSheet(): Promise<HTMLElement> {
  fireEvent.click(await screen.findByRole("button", { name: "Chuja" }));
  return screen.findByRole("dialog", { name: "Chuja" });
}

function rows(sheet: HTMLElement, group: string) {
  return within(within(sheet).getByRole("radiogroup", { name: group }));
}

function pick(sheet: HTMLElement, group: string, row: string) {
  fireEvent.click(rows(sheet, group).getByRole("radio", { name: row }));
}

describe("Chuja", () => {
  it("keeps the list to a side and a kind, says so, and keeps both in the address", async () => {
    theShopHas();
    render(<FlagsScreen />);
    const sheet = await openTheSheet();

    pick(sheet, "Upande", "Vyakula");
    pick(sheet, "Aina", "Saa yake haiaminiki");
    fireEvent.click(within(sheet).getByRole("button", { name: "Onyesha" }));

    expect(
      await screen.findByText("Umechuja: Vyakula · Saa yake haiaminiki"),
    ).toBeTruthy();
    const kept = { side: VYAKULA.id, kind: "unverified_time" };
    await waitFor(() =>
      expect(lastAsked()).toEqual({ state: "waiting", ...kept }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(
      Object.fromEntries(new URLSearchParams(window.location.search)),
    ).toEqual(kept);
  });

  it("asks for the whole shop's own by a word of its own, as they have no side", async () => {
    theShopHas();
    render(<FlagsScreen />);
    const sheet = await openTheSheet();

    pick(sheet, "Upande", "Duka zima");
    fireEvent.click(within(sheet).getByRole("button", { name: "Onyesha" }));

    expect(await screen.findByText("Umechuja: Duka zima")).toBeTruthy();
    await waitFor(() =>
      expect(lastAsked()).toEqual({ state: "waiting", whole_shop: "true" }),
    );
  });

  it("leaves the list as it was on Ghairi", async () => {
    theShopHas();
    render(<FlagsScreen />);
    const sheet = await openTheSheet();

    pick(sheet, "Upande", "Dawa");
    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.queryByText(/^Umechuja/)).toBeNull();
    expect(lastAsked()).toEqual({ state: "waiting" });
    // Opened again, it starts from the list as it is, not from what was picked and left.
    const again = await openTheSheet();
    expect(
      rows(again, "Upande")
        .getByRole("radio", { name: "Pande zote" })
        .getAttribute("aria-checked"),
    ).toBe("true");
  });

  it("goes back to the whole list with one button, and keeps the keyboard's place", async () => {
    window.history.replaceState(null, "", "/flags/?kind=device_gap&tab=closed");
    theShopHas();
    render(<FlagsScreen />);
    await screen.findByText("Umechuja: Kumbukumbu zinakosekana");

    fireEvent.click(screen.getByRole("button", { name: "Onyesha zote" }));

    await waitFor(() => expect(lastAsked()).toEqual({ state: "closed" }));
    expect(screen.queryByText(/^Umechuja/)).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Chuja" }),
    );
    // The tab stays as it was.
    expect(window.location.search).toBe("?tab=closed");
  });

  it.each(["Ghairi", "Onyesha"])(
    "gives the keyboard back to Chuja after %s",
    async (button) => {
      theShopHas();
      render(<FlagsScreen />);
      const sheet = await openTheSheet();

      fireEvent.click(within(sheet).getByRole("button", { name: button }));

      const opener = await screen.findByRole("button", { name: "Chuja" });
      await waitFor(() => expect(document.activeElement).toBe(opener));
    },
  );

  it("starts from what the address names, the sheet too", async () => {
    window.history.replaceState(
      null,
      "",
      `/flags/?side=${DAWA.id}&kind=permission_break`,
    );
    theShopHas();

    render(<FlagsScreen />);

    expect(
      await screen.findByText("Umechuja: Dawa · Hakuwa na ruhusa"),
    ).toBeTruthy();
    const sheet = await openTheSheet();
    for (const picked of ["Dawa", "Hakuwa na ruhusa"])
      expect(
        within(sheet)
          .getByRole("radio", { name: picked })
          .getAttribute("aria-checked"),
      ).toBe("true");
  });

  it("filters by nothing it doesn't know: a side since gone, a kind no more", async () => {
    // Filtered by either, the list would be empty, and read as good news.
    window.history.replaceState(null, "", "/flags/?side=gone&kind=no_such");
    theShopHas();

    render(<FlagsScreen />);

    await screen.findByText("Juma · Dawa · Jumapili 22/11");
    expect(lastAsked()).toEqual({ state: "waiting" });
    expect(screen.queryByText(/^Umechuja/)).toBeNull();
  });

  it("offers only the sides whose flags the person may close", async () => {
    // flag.review on Dawa alone, though she sells on Vyakula: no other side, and not the whole shop's, so nothing to
    // choose between; the kinds alone.
    window.history.replaceState(null, "", "/flags/?side=shop");
    theShopHas(
      whoIsHere([
        { side: DAWA, permissions: ["flag.review"] },
        { side: VYAKULA, permissions: ["sale.write"] },
      ]),
    );
    render(<FlagsScreen />);

    const sheet = await openTheSheet();

    expect(
      within(sheet).queryByRole("radiogroup", { name: "Upande" }),
    ).toBeNull();
    // "Aina zote" and the six kinds, a late tap's among them (WAGE-10).
    expect(rows(sheet, "Aina").getAllByRole("radio")).toHaveLength(7);
    expect(screen.queryByText(/^Umechuja/)).toBeNull();
  });

  it("offers the whole shop's own to someone of one side who may close them too", async () => {
    theShopHas({
      ...whoIsHere([]),
      permissions: {
        whole_shop: ["flag.review"],
        sides: [{ ...DAWA, permissions: ["flag.review"] }],
      },
    });
    render(<FlagsScreen />);

    const sheet = await openTheSheet();

    const sides = rows(sheet, "Upande");
    expect(sides.getAllByRole("radio")).toHaveLength(3);
    for (const name of ["Pande zote", "Dawa", "Duka zima"])
      expect(sides.getByRole("radio", { name })).toBeTruthy();
  });

  it.each(["waiting", "closed"])(
    "never says that nothing at all is %s, when it is only the filter",
    async (tab) => {
      window.history.replaceState(
        null,
        "",
        `/flags/?kind=device_gap&tab=${tab}`,
      );
      theShopHas(REVIEWER, flagsPage([]));

      render(<FlagsScreen />);

      // In the open tab: the other, hidden, may say the same of its own list.
      expect(
        await within(await screen.findByRole("tabpanel")).findByText(
          "Hakuna tofauti kwa ulichochuja.",
        ),
      ).toBeTruthy();
      expect(screen.queryByText("Hakuna tofauti inayosubiri.")).toBeNull();
      expect(screen.queryByText("Bado hakuna tofauti iliyofungwa.")).toBeNull();
    },
  );

  it("counts what waits under the filter, as its tab lists them", async () => {
    window.history.replaceState(null, "", `/flags/?side=${DAWA.id}`);
    theShopHas(REVIEWER, flagsPage([flagLine()], { waiting: 7 }));

    render(<FlagsScreen />);

    expect(
      await screen.findByRole("tab", { name: "Zinasubiri (7)" }),
    ).toBeTruthy();
  });
});
