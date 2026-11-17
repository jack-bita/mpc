// forgot-password.test.tsx — a forgotten password: the owner sets a temporary one face to face, or an
// email link sets a new one (UI-5, ADR-0038).
import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ALLAUTH } from "@/api/allauth";
import { allauthRefusal, answer, fakeFetch, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import { ForgotPassword } from "./forgot-password";

const REQUEST = `${ALLAUTH}auth/password/request`;

beforeEach(() => {
  // allauth's routes go through the browser's own fetch (src/api/allauth.ts).
  vi.stubGlobal("fetch", fakeFetch);
  document.cookie = "csrftoken=token-from-django; path=/";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

function ask(email: string) {
  fireEvent.change(screen.getByLabelText("Barua pepe"), {
    target: { value: email },
  });
  fireEvent.click(screen.getByRole("button", { name: "Tuma kiungo" }));
}

const requests = () =>
  sent.filter((request) => new URL(request.url).pathname === REQUEST);

describe("a forgotten password", () => {
  it("tells a person with no email to ask the owner, face to face", () => {
    // Most of the shop's people have a phone and no email (ADR-0038).
    render(<ForgotPassword />);

    expect(
      screen.getByText(
        "Huna barua pepe? Mwombe mmiliki akuwekee nenosiri la muda, ana kwa ana.",
      ),
    ).toBeTruthy();
  });

  it("sends the email, and says a link went if it has an account here", async () => {
    answer("POST", REQUEST, { status: 200, body: { status: 200 } });
    render(<ForgotPassword />);

    ask(" neema@example.com ");

    expect(
      await screen.findByText(
        "Kama barua pepe hii ina akaunti hapa, tumetuma kiungo. Kifungue ndani ya saa moja.",
      ),
    ).toBeTruthy();
    expect(await requests()[0]?.json()).toEqual({ email: "neema@example.com" });
    // The form is gone, with the way back to the login in its place.
    expect(screen.queryByLabelText("Barua pepe")).toBeNull();
    expect(
      screen.getByRole("link", { name: "Rudi kuingia" }).getAttribute("href"),
    ).toMatch(/^\/login\/?$/);
  });

  it("asks for a whole email before it sends anything", async () => {
    // A phone typed here: a link goes only to an email.
    render(<ForgotPassword />);

    ask("0712345678");

    expect(
      await screen.findByText("Andika barua pepe kamili, kama jina@mfano.com."),
    ).toBeTruthy();
    expect(requests()).toEqual([]);
  });

  it("says the same sentence beside the box when the server refuses the email", async () => {
    // Django's check of an email is the last word; its code is the general `invalid`.
    answer(
      "POST",
      REQUEST,
      allauthRefusal(400, [{ code: "invalid", param: "email" }]),
    );
    render(<ForgotPassword />);

    ask("neema@example");

    expect(
      await screen.findByText("Andika barua pepe kamili, kama jina@mfano.com."),
    ).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says too many tries when the limit answers", async () => {
    // 3 links an hour to one address (AUTH-3's review).
    answer("POST", REQUEST, allauthRefusal(429));
    render(<ForgotPassword />);

    ask("neema@example.com");

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Majaribio mengi mno",
    );
  });
});
