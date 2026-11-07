// at-the-device.test.tsx — leaving a shared laptop: Toka and Badilisha mtu end the session on the server,
// forget the person, and show the tiles for whoever is next (UI-4, 03 §5.9). The fake server keeps one
// session, as Django does for this browser: a PIN login starts it, a logout ends it, and `me` answers for it.
import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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
import { render } from "@/test/render";

import { AtTheDevice } from "./at-the-device";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const STAFF = "/api/devices/v1/staff/";
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
  },
  staff: {
    id: "019a5e00-0000-7000-8000-0000000000c3",
    display_name: "Juma",
    job_title: "Muuzaji",
  },
};

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
  answer("GET", STAFF, {
    status: 200,
    body: [NEEMA, JUMA].map((person) => ({
      id: person.staff.id,
      full_name: person.user.full_name,
      display_name: person.staff.display_name,
    })),
  });
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

    // TanStack waits a second before the next try.
    expect(
      await screen.findByRole(
        "heading",
        { level: 1, name: "Wewe ni nani?" },
        { timeout: 3000 },
      ),
    ).toBeDefined();
    expect(tries).toBe(2);
    expect(screen.queryByText("Neema")).toBeNull();
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
    vi.useFakeTimers({ shouldAdvanceTime: true });
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
    vi.useFakeTimers({ shouldAdvanceTime: true });
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

  it("speaks English after the switch, with no Swahili left", async () => {
    setLanguage("en");
    theLaptop(NEEMA);
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
    answer("GET", STAFF, {
      status: 200,
      body: [
        {
          id: JUMA.staff.id,
          full_name: JUMA.user.full_name,
          display_name: JUMA.staff.display_name,
        },
      ],
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
    // Juma taps his tile, then Rudi: the reason was for her, and is gone.
    fireEvent.click(screen.getByRole("button", { name: "Juma Mfano Juma" }));
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
    answer("GET", STAFF, { status: 200, body: [] });
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
