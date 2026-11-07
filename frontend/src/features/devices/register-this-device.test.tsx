// register-this-device.test.tsx — Sajili kifaa hiki: the code, its countdown on the server's clock,
// the wait for the manager, the shop's name once they say yes, and every way it can go wrong (UI-3).
import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { DAWA_LAPTOP, DAWA_LAPTOP_ANSWER } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

import { RegisterThisDevice, WAIT_CHECK_EVERY } from "./register-this-device";
import { saveDevice } from "./this-device";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/devices/v1/me/";
const PAIRING = "/api/devices/v1/pairing/";
const TEN_MINUTES = 10 * 60 * 1000;

/** The server's answer to a start: the code, and its expiry 10 minutes after the server's own time,
 * which its Date header carries, in whole seconds. */
function codeAnswer(code: string, serverNow = Date.now()) {
  return () =>
    Response.json(
      { code, expires_at: new Date(serverNow + TEN_MINUTES).toISOString() },
      { status: 201, headers: { Date: new Date(serverNow).toUTCString() } },
    );
}

beforeEach(() => {
  // The countdown and the waiting check run on timers: these move them by hand. shouldAdvanceTime lets
  // real time move them too, so the store's own small waits still pass.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date("2026-11-07T09:00:00Z"));
  // A CSRF token, as the device's check gives the browser when the app opens.
  document.cookie = "csrftoken=t0ken";
  // Not registered: the manager hasn't said yes yet.
  answer("GET", ME, refusal(401, "not_authenticated"));
});

afterEach(() => {
  vi.useRealTimers();
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

const getACode = () =>
  fireEvent.click(screen.getByRole("button", { name: "Pata namba" }));

describe("Sajili kifaa hiki", () => {
  it("gets a code and shows it in two groups, with the time it has left", async () => {
    answer("POST", PAIRING, codeAnswer("K7QM4RXT"));
    render(<RegisterThisDevice />);

    getACode();

    expect(await screen.findByText("K7QM-4RXT")).toBeDefined();
    expect(screen.getByText("Namba inaisha baada ya 9:59")).toBeDefined();
    expect(screen.getByText("Kinasubiri meneja…")).toBeDefined();
    // Focus moves to what to do next, as the button that asked is gone.
    expect(document.activeElement?.textContent).toBe("Mpe meneja namba hii");
  });

  it("counts on the server's clock, so a laptop an hour ahead still waits its 10 minutes", async () => {
    // The server's time is an hour behind this laptop's.
    answer(
      "POST",
      PAIRING,
      codeAnswer("K7QM4RXT", Date.now() - 60 * 60 * 1000),
    );
    render(<RegisterThisDevice />);

    getACode();

    expect(
      await screen.findByText("Namba inaisha baada ya 9:59"),
    ).toBeDefined();
  });

  it("asks every 3 seconds, and shows the shop's name once the manager says yes", async () => {
    answer("POST", PAIRING, codeAnswer("K7QM4RXT"));
    render(<RegisterThisDevice />);
    getACode();
    await screen.findByText("K7QM-4RXT");

    // The manager types the code on their phone.
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
    await act(() => vi.advanceTimersByTimeAsync(WAIT_CHECK_EVERY));

    expect(await screen.findByText("Kifaa hiki kimesajiliwa")).toBeDefined();
    // The shop by name, so a code claimed by another shop's manager shows at once (03 §5.9).
    expect(
      screen.getByText(
        "Jina lake ni Laptop Dawa, upande wa Dawa, duka la MPC.",
      ),
    ).toBeDefined();
    expect(
      screen.getByRole("link", { name: "Endelea" }).getAttribute("href"),
    ).toBe("/");
  });

  it("says when the code has expired, stops asking, and gets a new one", async () => {
    answer("POST", PAIRING, codeAnswer("K7QM4RXT"));
    render(<RegisterThisDevice />);
    getACode();
    await screen.findByText("K7QM-4RXT");

    await act(() => vi.advanceTimersByTimeAsync(TEN_MINUTES));
    expect(
      await screen.findByText("Muda wa namba hii umekwisha."),
    ).toBeDefined();
    expect(screen.queryByText("K7QM-4RXT")).toBeNull();

    // No more asking: the manager can't confirm an expired code.
    const asked = sent.filter((request) => request.url.endsWith(ME)).length;
    await act(() => vi.advanceTimersByTimeAsync(10 * WAIT_CHECK_EVERY));
    expect(sent.filter((request) => request.url.endsWith(ME)).length).toBe(
      asked,
    );

    answer("POST", PAIRING, codeAnswer("ABCD2345"));
    fireEvent.click(screen.getByRole("button", { name: "Pata namba mpya" }));
    expect(await screen.findByText("ABCD-2345")).toBeDefined();
  });

  it("keeps the old code's view while a new code comes, never the first screen", async () => {
    answer("POST", PAIRING, codeAnswer("K7QM4RXT"));
    render(<RegisterThisDevice />);
    getACode();
    await screen.findByText("K7QM-4RXT");
    await act(() => vi.advanceTimersByTimeAsync(TEN_MINUTES));

    // The new code is slow to come: the start waits until the test lets it answer.
    let answerNow = () => {};
    answer(
      "POST",
      PAIRING,
      () =>
        new Promise<Response>((resolve) => {
          answerNow = () => resolve(codeAnswer("ABCD2345")());
        }),
    );
    const newCode = screen.getByRole("button", { name: "Pata namba mpya" });
    fireEvent.click(newCode);

    await vi.waitFor(() =>
      expect((newCode as HTMLButtonElement).disabled).toBe(true),
    );
    expect(screen.queryByText(/bado hakijasajiliwa/)).toBeNull();
    expect(screen.getByText("Muda wa namba hii umekwisha.")).toBeDefined();

    answerNow();
    expect(await screen.findByText("ABCD-2345")).toBeDefined();
  });

  it("says how long to wait after too many tries from the shop's network", async () => {
    answer("POST", PAIRING, refusal(429, "throttled", { wait: 300 }));
    render(<RegisterThisDevice />);

    getACode();

    expect(
      await screen.findByText(
        "Majaribio mengi mno. Jaribu tena baada ya dakika 5.",
      ),
    ).toBeDefined();
  });

  it("sends the CSRF token with the start", async () => {
    answer("POST", PAIRING, codeAnswer("K7QM4RXT"));
    render(<RegisterThisDevice />);

    getACode();
    await screen.findByText("K7QM-4RXT");

    const start = sent.find((request) => request.method === "POST");
    expect(start?.headers.get("X-CSRFToken")).toBe("t0ken");
  });

  it("asks the device's check for a CSRF token first when it has none", async () => {
    // A tap faster than the app's first answer, on a slow network.
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    answer("POST", PAIRING, codeAnswer("K7QM4RXT"));
    render(<RegisterThisDevice />);

    getACode();
    await screen.findByText("K7QM-4RXT");

    expect(sent.map((request) => request.method)).toEqual(
      expect.arrayContaining(["GET", "POST"]),
    );
    expect(sent[0]?.url.endsWith(ME)).toBe(true);
  });

  it("shows a registered device its name, and no way to get a code", () => {
    saveDevice(DAWA_LAPTOP);

    render(<RegisterThisDevice />);

    expect(screen.getByText("Kifaa hiki kimesajiliwa")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Pata namba" })).toBeNull();
  });

  it("speaks English after the switch, with no Swahili left, while it waits", async () => {
    setLanguage("en");
    answer("POST", PAIRING, codeAnswer("K7QM4RXT"));
    const { container } = render(<RegisterThisDevice />);

    fireEvent.click(screen.getByRole("button", { name: "Get a code" }));

    expect(await screen.findByText("The code expires in 9:59")).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});
