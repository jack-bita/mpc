// at-the-device.test.tsx — leaving a shared laptop: Toka and Badilisha mtu end the session on the server,
// forget the person, and show the tiles for whoever is next (UI-4, 03 §5.9). The fake server keeps one
// session, as Django does for this browser: a PIN login starts it, a logout ends it, and `me` answers for it.
import { onlineManager, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import type { components } from "@/api/schema";
import { saveDevice } from "@/features/devices/this-device";
import { WHO_IS_HERE } from "@/features/people/who-is-here";
import { setLanguage } from "@/i18n/language";
import {
  DAWA,
  DAWA_LAPTOP,
  DAWA_LAPTOP_ANSWER,
  whoIsHere,
} from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { swahiliIn } from "@/test/language";
import { staffRow, theLaptopKnows } from "@/test/laptop";
import { FEW_TURNS } from "@/test/pins";
import { render } from "@/test/render";
import { DAWA_SIDE, IDLE_15, IDLE_RULE } from "@/test/shop-lists";

import { rememberPin } from "@/offline/pin";
import { shopDatabase } from "@/offline/this-shop";

import {
  arriveAtCounter,
  askToLeave,
  useAtTheCounter,
  useLeaveAsked,
  usePersonAtCounter,
} from "./at-the-counter";
import { AtTheDevice } from "./at-the-device";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const PIN_LOGIN = "/api/auth/pin-login/";
const LOGOUT = "/api/auth/logout/";

type WhoIsHere = components["schemas"]["WhoIsHere"];

// What `me` answers for each of the laptop's two people, logged in by PIN there. Fake people.
const NEEMA: WhoIsHere = {
  ...whoIsHere([{ side: DAWA, permissions: ["sale.make"] }]),
  device: DAWA_LAPTOP_ANSWER.device,
  home_side: DAWA_LAPTOP_ANSWER.home_side,
  idle_minutes: 15,
};
const JUMA: WhoIsHere = {
  ...NEEMA,
  user: {
    id: "019a5e00-0000-7000-8000-0000000000b2",
    full_name: "Juma Mfano",
    language: "sw",
    font: "default",
  },
  staff: {
    id: "019a5e00-0000-7000-8000-0000000000c3",
    display_name: "Juma",
    job_title: "Muuzaji",
  },
};

/** A person's row on the laptop's own copy of the staff, from what `me` answers for them. */
const rowOf = (person: WhoIsHere) =>
  staffRow(person.staff.id, person.user.full_name, person.staff.display_name);

// Both people are on the laptop's own copy of the staff, which the tiles read (SYNC-10).
beforeEach(() => theLaptopKnows(rowOf(NEEMA), rowOf(JUMA)));

/** The Dawa laptop with `first` logged in. Logout answers as `logout` says; by default, as Django does.
 * A test's own logout calls the `end` it gives back, as Django ends the session. */
function theLaptop(
  first: WhoIsHere | null,
  logout?: Parameters<typeof answer>[2],
) {
  saveDevice(DAWA_LAPTOP);
  let here = first;
  const nobody = refusal(403, "not_authenticated");
  answer("GET", ME, () =>
    here
      ? Response.json(here)
      : Response.json(nobody.body, { status: nobody.status }),
  );
  answer("POST", PIN_LOGIN, async (request) => {
    const { staff } = (await request.json()) as { staff: string };
    here = [NEEMA, JUMA].find((person) => person.staff.id === staff) ?? null;
    return new Response(null, { status: 204 });
  });
  const end = () => {
    here = null;
  };
  answer(
    "POST",
    LOGOUT,
    logout ??
      (() => {
        end();
        return new Response(null, { status: 204 });
      }),
  );
  return { end };
}

/** A fake clock for the idle lock: its timers and the time, and nothing else. shouldAdvanceTime: it still
 * moves on its own, so the fake server's answers arrive. The test database (fake-indexeddb) runs on
 * setImmediate, which must stay real, or its transactions end early and the tiles never read (SYNC-10). */
const IDLE_CLOCK: Parameters<typeof vi.useFakeTimers>[0] = {
  shouldAdvanceTime: true,
  toFake: [
    "setTimeout",
    "setInterval",
    "clearTimeout",
    "clearInterval",
    "Date",
  ],
};

const bar = () => within(screen.getByRole("banner"));
const logouts = () =>
  sent.filter((request) => new URL(request.url).pathname === LOGOUT);

describe("leaving the laptop", () => {
  it("Toka ends the session on the server, and asks who is next", async () => {
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    expect(logouts()).toHaveLength(1);
    expect(bar().queryByText("Neema")).toBeNull();
  });

  it("moves the keyboard to the welcome, and back to the question after Toka", async () => {
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { level: 1, name: "Karibu, Neema" }),
    );

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    await screen.findByRole("heading", { name: "Wewe ni nani?" });
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    );
  });

  it("Badilisha mtu lets Juma log in after Neema, and he sees only his own", async () => {
    // The quick switch: Juma steps up to the counter while Neema is still logged in.
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    fireEvent.click(bar().getByRole("button", { name: "Badilisha mtu" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    );
    for (const digit of "4829")
      fireEvent.click(screen.getByRole("button", { name: digit }));

    expect(
      await screen.findByRole("heading", { name: "Karibu, Juma" }),
    ).toBeDefined();
    expect(bar().getByText("Juma")).toBeDefined();
    expect(screen.queryByText("Neema")).toBeNull();
    // Her session ended before his began: the server never held both for this browser.
    expect(logouts()).toHaveLength(1);
  });

  it("hides the person at once, before the server has heard", async () => {
    // A slow 3G answer: the next person at the counter must not see Neema meanwhile.
    theLaptop(NEEMA, () => new Promise<Response>(() => {}));
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    await vi.waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "Karibu, Neema" }),
      ).toBeNull(),
    );
    expect(bar().queryByText("Neema")).toBeNull();
    // Not the tiles yet: Juma's login, sent while her logout is still on its way, could be ended by it.
    expect(screen.getByText("Unatoka…")).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Wewe ni nani?" })).toBeNull();
  });

  it("says it is leaving in a status line that was on the page already", async () => {
    // A status line that comes with its words in it often goes unsaid (NVDA, JAWS): it must be there, empty,
    // before its words arrive, as the offline banner's is.
    theLaptop(NEEMA, () => new Promise<Response>(() => {}));
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });
    const lines = screen.getAllByRole("status");

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    expect(lines).toContain(await screen.findByText("Unatoka…"));
  });

  it("sends the logout again when no answer came, until the server hears it", async () => {
    // The network dropped as she pressed Toka. Left there, her session would outlive the press: when the
    // network came back before its idle time, `me` would bring her back on the screen.
    let tries = 0;
    const laptop = theLaptop(NEEMA, () => {
      tries += 1;
      if (tries === 1) throw new TypeError("Failed to fetch");
      laptop.end();
      return new Response(null, { status: 204 });
    });
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    // The tiles come back already while it waits: the first try got no answer, so the next person logs in
    // on the laptop's own check meanwhile (SYNC-10).
    expect(
      await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    // TanStack waits a second before the next try, which the server hears.
    await vi.waitFor(() => expect(tries).toBe(2), { timeout: 3000 });
    // Gone as the person here: neither in the bar nor welcomed. Her tile is there, as everyone's is.
    expect(bar().queryByText("Neema")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Karibu, Neema" })).toBeNull();
  });

  it("says why a refused logout failed, and leaves the person where they are", async () => {
    theLaptop(NEEMA, refusal(403, "permission_denied"));
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    expect(
      await screen.findByText("Huna ruhusa ya kufanya hili."),
    ).toBeDefined();
    expect(
      screen.getByRole("heading", { name: "Karibu, Neema" }),
    ).toBeDefined();
    // Asked once: a refusal the server meant gets the same no again.
    expect(logouts()).toHaveLength(1);
  });

  it("logs the person out by itself after the idle minutes untouched", async () => {
    // Neema walks away from the counter. Her `me` says 15 minutes (AUTH-4's setting, UI-4's step 2).
    // shouldAdvanceTime: the fake clock still moves on its own, so the fake server's answers arrive.
    vi.useFakeTimers(IDLE_CLOCK);
    try {
      theLaptop(NEEMA);
      render(<AtTheDevice device={DAWA_LAPTOP} />);
      await screen.findByRole("heading", { name: "Karibu, Neema" });

      await vi.advanceTimersByTimeAsync(15 * 60 * 1000 + 10 * 1000);

      expect(
        await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
      ).toBeDefined();
      expect(logouts()).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows a refused logout's reason only to the person who pressed", async () => {
    // Neema's Toka is refused. Her session later ends at its idle time, and Juma logs in: the reason was
    // hers, and must not greet him.
    const laptop = theLaptop(NEEMA, refusal(403, "permission_denied"));
    const store = makeQueryClient();
    render(
      <QueryClientProvider client={store}>
        <AtTheDevice device={DAWA_LAPTOP} />
      </QueryClientProvider>,
    );
    await screen.findByRole("heading", { name: "Karibu, Neema" });
    fireEvent.click(bar().getByRole("button", { name: "Toka" }));
    await screen.findByText("Huna ruhusa ya kufanya hili.");

    laptop.end();
    await act(() => store.refetchQueries({ queryKey: WHO_IS_HERE }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    );
    for (const digit of "4829")
      fireEvent.click(screen.getByRole("button", { name: digit }));

    expect(
      await screen.findByRole("heading", { name: "Karibu, Juma" }),
    ).toBeDefined();
    expect(screen.queryByText("Huna ruhusa ya kufanya hili.")).toBeNull();
  });

  it("logs out a password's session on the shared laptop after the idle minutes too", async () => {
    // A manager logged in with a password at the Dawa laptop, as UI-3's hand test did through the Console:
    // `me` names no device for a password (ADR-0038), but the laptop is shared, and locks the same.
    const manager: WhoIsHere = { ...NEEMA, device: null, home_side: null };
    vi.useFakeTimers(IDLE_CLOCK);
    try {
      theLaptop(manager);
      render(<AtTheDevice device={DAWA_LAPTOP} />);
      await screen.findByRole("heading", { name: "Karibu, Neema" });

      await vi.advanceTimersByTimeAsync(15 * 60 * 1000 + 10 * 1000);

      expect(
        await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
      ).toBeDefined();
      expect(logouts()).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("says to wait while it asks who is here, in both languages", async () => {
    // A slow 3G answer, as the app opens and after each login: a blank screen would look broken.
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, () => new Promise<Response>(() => {}));
    const { unmount } = render(<AtTheDevice device={DAWA_LAPTOP} />);

    expect(screen.getByText("Subiri kidogo…")).toBeDefined();
    unmount();
    setLanguage("en");
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    expect(screen.getByText("One moment…")).toBeDefined();
  });

  it("shows neither button while nobody is logged in", async () => {
    theLaptop(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Wewe ni nani?" });

    expect(bar().queryByRole("button", { name: "Toka" })).toBeNull();
    expect(bar().queryByRole("button", { name: "Badilisha mtu" })).toBeNull();
  });

  it("speaks English to someone who reads it, with no Swahili left", async () => {
    // Her own language, saved on her: since UI-9 it decides once she is in, not the laptop's switch.
    theLaptop({ ...NEEMA, user: { ...NEEMA.user, language: "en" } });
    const { container } = render(<AtTheDevice device={DAWA_LAPTOP} />);

    expect(
      await screen.findByRole("heading", { name: "Welcome, Neema" }),
    ).toBeDefined();
    expect(bar().getByRole("button", { name: "Switch person" })).toBeDefined();
    expect(bar().getByRole("button", { name: "Log out" })).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});

describe("a session the server ends", () => {
  it("says why once, ends that session on the server, and tells nobody after", async () => {
    // Neema was suspended while logged in: `me` refuses her session with the reason (AUTH-4). The server
    // keeps refusing it, with the same reason, until it is ended, and the next person at the counter
    // must not be told she was suspended.
    saveDevice(DAWA_LAPTOP);
    let ended = false;
    const suspended = refusal(403, "staff.suspended");
    const nobody = refusal(403, "not_authenticated");
    answer("GET", ME, () => {
      const why = ended ? nobody : suspended;
      return Response.json(why.body, { status: why.status });
    });
    answer("POST", LOGOUT, () => {
      ended = true;
      return new Response(null, { status: 204 });
    });
    render(<AtTheDevice device={DAWA_LAPTOP} />);

    const why = "Umesimamishwa. Ongea na meneja au mmiliki.";
    expect(await screen.findByText(why)).toBeDefined();
    expect(
      screen.getByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    expect(logouts()).toHaveLength(1);
    // Juma taps his tile, then Rudi: the reason was for her, and is gone. The tiles come a moment after
    // the question, from the laptop's copy.
    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Rudi" }));
    expect(
      screen.getByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    // TanStack tells the screen of the forgetting at its next turn, not in the same moment.
    await vi.waitFor(() => expect(screen.queryByText(why)).toBeNull());
    expect(logouts()).toHaveLength(1);
  });

  it("stays ended through a failed refresh after it", async () => {
    // Neema's session ends on the server by itself, at its idle time, and the next refresh of `me` meets
    // a deploy's 502. TanStack keeps her last answer beside that error: read again, it would put her back
    // in the bar, with Toka and an idle lock armed for another 15 minutes.
    saveDevice(DAWA_LAPTOP);
    let server: "her" | "nobody" | "broken" = "her";
    const nobody = refusal(403, "not_authenticated");
    const broken = refusal(502, "server_error");
    answer("GET", ME, () =>
      server === "her"
        ? Response.json(NEEMA)
        : server === "nobody"
          ? Response.json(nobody.body, { status: nobody.status })
          : Response.json(broken.body, { status: broken.status }),
    );
    const store = makeQueryClient();
    // A 502 isn't asked again here: the store's own rule would ask twice more, a second and two apart.
    store.setDefaultOptions({ queries: { retry: false } });
    render(
      <QueryClientProvider client={store}>
        <AtTheDevice device={DAWA_LAPTOP} />
      </QueryClientProvider>,
    );
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    server = "nobody";
    await act(() => store.refetchQueries({ queryKey: WHO_IS_HERE }));
    await screen.findByRole("heading", { name: "Wewe ni nani?" });
    server = "broken";
    await act(() => store.refetchQueries({ queryKey: WHO_IS_HERE }));

    expect(
      await screen.findByText("Seva ina hitilafu. Jaribu tena baadaye."),
    ).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Karibu, Neema" })).toBeNull();
    expect(bar().queryByText("Neema")).toBeNull();
    expect(bar().queryByRole("button", { name: "Toka" })).toBeNull();
  });
});

describe("the way in by password", () => {
  it("offers it under the tiles, for someone with a password and no PIN", async () => {
    // Baba, the owner, has a password and no PIN: at the shop laptop he would see only the tiles (Jack,
    // 8 Nov 2026, at UI-5's review).
    theLaptop(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Wewe ni nani?" });

    const link = screen.getByRole("link", { name: "Ingia kwa nenosiri" });
    // The end slash comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(link.getAttribute("href")).toMatch(/^\/login\/?$/);
  });

  it("isn't there while someone is logged in", async () => {
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    expect(
      screen.queryByRole("link", { name: "Ingia kwa nenosiri" }),
    ).toBeNull();
  });
});

describe("Mipangilio yangu", () => {
  it("is offered to the person at the laptop, under the welcome", async () => {
    // Neema logs in by PIN here and never sees the office's home page: her own language and font are
    // one tap from her welcome (UI-9).
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    const link = screen.getByRole("link", { name: "Mipangilio yangu" });
    // The end slash comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(link.getAttribute("href")).toMatch(/^\/my-settings\/?$/);
  });

  it("isn't there while nobody is logged in: the tiles have no one's settings", async () => {
    theLaptop(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Wewe ni nani?" });

    expect(screen.queryByRole("link", { name: "Mipangilio yangu" })).toBeNull();
  });
});

describe("each person's own language and font", () => {
  // Neema saved English and the second font in Mipangilio yangu; Juma keeps Swahili and the default one.
  const NEEMA_IN_ENGLISH: WhoIsHere = {
    ...NEEMA,
    user: { ...NEEMA.user, language: "en", font: "second" },
  };
  const page = document.documentElement;

  it("applies her choices as she logs in, wherever she logs in", async () => {
    // Saved on her, not on this laptop: any device that asks `me` after her login shows them (UI-9).
    theLaptop(NEEMA_IN_ENGLISH);
    render(<AtTheDevice device={DAWA_LAPTOP} />);

    expect(
      await screen.findByRole("heading", { name: "Welcome, Neema" }),
    ).toBeTruthy();
    expect(page.lang).toBe("en");
    expect(page.dataset.font).toBe("second");
  });

  it("juma logs in after her on the same laptop and sees his own choices", async () => {
    // The card's own case: the quick switch hands the laptop from her to him, and nothing of hers stays.
    // The laptop's own language is English, switched from the bar, and Juma reads Swahili: so his welcome
    // in Swahili is his own choice at work, not the laptop's (UI-9's review).
    setLanguage("en");
    theLaptop(NEEMA_IN_ENGLISH);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Welcome, Neema" });

    fireEvent.click(bar().getByRole("button", { name: "Switch person" }));
    // The tiles, in the laptop's own language and font: they are for whoever is next.
    expect(
      await screen.findByRole("heading", { name: "Who are you?" }),
    ).toBeTruthy();
    expect(page.dataset.font).toBeUndefined();
    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    );
    for (const digit of "4829")
      fireEvent.click(screen.getByRole("button", { name: digit }));

    expect(
      await screen.findByRole("heading", { name: "Karibu, Juma" }),
    ).toBeTruthy();
    expect(page.lang).toBe("sw");
    expect(page.dataset.font).toBe("default");
  });

  it("shows the bar's language button only while nobody is logged in", async () => {
    // Jack's choice (UI-9): the button switches the laptop's own language, for the tiles; once someone
    // is in, their language is changed in Mipangilio yangu, the one place for it.
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });
    expect(bar().queryByRole("button", { name: "English" })).toBeNull();

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    await screen.findByRole("heading", { name: "Wewe ni nani?" });
    expect(bar().getByRole("button", { name: "English" })).toBeTruthy();
  });
});

describe("with no network (SYNC-10)", () => {
  const db = () => shopDatabase(DAWA_LAPTOP.shop.id);

  // Every test here on the fake clock, which still moves on its own. A test that ends with its network
  // gone leaves a logout trying again with no end; its next try sleeps on this clock, and the sleep is
  // thrown away with the clock as the test ends. Left on the real one, it would wake in a later test and
  // reach that test's server, and could make it pass, or fail, for the wrong reason.
  beforeEach(() => {
    vi.useFakeTimers(IDLE_CLOCK);
  });
  afterEach(() => {
    vi.useRealTimers();
    // The browser's network back on, for the next test, if this one switched it off.
    onlineManager.setOnline(true);
    vi.restoreAllMocks();
  });

  /** The browser itself says there is no network: navigator.onLine false, and TanStack told so, as its
   * own watch of the browser's "offline" event would tell it. Reads and changes wait (paused), and none is
   * sent. */
  function theBrowserIsOffline() {
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
    onlineManager.setOnline(false);
  }
  // Juma on the laptop's copy, as the sync left him: a seller on Dawa, with a PIN set.
  const JUMA_ROW = {
    ...staffRow(JUMA.staff.id, JUMA.user.full_name, JUMA.staff.display_name),
    permissions: {
      every_side: [],
      sides: [{ side: DAWA.id, permissions: ["sale.make"] }],
    },
  };

  /**
   * The Dawa laptop, its network gone, with `first`'s session from before still in its cookie: while the
   * network is gone, every call gets no answer. Juma logged in here online once, with 4829, so the laptop
   * holds its check of his PIN.
   */
  async function aLaptopWithNoNetwork(first: WhoIsHere | null) {
    saveDevice(DAWA_LAPTOP);
    await db().staff.put(JUMA_ROW);
    await db().side.put(DAWA_SIDE);
    await rememberPin(db(), JUMA.staff.id, "4829", FEW_TURNS);
    // `logoutsHeard`: the logouts that reached the server.
    const laptop = { network: false, here: first, logoutsHeard: 0 };
    const nobody = refusal(403, "not_authenticated");
    const noAnswer = () => {
      throw new TypeError("Failed to fetch");
    };
    answer("GET", ME, () => {
      if (!laptop.network) noAnswer();
      return laptop.here
        ? Response.json(laptop.here)
        : Response.json(nobody.body, { status: nobody.status });
    });
    answer("POST", LOGOUT, () => {
      if (!laptop.network) noAnswer();
      laptop.logoutsHeard += 1;
      laptop.here = null;
      return new Response(null, { status: 204 });
    });
    answer("POST", PIN_LOGIN, async (request) => {
      if (!laptop.network) noAnswer();
      const { staff } = (await request.json()) as { staff: string };
      laptop.here =
        [NEEMA, JUMA].find((person) => person.staff.id === staff) ?? null;
      return new Response(null, { status: 204 });
    });
    return laptop;
  }

  /** Juma taps his tile and types his PIN, and the laptop lets him in. */
  async function jumaLogsInHere() {
    // Up to 3 s, not Testing Library's 1: the tiles, the check and the welcome each read the database,
    // which a full run, many files at once, can slow down.
    const wait = { timeout: 3000 };
    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }, wait),
    );
    for (const digit of "4829")
      fireEvent.click(screen.getByRole("button", { name: digit }));
    await screen.findByRole("heading", { name: "Karibu, Juma" }, wait);
  }

  const pinLogins = () =>
    sent.filter((request) => new URL(request.url).pathname === PIN_LOGIN);

  it("shows the tiles after a reload, and lets Juma in on the laptop's own check", async () => {
    await aLaptopWithNoNetwork(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);

    await jumaLogsInHere();

    // In the bar, with the side he works on, from his staff row and the laptop's sides.
    expect(bar().getByText("Juma")).toBeDefined();
    expect(bar().getByText("MPC · Dawa")).toBeDefined();
    // Never sent: the laptop checked it.
    expect(pinLogins()).toEqual([]);
  });

  it("brings the tiles back at once after Toka, and lets the next person in", async () => {
    // Neema logged in online; then the network went. Her Toka can't reach the server, and the counter
    // can't wait all day for it.
    const laptop = await aLaptopWithNoNetwork(NEEMA);
    laptop.network = true;
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });
    laptop.network = false;

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));
    await jumaLogsInHere();

    expect(bar().queryByText("Neema")).toBeNull();
    expect(pinLogins()).toEqual([]);
  });

  it("shows the tiles at once on a reload the browser knows is offline, and sends nothing", async () => {
    // `me` isn't even tried (TanStack waits for the network), so no failure comes to wait for.
    await aLaptopWithNoNetwork(null);
    theBrowserIsOffline();
    render(<AtTheDevice device={DAWA_LAPTOP} />);

    await jumaLogsInHere();

    // Nothing reached the server: not `me`, not his PIN, and the logout sent at his arrival waits.
    expect(sent).toEqual([]);
    // No "Subiri kidogo…" for an answer that can't come.
    expect(screen.queryByText("Subiri kidogo…")).toBeNull();
  });

  it("brings the tiles back after Toka while the browser knows it is offline, and sends the logout once it is back", async () => {
    const laptop = await aLaptopWithNoNetwork(NEEMA);
    laptop.network = true;
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });
    theBrowserIsOffline();

    // Her logout waits, paused, never tried: the tiles come back all the same.
    fireEvent.click(bar().getByRole("button", { name: "Toka" }));
    await jumaLogsInHere();
    expect(laptop.logoutsHeard).toBe(0);

    // The network is back: the browser says so, and the logout goes, once.
    vi.restoreAllMocks();
    onlineManager.setOnline(true);
    await vi.waitFor(() => expect(laptop.logoutsHeard).toBe(1));
    expect(screen.getByRole("heading", { name: "Karibu, Juma" })).toBeDefined();
  });

  it("ends a local session with Toka, back to the tiles", async () => {
    await aLaptopWithNoNetwork(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await jumaLogsInHere();

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    expect(bar().queryByText("Juma")).toBeNull();
  });

  it("ends the session from before once the network is back, so it never comes back", async () => {
    // A reload with no network, Neema's session still in the cookie. Juma logs in on the laptop. Once the
    // network is back, the logout sent at his arrival ends hers: after his Toka, nobody is here, not her.
    const laptop = await aLaptopWithNoNetwork(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await jumaLogsInHere();

    laptop.network = true;
    // TanStack waits a second, then two, between the logout's tries.
    await vi.waitFor(() => expect(laptop.here).toBeNull(), { timeout: 5000 });
    expect(screen.getByRole("heading", { name: "Karibu, Juma" })).toBeDefined();

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Karibu, Neema" })).toBeNull();
  });

  it("never lets a logout from before end the next person's online login", async () => {
    // SYNC-10's review. Neema's Toka gets no answer; Juma logs in on the laptop; the internet comes back;
    // Juma leaves; Neema logs in online. Her old logout must have gone once, in its turn, and never wake
    // up later to end her new session.
    const laptop = await aLaptopWithNoNetwork(NEEMA);
    laptop.network = true;
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });
    laptop.network = false;
    fireEvent.click(bar().getByRole("button", { name: "Toka" }));
    await jumaLogsInHere();

    // The internet is back: the logout waiting since her Toka lands at its next try.
    laptop.network = true;
    await vi.waitFor(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
      expect(laptop.logoutsHeard).toBe(1);
    });
    fireEvent.click(bar().getByRole("button", { name: "Toka" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Neema Mfano Neema" }),
    );
    for (const digit of "3690")
      fireEvent.click(screen.getByRole("button", { name: digit }));
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    // Longer than the longest wait between a logout's tries (30 s).
    await vi.advanceTimersByTimeAsync(31_000);

    expect(
      screen.getByRole("heading", { name: "Karibu, Neema" }),
    ).toBeDefined();
    expect(laptop.logoutsHeard).toBe(1);
    expect(laptop.here).toBe(NEEMA);
  });

  it("logs a local session out after the shop's idle minutes untouched", async () => {
    // No `me` to say the minutes: the shop's rule on the laptop, 15.
    await aLaptopWithNoNetwork(null);
    await db().setting.put(IDLE_15);
    await db().setting_keys.put(IDLE_RULE);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await jumaLogsInHere();

    await vi.advanceTimersByTimeAsync(15 * 60 * 1000 + 10 * 1000);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    // 15 s, not Vitest's 5: fifteen minutes of the clock run about 90 of the lock's checks and the waiting
    // logout's tries, which a full run can slow past 5 s.
  }, 15_000);

  it("shows him in his own language and font, from his staff row", async () => {
    await aLaptopWithNoNetwork(null);
    await db().staff.put({ ...JUMA_ROW, language: "en", font: "second" });
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    );
    for (const digit of "4829")
      fireEvent.click(screen.getByRole("button", { name: digit }));

    expect(
      await screen.findByRole("heading", { name: "Welcome, Juma" }),
    ).toBeDefined();
    expect(document.documentElement.dataset.font).toBe("second");
  });

  it("ends his session once a sync says he is suspended", async () => {
    await aLaptopWithNoNetwork(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await jumaLogsInHere();

    // What a pull writes when the network comes and goes (X2).
    await act(() => db().staff.put({ ...JUMA_ROW, status: "suspended" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Karibu, Juma" })).toBeNull();
  });

  it("offers no Mipangilio yangu in a local session: that screen needs the server", async () => {
    await aLaptopWithNoNetwork(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await jumaLogsInHere();

    expect(screen.queryByRole("link", { name: "Mipangilio yangu" })).toBeNull();
  });

  it("tells the counter who the laptop let in, with the shop's idle minutes (SYNC-11)", async () => {
    // No `me` to say the minutes: the shop's rule on the laptop, 15, goes with him to the counter.
    await aLaptopWithNoNetwork(null);
    await db().setting.put(IDLE_15);
    await db().setting_keys.put(IDLE_RULE);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await jumaLogsInHere();

    const { result } = renderHook(() => usePersonAtCounter());
    await waitFor(() => expect(result.current?.row.id).toBe(JUMA.staff.id));
    expect(result.current?.idleMinutes).toBe(15);
  });

  it("offers Mahudhurio in a local session too: the counter needs no server (SYNC-11)", async () => {
    await aLaptopWithNoNetwork(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await jumaLogsInHere();

    expect(
      await screen.findByRole("link", { name: "Mahudhurio" }),
    ).toBeDefined();
  });

  it("sends the logout of a counter's Toka with no answer about her at all, so she never comes back (SYNC-11)", async () => {
    // Neema came in by the server, then stayed over 5 minutes on a counter screen: the store forgot `me`'s
    // answer about her (TanStack's gcTime), and the network is gone. Her Toka there must still end her
    // session, or the network's return would bring her welcome back for anyone to use.
    const laptop = await aLaptopWithNoNetwork(NEEMA);
    arriveAtCounter(rowOf(NEEMA), 15, "server");
    askToLeave();
    render(<AtTheDevice device={DAWA_LAPTOP} />);

    // The tiles for the next person, at once: her logout waits for the network.
    expect(
      await screen.findByRole(
        "heading",
        { level: 1, name: "Wewe ni nani?" },
        { timeout: 3000 },
      ),
    ).toBeDefined();
    expect(laptop.logoutsHeard).toBe(0);

    // The network comes back, and the store asks `me` again as it does then.
    laptop.network = true;
    act(() => {
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });

    await vi.waitFor(() => expect(laptop.logoutsHeard).toBe(1), {
      timeout: 8000,
    });
    expect(laptop.here).toBeNull();
    expect(screen.queryByRole("heading", { name: "Karibu, Neema" })).toBeNull();
    expect(bar().queryByText("Neema")).toBeNull();
  }, 15_000);

  it("ends a local session when a counter screen says he is leaving (SYNC-11)", async () => {
    await aLaptopWithNoNetwork(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await jumaLogsInHere();
    const note = renderHook(() => useAtTheCounter());
    await waitFor(() =>
      expect(note.result.current?.staffId).toBe(JUMA.staff.id),
    );

    act(() => askToLeave());

    expect(
      await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    expect(bar().queryByText("Juma")).toBeNull();
  });
});

describe("the way to Mahudhurio (SYNC-11)", () => {
  const mahudhurio = () => screen.queryByRole("link", { name: "Mahudhurio" });

  it("is on her welcome, and opens the counter's screen", async () => {
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    await waitFor(() => expect(mahudhurio()).not.toBeNull());
    // The slash at the end is the build's (trailingSlash, next.config.ts), which a test's Next leaves off.
    expect(mahudhurio()?.getAttribute("href")).toMatch(/^\/attendance\/?$/);
  });

  it("isn't there while nobody is logged in", async () => {
    theLaptop(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);

    await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" });
    expect(mahudhurio()).toBeNull();
  });

  it("isn't offered to someone the laptop has no row of: the counter could not name them", async () => {
    // A laptop paired a moment ago, before its first sync, with a password's login on it.
    await shopDatabase(DAWA_LAPTOP.shop.id).staff.clear();
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);

    await screen.findByRole("heading", { name: "Karibu, Neema" });
    expect(mahudhurio()).toBeNull();
  });
});

describe("the way to Kompyuta hii (SYNC-12)", () => {
  const kompyutaHii = () =>
    screen.queryByRole("link", { name: "Kompyuta hii" });

  it("is on her welcome, and opens the counter's screen", async () => {
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    await waitFor(() => expect(kompyutaHii()).not.toBeNull());
    expect(kompyutaHii()?.getAttribute("href")).toMatch(/^\/this-laptop\/?$/);
  });

  it("isn't there while nobody is logged in", async () => {
    theLaptop(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);

    await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" });
    expect(kompyutaHii()).toBeNull();
  });
});

describe("records not sent yet, at Toka (SYNC-12)", () => {
  /** Puts `count` clock-ins in the laptop's outbox, waiting to be sent. */
  async function waitingOnTheLaptop(count: number) {
    await shopDatabase(DAWA_LAPTOP.shop.id).outbox.bulkAdd(
      Array.from({ length: count }, (_, i) => ({
        id: `019a5e00-0000-7000-8000-00000000f0${i}0`,
        type: "attendance.clock",
        device_seq: 60 + i,
        status: "waiting" as const,
        attempts: 0,
        last_error: null,
      })),
    );
  }

  it("lets her log out, says how many wait and that they are safe, and keeps every one", async () => {
    // Neema clocked in three times offline; the internet is still out as she leaves (Jack's choice A).
    await waitingOnTheLaptop(3);
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    // No stop: the tiles are back, as after any Toka, with the note above them.
    await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" });
    expect(
      await screen.findByText(
        "Kumbukumbu 3 bado hazijatumwa. Ziko salama kwenye kompyuta hii, na zitatumwa zenyewe.",
      ),
    ).toBeDefined();
    // Logging out took nothing from the outbox: the laptop sends them, whoever is logged in.
    expect(await shopDatabase(DAWA_LAPTOP.shop.id).outbox.count()).toBe(3);
  });

  it("goes by itself once the push has sent them", async () => {
    await waitingOnTheLaptop(1);
    theLaptop(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    const note = await screen.findByText(
      "Kumbukumbu 1 bado haijatumwa. Iko salama kwenye kompyuta hii, na itatumwa yenyewe.",
    );

    // The push's accepted answer takes the row out of the outbox (push.ts).
    await shopDatabase(DAWA_LAPTOP.shop.id).outbox.clear();
    await waitFor(() => expect(note.isConnected).toBe(false));
  });
});

describe("what the counter knows (SYNC-11)", () => {
  // A counter screen never asks the server who is here (rule 5), so the home page, which may, keeps a
  // note for it (at-the-counter.ts), and hears a counter screen say "this person is leaving".
  const leaveAsked = () =>
    renderHook(() => useLeaveAsked()).result.current?.staffId ?? null;

  it("names whoever is logged in, with the minutes her screen may sit untouched", async () => {
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });

    const { result } = renderHook(() => usePersonAtCounter());
    await waitFor(() => expect(result.current?.row.id).toBe(NEEMA.staff.id));
    expect(result.current?.idleMinutes).toBe(15);
  });

  it("names nobody once she has pressed Toka", async () => {
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });
    const { result } = renderHook(() => useAtTheCounter());
    await waitFor(() => expect(result.current?.staffId).toBe(NEEMA.staff.id));

    fireEvent.click(bar().getByRole("button", { name: "Toka" }));

    await waitFor(() => expect(result.current).toBeNull());
  });

  it("logs her out on the server when a counter screen says she is leaving", async () => {
    theLaptop(NEEMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });
    const note = renderHook(() => useAtTheCounter());
    await waitFor(() =>
      expect(note.result.current?.staffId).toBe(NEEMA.staff.id),
    );

    act(() => askToLeave());

    expect(
      await screen.findByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    expect(logouts()).toHaveLength(1);
    // Heard: the same ask must not end her next login too.
    expect(leaveAsked()).toBeNull();
  });

  it("says why when the server refuses a counter's logout, and keeps her where she is", async () => {
    // As Toka here does: a refusal the server meant is shown to her, never a blank page with no tiles.
    theLaptop(NEEMA, refusal(403, "permission_denied"));
    render(<AtTheDevice device={DAWA_LAPTOP} />);
    await screen.findByRole("heading", { name: "Karibu, Neema" });
    const note = renderHook(() => useAtTheCounter());
    await waitFor(() =>
      expect(note.result.current?.staffId).toBe(NEEMA.staff.id),
    );

    act(() => askToLeave());

    expect(
      await screen.findByText("Huna ruhusa ya kufanya hili."),
    ).toBeDefined();
    expect(
      screen.getByRole("heading", { name: "Karibu, Neema" }),
    ).toBeDefined();
    expect(leaveAsked()).toBeNull();
    // Asked once: a refusal the server meant gets the same no again.
    expect(logouts()).toHaveLength(1);
  });

  it("never shows her welcome on the way out, when the home page opens after the counter asked", async () => {
    // The real order: Toka on a counter screen, then the home page opens, with her `me` still in the
    // store. The logout's answer never comes here, so the page stays as its first drawing left it.
    theLaptop(NEEMA, () => new Promise<Response>(() => {}));
    const store = makeQueryClient();
    store.setQueryData(WHO_IS_HERE, NEEMA);
    arriveAtCounter(rowOf(NEEMA), 15, "server");
    askToLeave();

    render(
      <QueryClientProvider client={store}>
        <AtTheDevice device={DAWA_LAPTOP} />
      </QueryClientProvider>,
    );

    // Not for a moment: the next person is already standing at the counter.
    expect(screen.queryByRole("heading", { name: "Karibu, Neema" })).toBeNull();
    expect(bar().queryByText("Neema")).toBeNull();
    expect(await screen.findByText("Unatoka…")).toBeDefined();
    await vi.waitFor(() => expect(logouts()).toHaveLength(1));
  });

  it("logs nobody out when the one who asked to leave is no longer here", async () => {
    // Neema's ask found nobody to hear it, as her session had ended by itself. Juma is here now.
    arriveAtCounter(rowOf(NEEMA), 15, "server");
    askToLeave();
    theLaptop(JUMA);
    render(<AtTheDevice device={DAWA_LAPTOP} />);

    await screen.findByRole("heading", { name: "Karibu, Juma" });
    await waitFor(() => expect(leaveAsked()).toBeNull());
    expect(logouts()).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "Karibu, Juma" })).toBeDefined();
  });

  it("forgets a leave nobody heard, so her next login isn't ended by it", async () => {
    // Her session had ended by itself before the home page opened: the tiles show, and the ask waits.
    arriveAtCounter(rowOf(NEEMA), 15, "server");
    askToLeave();
    theLaptop(null);
    render(<AtTheDevice device={DAWA_LAPTOP} />);

    // She logs in again: the tap on her tile forgets the old ask.
    fireEvent.click(
      await screen.findByRole("button", { name: "Neema Mfano Neema" }),
    );
    for (const digit of "2580")
      fireEvent.click(screen.getByRole("button", { name: digit }));

    expect(
      await screen.findByRole("heading", { name: "Karibu, Neema" }),
    ).toBeDefined();
    expect(leaveAsked()).toBeNull();
    expect(logouts()).toHaveLength(0);
  });
});
