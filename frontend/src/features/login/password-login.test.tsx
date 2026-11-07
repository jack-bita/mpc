// password-login.test.tsx — the owner and managers log in on their own phones, by phone or email and a
// password, through allauth (UI-5, ADR-0038).
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ALLAUTH } from "@/api/allauth";
import { makeQueryClient } from "@/api/query-client";
import { WHO_IS_HERE } from "@/features/people/who-is-here";
import { DAWA, whoIsHere } from "@/test/devices";
import {
  allauthRefusal,
  answer,
  fakeFetch,
  refusal,
  sent,
} from "@/test/fake-server";
import { render } from "@/test/render";
import { router } from "@/test/router";

import { AFTER_LOGIN, PasswordLogin } from "./password-login";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const LOGIN = `${ALLAUTH}auth/login`;

beforeEach(() => {
  // allauth's routes go through the browser's own fetch (src/api/allauth.ts).
  vi.stubGlobal("fetch", fakeFetch);
  document.cookie = "csrftoken=token-from-django; path=/";
  // Nobody is logged in on this phone yet.
  answer("GET", ME, refusal(403, "not_authenticated"));
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

function logIn(name: string, password: string) {
  fireEvent.change(screen.getByLabelText("Simu au barua pepe"), {
    target: { value: name },
  });
  fireEvent.change(screen.getByLabelText("Nenosiri"), {
    target: { value: password },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ingia" }));
}

const logins = () =>
  sent.filter((request) => new URL(request.url).pathname === LOGIN);
const askedWhoIsHere = () =>
  sent.filter((request) => new URL(request.url).pathname === ME).length;

describe("the password login", () => {
  it("sends the phone written in full, forgets the last person, and opens the office", async () => {
    answer("POST", LOGIN, { status: 200, body: { status: 200 } });
    render(<PasswordLogin />);
    await waitFor(() => expect(askedWhoIsHere()).toBe(1));

    logIn("0712 345 678", "siri-ya-neema");

    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith(AFTER_LOGIN),
    );
    const [login] = logins();
    expect(await login?.json()).toEqual({
      phone: "+255712345678",
      password: "siri-ya-neema",
    });
    // The store forgot whoever was here before: `me` was asked again, for the new person (UI-4).
    expect(askedWhoIsHere()).toBe(2);
  });

  it("sends an email as an email", async () => {
    answer("POST", LOGIN, { status: 200, body: { status: 200 } });
    render(<PasswordLogin />);

    logIn("neema@example.com", "siri-ya-neema");

    await waitFor(() => expect(logins()).toHaveLength(1));
    expect(await logins()[0]?.json()).toEqual({
      email: "neema@example.com",
      password: "siri-ya-neema",
    });
  });

  it("says beside the password box when the password is wrong", async () => {
    answer(
      "POST",
      LOGIN,
      allauthRefusal(400, [
        { code: "phone_password_mismatch", param: "password" },
      ]),
    );
    render(<PasswordLogin />);

    logIn("0712345678", "si-yenyewe");

    expect(await screen.findByText("Simu au nenosiri si sahihi.")).toBeTruthy();
    expect(screen.getByLabelText("Nenosiri").getAttribute("aria-invalid")).toBe(
      "true",
    );
    // Said once, beside its box: not in an alert under the form too.
    expect(screen.queryByRole("alert")).toBeNull();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("says beside the first box when the phone is not a real number", async () => {
    // Our cleaner's code, beside allauth's phone field (apps/people/accounts.py).
    answer(
      "POST",
      LOGIN,
      allauthRefusal(400, [{ code: "phone.invalid", param: "phone" }]),
    );
    render(<PasswordLogin />);

    logIn("0123", "siri-ya-neema");

    expect(
      await screen.findByText("Namba hii ya simu si sahihi."),
    ).toBeTruthy();
    expect(
      screen.getByLabelText("Simu au barua pepe").getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("asks for both boxes before it sends anything", async () => {
    render(<PasswordLogin />);

    fireEvent.click(screen.getByRole("button", { name: "Ingia" }));

    expect(await screen.findAllByText("Jaza sehemu hii.")).toHaveLength(2);
    expect(logins()).toEqual([]);
  });

  it("says to log out first when this browser already holds a session", async () => {
    // A PIN's session on the shared laptop: allauth's session says nobody, its login says 409 (AUTH-4).
    answer("POST", LOGIN, allauthRefusal(409));
    render(<PasswordLogin />);

    logIn("0712345678", "siri-ya-neema");

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Toka kwanza",
    );
  });

  it("tells a switched-off person to talk to the owner", async () => {
    // The right password for a person switched off: allauth starts no session, and says only 401.
    answer("POST", LOGIN, allauthRefusal(401));
    render(<PasswordLogin />);

    logIn("0712345678", "siri-ya-neema");

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Ongea na mmiliki",
    );
  });

  it("says too many tries when a limit answers", async () => {
    answer("POST", LOGIN, allauthRefusal(429));
    render(<PasswordLogin />);

    logIn("0712345678", "siri-ya-neema");

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Majaribio mengi mno",
    );
  });

  it("says to check the internet when no answer comes", async () => {
    render(<PasswordLogin />);
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );

    logIn("0712345678", "siri-ya-neema");

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Angalia mtandao",
    );
  });

  it("sends someone already logged in on this phone straight to the office", async () => {
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["device.manage"] }]),
    });

    render(<PasswordLogin />);

    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith(AFTER_LOGIN),
    );
    expect(logins()).toEqual([]);
  });

  it("shows the way back in after a forgotten password", () => {
    render(<PasswordLogin />);

    const link = screen.getByRole("link", { name: "Umesahau nenosiri?" });
    // The end slash comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(link.getAttribute("href")).toMatch(/^\/forgot-password\/?$/);
  });

  it("shows the form when the store still holds a session that has ended", async () => {
    // Neema's session ended at its idle time while the office showed her, and the store kept her last
    // answer. Read as "already here", the office would send her back, and back again (office-frame.tsx).
    const store = makeQueryClient();
    store.setQueryData(
      WHO_IS_HERE,
      whoIsHere([{ side: DAWA, permissions: ["device.manage"] }]),
    );

    render(
      <QueryClientProvider client={store}>
        <PasswordLogin />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(store.getQueryState(WHO_IS_HERE)?.status).toBe("error"),
    );
    expect(router.replace).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Nenosiri")).toBeTruthy();
  });
});
