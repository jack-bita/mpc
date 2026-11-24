// flags-screen.test.tsx — Tofauti lists what waits and what is closed, each behind its tab, a line per flag in the
// shop's words, that opens its own page (CTRL-4).
import { QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import { setLanguage } from "@/i18n/language";
import { answer, refusal, sent } from "@/test/fake-server";
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

type Page = ReturnType<typeof flagsPage>;

/** The manager is logged in; each tab answers with its page, by the state asked. */
function theShopHas(tabs: { waiting?: Page; closed?: Page }) {
  answer("GET", ME, { status: 200, body: REVIEWER });
  answer("GET", FLAGS_ROUTE, (request) => {
    const state = new URL(request.url).searchParams.get("state");
    return Response.json(
      (state === "closed" ? tabs.closed : tabs.waiting) ?? flagsPage([]),
    );
  });
}

/** The states the page asked the list for, in order. */
function statesAsked(): (string | null)[] {
  return sent
    .map((request) => new URL(request.url))
    .filter((url) => url.pathname === FLAGS_ROUTE)
    .map((url) => url.searchParams.get("state"));
}

async function lines(): Promise<HTMLElement[]> {
  return within(await screen.findByRole("list")).getAllByRole("listitem");
}

describe("the list of flags", () => {
  it("says each flag's kind, who it names, where and the day, and opens its page", async () => {
    const suspended = flagLine();
    theShopHas({
      waiting: flagsPage([
        suspended,
        // Whole shop's, naming two.
        flagLine({
          kind: "unverified_time",
          side: null,
          people: ["Neema", "Asha"],
        }),
        // Naming nobody: the laptop is named in their place.
        flagLine({ kind: "device_gap", people: [] }),
        // About something no laptop made: the day the server found it, and nobody to name.
        flagLine({
          kind: "invalid_document",
          people: [],
          device: null,
          made_at: null,
        }),
      ]),
    });

    render(<FlagsScreen />);

    const [first, second, third, fourth] = await lines();
    const link = within(first!).getByRole("link", {
      name: "Alisimamishwa au aliondoka, lakini alibonyeza Juma · Dawa · Jumapili 22/11",
    });
    // The slash before "?" comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(link.getAttribute("href")).toMatch(
      new RegExp(`^/flags/view/?\\?id=${suspended.id}$`),
    );
    expect(
      within(second!).getByText("Neema na Asha · Duka zima · Jumapili 22/11"),
    ).toBeTruthy();
    expect(within(second!).getByText("Saa yake haiaminiki")).toBeTruthy();
    expect(
      within(third!).getByText("Laptop Dawa · Dawa · Jumapili 22/11"),
    ).toBeTruthy();
    expect(within(fourth!).getByText("Dawa · Jumatatu 23/11")).toBeTruthy();
  });

  it("says the day on the shop's own calendar", async () => {
    // 00:30 on Monday in Arusha, Sunday still in UTC.
    theShopHas({
      waiting: flagsPage([flagLine({ made_at: "2026-11-22T21:30:00Z" })]),
    });

    render(<FlagsScreen />);

    expect(
      await screen.findByText("Juma · Dawa · Jumatatu 23/11"),
    ).toBeTruthy();
  });

  it("marks one explained and still waiting, and never an open one", async () => {
    theShopHas({
      waiting: flagsPage([flagLine({ status: "explained" }), flagLine()]),
    });

    render(<FlagsScreen />);

    const [explained, open] = await lines();
    expect(within(explained!).getByText("Imeelezwa")).toBeTruthy();
    expect(within(open!).queryByText("Inasubiri")).toBeNull();
  });

  it("reads a kind the app has no words for as another flag, never a blank", async () => {
    theShopHas({ waiting: flagsPage([flagLine({ kind: "negative_stock" })]) });

    render(<FlagsScreen />);

    expect(await screen.findByText("Tofauti nyingine")).toBeTruthy();
  });

  it("speaks English to someone who chose it", async () => {
    setLanguage("en");
    theShopHas({ waiting: flagsPage([flagLine()]) });

    render(<FlagsScreen />);

    expect(
      await screen.findByRole("tab", { name: "Waiting (1)" }),
    ).toBeTruthy();
    expect(screen.getByText("Juma · Dawa · Sunday 22/11")).toBeTruthy();
  });
});

describe("its two tabs", () => {
  it("counts what waits by the server's count, not by the lines of a page", async () => {
    theShopHas({ waiting: flagsPage([flagLine()], { waiting: 60 }) });

    render(<FlagsScreen />);

    expect(
      await screen.findByRole("tab", { name: "Zinasubiri (60)" }),
    ).toBeTruthy();
  });

  it("asks for the closed ones once their tab is opened, and keeps it in the address", async () => {
    theShopHas({
      waiting: flagsPage([flagLine()]),
      closed: flagsPage(
        [
          flagLine({ status: "resolved", people: ["Asha"] }),
          flagLine({ status: "dismissed", people: ["Baraka"] }),
        ],
        { waiting: 1 },
      ),
    });
    render(<FlagsScreen />);
    await screen.findByText("Juma · Dawa · Jumapili 22/11");
    expect(statesAsked()).toEqual(["waiting"]);

    fireEvent.click(screen.getByRole("tab", { name: "Zilizofungwa" }));

    const [resolved, dismissed] = await lines();
    expect(within(resolved!).getByText("Imetatuliwa")).toBeTruthy();
    expect(within(dismissed!).getByText("Si tatizo")).toBeTruthy();
    expect(statesAsked()).toEqual(["waiting", "closed"]);
    expect(window.location.search).toBe("?tab=closed");
    // What waits is still counted, whichever tab is open.
    expect(screen.getByRole("tab", { name: "Zinasubiri (1)" })).toBeTruthy();
  });

  it("opens the tab the address names", async () => {
    window.history.replaceState(null, "", "/flags/?tab=closed");
    theShopHas({
      closed: flagsPage([flagLine({ status: "resolved" })], { waiting: 0 }),
    });

    render(<FlagsScreen />);

    expect(await screen.findByText("Imetatuliwa")).toBeTruthy();
    expect(
      screen
        .getByRole("tab", { name: "Zilizofungwa" })
        .getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("says so when nothing waits, and when nothing was closed yet", async () => {
    theShopHas({});
    render(<FlagsScreen />);

    expect(await screen.findByText("Hakuna tofauti inayosubiri.")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Zinasubiri (0)" })).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Zilizofungwa" }));
    expect(
      await screen.findByText("Bado hakuna tofauti iliyofungwa."),
    ).toBeTruthy();
  });
});

describe("Onyesha zaidi", () => {
  it("brings the next page after the first, moves to its first line, and goes at the end", async () => {
    answer("GET", ME, { status: 200, body: REVIEWER });
    answer("GET", FLAGS_ROUTE, (request) => {
      const query = new URL(request.url).searchParams;
      return Response.json(
        query.get("cursor") === "cD0x"
          ? flagsPage([flagLine({ people: ["Baraka"] })], { waiting: 2 })
          : flagsPage([flagLine({ people: ["Asha"] })], {
              waiting: 2,
              next: `http://shop.test${FLAGS_ROUTE}?cursor=cD0x&state=waiting`,
            }),
      );
    });
    render(<FlagsScreen />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Onyesha zaidi" }),
    );

    await screen.findByText("Baraka · Dawa · Jumapili 22/11");
    const [asha, baraka] = await lines();
    expect(within(asha!).getByText(/^Asha/)).toBeTruthy();
    // The button that asked is gone, so the keyboard goes on from the first new line.
    await waitFor(() =>
      expect(document.activeElement).toBe(within(baraka!).getByRole("link")),
    );
    expect(screen.queryByRole("button", { name: "Onyesha zaidi" })).toBeNull();
    // The cursor sent back with the tab's own state.
    const last = new URL(sent.at(-1)!.url).searchParams;
    expect([last.get("cursor"), last.get("state")]).toEqual([
      "cD0x",
      "waiting",
    ]);
  });
});

describe("Onyesha zaidi, refused", () => {
  /** Asha's line, and a second page the server refuses; then what `later` says, for every read after. */
  function theSecondPageIsRefused(later: Page) {
    let refused = false;
    answer("GET", ME, { status: 200, body: REVIEWER });
    answer("GET", FLAGS_ROUTE, (request) => {
      if (new URL(request.url).searchParams.has("cursor")) {
        refused = true;
        return Response.json(refusal(404, "not_found").body, { status: 404 });
      }
      return Response.json(
        refused
          ? later
          : flagsPage([flagLine({ people: ["Asha"] })], {
              waiting: 2,
              next: `http://shop.test${FLAGS_ROUTE}?cursor=cD0x&state=waiting`,
            }),
      );
    });
  }

  it("says why beside its button, under the lines, where the person is", async () => {
    theSecondPageIsRefused(flagsPage([]));
    render(<FlagsScreen />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Onyesha zaidi" }),
    );

    const why = await screen.findByRole("alert");
    // After the list on the page, not above its fifty lines; and the lines stay, with the button to try again.
    expect(
      screen.getByRole("list").compareDocumentPosition(why) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(await lines()).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Onyesha zaidi" })).toBeTruthy();
  });

  it("never moves the keyboard later, when lines come by themselves", async () => {
    theSecondPageIsRefused(
      flagsPage([
        flagLine({ people: ["Baraka"] }),
        flagLine({ people: ["Asha"] }),
      ]),
    );
    const store = makeQueryClient();
    render(
      <QueryClientProvider client={store}>
        <FlagsScreen />
      </QueryClientProvider>,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Onyesha zaidi" }),
    );
    await screen.findByRole("alert");
    const elsewhere = screen.getByRole("button", { name: "Chuja" });
    elsewhere.focus();

    // The window comes back to the front, and the list is read again: one more line than before.
    await act(() => store.invalidateQueries());

    await screen.findByText(/^Baraka/);
    expect(await lines()).toHaveLength(2);
    expect(document.activeElement).toBe(elsewhere);
  });
});

describe("with no list to show", () => {
  it("shows the server's refusal to someone who may close none", async () => {
    answer("GET", ME, { status: 200, body: REVIEWER });
    answer("GET", FLAGS_ROUTE, refusal(403, "permission_denied"));

    render(<FlagsScreen />);

    expect((await screen.findByRole("alert")).textContent).toContain("ruhusa");
    expect(screen.queryByText("Subiri kidogo…")).toBeNull();
    expect(screen.queryByText("Hakuna tofauti inayosubiri.")).toBeNull();
  });

  it("says to log in first, and never waits for a list it can't ask for", async () => {
    answer("GET", ME, refusal(403, "not_authenticated"));

    render(<FlagsScreen />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("Subiri kidogo…")).toBeNull();
    expect(statesAsked()).toEqual([]);
  });

  it("waits in words until the first answer", async () => {
    answer("GET", ME, { status: 200, body: REVIEWER });
    answer("GET", FLAGS_ROUTE, () => new Promise<Response>(() => {}));

    render(<FlagsScreen />);

    expect(await screen.findByText("Subiri kidogo…")).toBeTruthy();
    expect(await screen.findByRole("tab", { name: "Zinasubiri" })).toBeTruthy();
  });
});
