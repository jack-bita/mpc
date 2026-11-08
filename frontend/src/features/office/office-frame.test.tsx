// office-frame.test.tsx — the office area's frame names who is logged in and their shop, with Toka;
// sends someone who isn't logged in to the way in; and locks a shared laptop by itself (UI-5).
import { QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import { saveDevice } from "@/features/devices/this-device";
import { WHO_IS_HERE } from "@/features/people/who-is-here";
import { DAWA, DAWA_LAPTOP, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import {
  leaveTheLastPersonsAnswers,
  stillHoldsTheirs,
} from "@/test/last-person";
import { render } from "@/test/render";
import { router } from "@/test/router";

import { OfficeFrame } from "./office-frame";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const LOGOUT = "/api/auth/logout/";

const NEEMA = whoIsHere([{ side: DAWA, permissions: ["device.manage"] }]);

function renderTheFrame() {
  return render(
    <OfficeFrame>
      <p>screen</p>
    </OfficeFrame>,
  );
}

/** Neema logged in, until a logout ends her session: then `me` refuses, as the server does. */
function neemaLoggedIn() {
  let here = true;
  answer("GET", ME, () => {
    const nobody = refusal(403, "not_authenticated");
    return here
      ? Response.json(NEEMA)
      : Response.json(nobody.body, { status: nobody.status });
  });
  answer("POST", LOGOUT, () => {
    here = false;
    return new Response(null, { status: 204 });
  });
  return {
    end: () => {
      here = false;
    },
  };
}

const bar = () => within(screen.getByRole("banner"));
const logouts = () =>
  sent.filter((request) => new URL(request.url).pathname === LOGOUT);
const askedWhoIsHere = () =>
  sent.filter((request) => new URL(request.url).pathname === ME).length;

describe("the office's frame", () => {
  it("names the person and their shop, on a phone that knows no device", async () => {
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["device.manage"] }]),
    });

    renderTheFrame();

    const bar = within(screen.getByRole("banner"));
    expect(await bar.findByText("Neema")).toBeTruthy();
    expect(bar.getByText("MPC")).toBeTruthy();
    expect(screen.getByRole("main").textContent).toBe("screen");
  });

  it("names the side the person works on, at a registered laptop", async () => {
    // Neema works on Vyakula, and logs in by password at the Dawa laptop.
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: VYAKULA, permissions: ["device.manage"] }]),
    });

    renderTheFrame();

    expect(
      await within(screen.getByRole("banner")).findByText("MPC · Vyakula"),
    ).toBeTruthy();
  });

  it("sends someone not logged in on a phone to the password login", async () => {
    answer("GET", ME, refusal(403, "not_authenticated"));

    renderTheFrame();

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login/"));
  });

  it("sends someone not logged in at a registered laptop to its PIN login", async () => {
    // The laptop's home page is the PIN login (UI-4): the way in at the counter.
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, refusal(403, "not_authenticated"));

    renderTheFrame();

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
  });

  it("keeps a person whose session the server refused for a reason, to read why, with Toka", async () => {
    // A suspension says so in place of the screen; sending them to the login would hide it.
    answer("GET", ME, refusal(403, "staff.suspended"));
    answer("POST", LOGOUT, { status: 204 });

    renderTheFrame();

    expect(
      await screen.findByText("Umesimamishwa. Ongea na meneja au mmiliki."),
    ).toBeTruthy();
    expect(screen.queryByText("screen")).toBeNull();
    expect(router.replace).not.toHaveBeenCalled();
    // The session still stands on the server, and blocks a new login (409): Toka ends it.
    fireEvent.click(
      within(screen.getByRole("main")).getByRole("button", { name: "Toka" }),
    );
    await waitFor(() => expect(logouts()).toHaveLength(1));
  });

  it("forgets a person the server refuses for a reason, so a later failure never brings them back", async () => {
    // Baba suspends Neema while the office shows her. TanStack keeps her last answer beside the
    // refusal, so a 502 a moment later, as the server restarts, would put her name and Toka back.
    let answers = "neema";
    answer("GET", ME, () => {
      if (answers === "neema") return Response.json(NEEMA);
      const why =
        answers === "suspended"
          ? refusal(403, "staff.suspended")
          : refusal(502, "server_error");
      return Response.json(why.body, { status: why.status });
    });
    const store = makeQueryClient();
    render(
      <QueryClientProvider client={store}>
        <OfficeFrame>
          <p>screen</p>
        </OfficeFrame>
      </QueryClientProvider>,
    );
    await bar().findByText("Neema");

    answers = "suspended";
    await act(() => store.refetchQueries({ queryKey: WHO_IS_HERE }));
    expect(
      await screen.findByText("Umesimamishwa. Ongea na meneja au mmiliki."),
    ).toBeTruthy();
    expect(bar().queryByText("Neema")).toBeNull();
    await waitFor(() =>
      expect(store.getQueryData(WHO_IS_HERE)).toBeUndefined(),
    );

    answers = "restarting";
    await act(() =>
      store.refetchQueries({ queryKey: WHO_IS_HERE }).catch(() => undefined),
    );
    expect(bar().queryByText("Neema")).toBeNull();
    expect(bar().queryByRole("button", { name: "Toka" })).toBeNull();
  });

  it("stays where it is while there is no network", async () => {
    answer("GET", ME, () => {
      throw new TypeError("Failed to fetch");
    });

    renderTheFrame();

    await waitFor(() => expect(sent.length).toBeGreaterThan(0));
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("forgets a person whose session ended on the server, before sending them to the way in", async () => {
    // Neema's session ends at its idle time while the office shows her. Kept, her last answer would
    // send her from the login straight back here (password-login.tsx).
    const phone = neemaLoggedIn();
    const store = makeQueryClient();
    render(
      <QueryClientProvider client={store}>
        <OfficeFrame>
          <p>screen</p>
        </OfficeFrame>
      </QueryClientProvider>,
    );
    await bar().findByText("Neema");

    phone.end();
    await act(() => store.refetchQueries({ queryKey: WHO_IS_HERE }));

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login/"));
    expect(store.getQueryData(WHO_IS_HERE)).toBeUndefined();
    expect(bar().queryByText("Neema")).toBeNull();
  });
});

describe("leaving the office", () => {
  it("Toka ends the session on the server, forgets the person, and goes to the way in", async () => {
    neemaLoggedIn();
    const store = makeQueryClient();
    leaveTheLastPersonsAnswers(store);
    render(
      <QueryClientProvider client={store}>
        <OfficeFrame>
          <p>screen</p>
        </OfficeFrame>
      </QueryClientProvider>,
    );

    fireEvent.click(await bar().findByRole("button", { name: "Toka" }));

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login/"));
    expect(logouts()).toHaveLength(1);
    // The store forgot her: her answer and her change are gone, and `me` was asked again, and answered
    // nobody.
    expect(stillHoldsTheirs(store)).toBe(false);
    expect(askedWhoIsHere()).toBeGreaterThan(1);
  });

  it("hides the person and the screen from the press, while the logout is on its way", async () => {
    // The network is slow: the logout hasn't arrived. The next person must see nothing of Neema's.
    neemaLoggedIn();
    answer("POST", LOGOUT, () => new Promise<Response>(() => {}));
    renderTheFrame();

    fireEvent.click(await bar().findByRole("button", { name: "Toka" }));

    // A status line, which a screen reader says as its words change; the offline banner is another.
    expect((await screen.findByText("Unatoka…")).getAttribute("role")).toBe(
      "status",
    );
    expect(screen.queryByText("screen")).toBeNull();
    expect(bar().queryByText("Neema")).toBeNull();
    expect(bar().queryByRole("button", { name: "Toka" })).toBeNull();
  });

  it("shows why when the server refuses the logout, and keeps the person", async () => {
    neemaLoggedIn();
    answer("POST", LOGOUT, refusal(403, "permission_denied"));
    renderTheFrame();

    fireEvent.click(await bar().findByRole("button", { name: "Toka" }));

    expect(
      await screen.findByText("Huna ruhusa ya kufanya hili."),
    ).toBeTruthy();
    expect(bar().getByText("Neema")).toBeTruthy();
    // Asked once: a refusal the server meant gets the same no again.
    expect(logouts()).toHaveLength(1);
  });

  it("logs out a password's session at the shared laptop after the idle minutes untouched", async () => {
    // Neema logs in by password at the Dawa laptop, then walks away. `me` gives her the shop's 15 minutes.
    // shouldAdvanceTime: the fake clock still moves on its own, so the fake server's answers arrive.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      saveDevice(DAWA_LAPTOP);
      neemaLoggedIn();
      renderTheFrame();
      await bar().findByText("Neema");

      await vi.advanceTimersByTimeAsync(15 * 60 * 1000 + 10 * 1000);

      await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
      expect(logouts()).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("never logs out a manager's own phone by itself", async () => {
    // Nobody else stands at it: its session ends on the server by itself (AUTH-4).
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      neemaLoggedIn();
      renderTheFrame();
      await bar().findByText("Neema");

      await vi.advanceTimersByTimeAsync(30 * 60 * 1000);

      expect(logouts()).toEqual([]);
      expect(bar().getByText("Neema")).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });
});
