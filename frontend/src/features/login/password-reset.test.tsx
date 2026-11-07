// password-reset.test.tsx — the email link's page: it reads the key after the #, clears it from the
// browser, checks it, and sets the new password with it (UI-5, AUTH-3).
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ALLAUTH } from "@/api/allauth";
import { allauthRefusal, answer, fakeFetch, sent } from "@/test/fake-server";
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

    openTheLink();

    expect(await screen.findByLabelText("Nenosiri jipya")).toBeTruthy();
    const [check] = resets("GET");
    expect(check?.headers.get("X-Password-Reset-Key")).toBe(KEY);
    // Out of the address bar and the history: the next person at this browser can't use it.
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/password-reset/");
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
