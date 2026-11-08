// password-reset.test.tsx — the email link's page: it reads the key after the #, clears it from the
// browser, checks it, and sets the new password with it (UI-5, AUTH-3).
import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ALLAUTH } from "@/api/allauth";
import { makeQueryClient } from "@/api/query-client";
import { allauthRefusal, answer, fakeFetch, sent } from "@/test/fake-server";
import { stillHoldsTheSecret } from "@/test/last-person";
import { render } from "@/test/render";

import { PasswordReset } from "./password-reset";

const RESET = `${ALLAUTH}auth/password/reset`;
const KEY = "3-c9x2k1-5f0b7e8d9a1c2b3d4e5f";

beforeEach(() => {
  // allauth's routes go through the browser's own fetch (src/api/allauth.ts).
  vi.stubGlobal("fetch", fakeFetch);
  document.cookie = "csrftoken=token-from-django; path=/";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.history.replaceState(null, "", "/");
});

/** The page as the email's link opens it: the key after the #, which no server ever sees. */
function openTheLink(key = KEY) {
  window.history.replaceState(null, "", `/password-reset/#${key}`);
  return render(<PasswordReset />);
}

/** The key works, and setting the password answers `set`: 401 by default, as a reset that worked logs
 * nobody in (AUTH-3). */
function aWorkingKey(
  set: { status: number; body?: unknown } = {
    status: 401,
    body: { status: 401 },
  },
) {
  answer("GET", RESET, { status: 200, body: { status: 200, data: {} } });
  answer("POST", RESET, set);
}

function setPassword(fresh: string, again = fresh) {
  fireEvent.change(screen.getByLabelText("Nenosiri jipya"), {
    target: { value: fresh },
  });
  fireEvent.change(screen.getByLabelText("Andika nenosiri jipya tena"), {
    target: { value: again },
  });
  fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));
}

const resets = (method: string) =>
  sent.filter(
    (request) =>
      request.method === method && new URL(request.url).pathname === RESET,
  );

describe("the email link's page", () => {
  it("reads the key after the #, clears it from the browser, and checks it", async () => {
    aWorkingKey();
    const entries = window.history.length;

    openTheLink();

    expect(await screen.findByLabelText("Nenosiri jipya")).toBeTruthy();
    const [check] = resets("GET");
    expect(check?.headers.get("X-Password-Reset-Key")).toBe(KEY);
    // Out of the address bar and the tab's entry: the next person at this tab can't use it.
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/password-reset/");
    // In the same entry, not a new one: Back would open the address with its key (pushState would pass
    // the two lines above).
    expect(window.history.length).toBe(entries);
  });

  it("sets the new password with the link's key, and says to log in with it", async () => {
    aWorkingKey();
    openTheLink();
    await screen.findByLabelText("Nenosiri jipya");

    setPassword("siri-ya-neema-2026");

    expect(
      await screen.findByText(
        "Nenosiri lako jipya limewekwa. Ingia nalo sasa.",
      ),
    ).toBeTruthy();
    const [set] = resets("POST");
    expect(await set?.json()).toEqual({
      key: KEY,
      password: "siri-ya-neema-2026",
    });
    expect(
      screen.getByRole("link", { name: "Ingia" }).getAttribute("href"),
    ).toMatch(/^\/login\/?$/);
  });

  it("keeps no password in the store once it is set", async () => {
    // A shared laptop: the next person at it must find nothing of the new password.
    aWorkingKey();
    window.history.replaceState(null, "", `/password-reset/#${KEY}`);
    const store = makeQueryClient();
    render(
      <QueryClientProvider client={store}>
        <PasswordReset />
      </QueryClientProvider>,
    );
    await screen.findByLabelText("Nenosiri jipya");

    setPassword("siri-ya-neema-2026");

    await screen.findByText("Nenosiri lako jipya limewekwa. Ingia nalo sasa.");
    await waitFor(() =>
      expect(stillHoldsTheSecret(store, "siri-ya-neema-2026")).toBe(false),
    );
  });

  it("takes a 200 as done too, as a browser logged in already may get", async () => {
    aWorkingKey({ status: 200, body: { status: 200 } });
    openTheLink();
    await screen.findByLabelText("Nenosiri jipya");

    setPassword("siri-ya-neema-2026");

    expect(
      await screen.findByText(
        "Nenosiri lako jipya limewekwa. Ingia nalo sasa.",
      ),
    ).toBeTruthy();
  });

  it("says the link no longer works when its key is dead, and offers a new one", async () => {
    // Used once already, or older than an hour (AUTH-3).
    answer(
      "GET",
      RESET,
      allauthRefusal(400, [{ code: "invalid_password_reset", param: "key" }]),
    );

    openTheLink();

    expect(
      await screen.findByText("Kiungo hiki hakifanyi kazi tena. Omba kingine."),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Nenosiri jipya")).toBeNull();
    expect(
      screen
        .getByRole("link", { name: "Omba kiungo kingine" })
        .getAttribute("href"),
    ).toMatch(/^\/forgot-password\/?$/);
  });

  it("says the link no longer works when it died while the person typed", async () => {
    aWorkingKey(
      allauthRefusal(400, [{ code: "invalid_password_reset", param: "key" }]),
    );
    openTheLink();
    await screen.findByLabelText("Nenosiri jipya");

    setPassword("siri-ya-neema-2026");

    expect(
      await screen.findByText("Kiungo hiki hakifanyi kazi tena. Omba kingine."),
    ).toBeTruthy();
  });

  it("says beside the box when the new password is refused", async () => {
    aWorkingKey(
      allauthRefusal(400, [{ code: "password_too_common", param: "password" }]),
    );
    openTheLink();
    await screen.findByLabelText("Nenosiri jipya");

    setPassword("password123");

    expect(
      await screen.findByText(
        "Nenosiri hili linatumiwa na watu wengi mno. Chagua jingine.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByLabelText("Nenosiri jipya").getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("asks for the new password twice, the same both times, before it sends anything", async () => {
    aWorkingKey();
    openTheLink();
    await screen.findByLabelText("Nenosiri jipya");

    setPassword("siri-ya-neema-2026", "siri-ya-neema-2062");

    expect(
      await screen.findByText("Andika nenosiri lile lile mara zote mbili."),
    ).toBeTruthy();
    expect(resets("POST")).toEqual([]);
  });

  it("follows a new link pasted into the same tab, with nothing kept from the old one", async () => {
    // The hand test: the page said an old link was dead, and a new link was pasted over it. Only the part
    // after the # changed, so the browser didn't reload the page, and the old answer stayed on show.
    const fresh = "3-d0y3l2-6a1c8f9e0b2d3c4e5f6a";
    answer("GET", RESET, (request) =>
      request.headers.get("X-Password-Reset-Key") === fresh
        ? Response.json({ status: 200, data: {} })
        : Response.json(
            {
              status: 400,
              errors: [{ code: "invalid_password_reset", param: "key" }],
            },
            { status: 400 },
          ),
    );
    openTheLink();
    await screen.findByText("Kiungo hiki hakifanyi kazi tena. Omba kingine.");

    act(() => {
      window.history.replaceState(null, "", `/password-reset/#${fresh}`);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    expect(await screen.findByLabelText("Nenosiri jipya")).toBeTruthy();
    expect(
      screen.queryByText("Kiungo hiki hakifanyi kazi tena. Omba kingine."),
    ).toBeNull();
    expect(window.location.hash).toBe("");
  });

  it("takes the key out of the address again when the same link is pasted twice", async () => {
    // The page keeps the key it already has, so nothing else changes, but the address must not keep it.
    aWorkingKey();
    openTheLink();
    await screen.findByLabelText("Nenosiri jipya");
    expect(window.location.hash).toBe("");

    act(() => {
      window.history.replaceState(null, "", `/password-reset/#${KEY}`);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    await waitFor(() => expect(window.location.hash).toBe(""));
  });

  it("takes the key out with no history state of its own, so Next.js's router forgets it too", async () => {
    // Next.js patches replaceState: a call carrying its own state (__NA) is taken as its own, and its router
    // keeps the old address, key and all, to write back at its next change. With null, it copies its
    // state itself and takes the new address (next/dist/client/components/app-router.js).
    aWorkingKey();
    // The state Next.js keeps in a page's history entry, as a real page has it.
    window.history.replaceState(
      { __NA: true, __PRIVATE_NEXTJS_INTERNALS_TREE: {} },
      "",
      `/password-reset/#${KEY}`,
    );
    const replace = vi.spyOn(window.history, "replaceState");
    render(<PasswordReset />);
    await screen.findByLabelText("Nenosiri jipya");

    const takingTheKeyOut = replace.mock.calls.filter(
      ([, , url]) => url === "/password-reset/",
    );
    expect(takingTheKeyOut).toHaveLength(1);
    expect(takingTheKeyOut[0]?.[0]).toBeNull();
    replace.mockRestore();
  });

  it("says what to do when the link has no key, and sends nothing", async () => {
    // A link cut short as it was copied from the email.
    window.history.replaceState(null, "", "/password-reset/");

    render(<PasswordReset />);

    expect(
      await screen.findByText(
        "Kiungo hiki hakijakamilika. Kifungue tena kutoka kwenye barua pepe, au omba kingine.",
      ),
    ).toBeTruthy();
    await waitFor(() => expect(sent).toEqual([]));
  });
});
