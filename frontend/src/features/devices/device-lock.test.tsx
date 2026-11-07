// device-lock.test.tsx — a blocked device's app locks on its next request, with a clear message (the
// UI-3 card's second Done line), stays locked offline, and opens again after an unblock.
import { useMutation, useQuery } from "@tanstack/react-query";
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { QueryProvider } from "@/api/provider";
import { answerOf } from "@/api/refusal";
import { setLanguage } from "@/i18n/language";
import { DAWA_LAPTOP, DAWA_LAPTOP_ANSWER } from "@/test/devices";
import { answer, refusal } from "@/test/fake-server";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

import { DeviceCheck } from "./device-check";
import { DeviceLock } from "./device-lock";
import { saveBlocked, saveDevice } from "./this-device";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/devices/v1/me/";

/** The app in miniature, as the root layout puts it together: the page under the lock, the check
 * beside it. */
function renderApp(page = <p>screen</p>) {
  return render(
    <QueryProvider>
      <DeviceLock>{page}</DeviceLock>
      <DeviceCheck />
    </QueryProvider>,
  );
}

// A screen that reads `me` through the store, as UI-4's PIN screen will.
function WhoIsHere() {
  const who = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => answerOf(api.GET("/api/auth/me/")),
  });
  return <p>{who.isError ? "refused" : "screen"}</p>;
}

// A screen that sends a change through the store, as a PIN login will.
function PinLogin() {
  const login = useMutation({
    mutationFn: () =>
      answerOf(
        api.POST("/api/auth/pin-login/", {
          body: { staff: DAWA_LAPTOP.id, pin: "4826" },
        }),
      ),
  });
  return (
    <button type="button" onClick={() => login.mutate()}>
      screen
    </button>
  );
}

const lockTitle = () => screen.findByText("Kifaa hiki kimezuiwa");

/** The Jaribu tena button, once the check that brought the lock is over: it is switched off while a
 * check runs, so a second tap can't send a second one. */
async function readyToTryAgain(): Promise<HTMLButtonElement> {
  const button = screen.getByRole<HTMLButtonElement>("button", {
    name: "Jaribu tena",
  });
  await vi.waitFor(() => expect(button.disabled).toBe(false));
  return button;
}

describe("the lock", () => {
  it("covers the page at the next check, and says which device and who can open it", async () => {
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, refusal(401, "device.blocked"));

    renderApp();

    expect(await lockTitle()).toBeDefined();
    const message = screen.getAllByRole("alert")[0]?.textContent;
    // The name on the manager's list, so they know which one to unblock.
    expect(message).toContain("Laptop Dawa · MPC");
    expect(message).toContain("Mwombe meneja akifungue.");
    // Nothing of the page shows behind it.
    expect(screen.queryByText("screen")).toBeNull();
  });

  it("comes at the device's next read of any kind", async () => {
    // A PIN session's office routes answer device.blocked as a 403 (AUTH-4).
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
    answer("GET", "/api/auth/me/", refusal(403, "device.blocked"));

    renderApp(<WhoIsHere />);

    expect(await lockTitle()).toBeDefined();
  });

  it("comes at the device's next change of any kind", async () => {
    // A PIN login on a blocked device: the device's own login refuses it first (AUTH-2).
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
    answer("POST", "/api/auth/pin-login/", refusal(401, "device.blocked"));
    renderApp(<PinLogin />);

    fireEvent.click(await screen.findByRole("button", { name: "screen" }));

    expect(await lockTitle()).toBeDefined();
  });

  it("opens again when Jaribu tena finds the device unblocked", async () => {
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, refusal(401, "device.blocked"));
    renderApp();
    expect(await lockTitle()).toBeDefined();

    // The manager unblocks it: the same key works again (AUTH-1).
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
    fireEvent.click(await readyToTryAgain());

    expect(await screen.findByText("screen")).toBeDefined();
    expect(screen.queryByText("Kifaa hiki kimezuiwa")).toBeNull();
  });

  it("stays on through a reload with no network, and says why a try changes nothing", async () => {
    saveDevice(DAWA_LAPTOP);
    saveBlocked();
    answer("GET", ME, () => {
      throw new TypeError("Failed to fetch");
    });

    renderApp();

    expect(await lockTitle()).toBeDefined();
    expect(screen.queryByText("screen")).toBeNull();
    expect(
      await screen.findByText(
        "Imeshindwa kufika kwenye seva. Angalia mtandao, kisha ujaribu tena.",
      ),
    ).toBeDefined();
  });

  it("locks a device it never knew, with no names", async () => {
    // Its saved copy was wiped; its key still works for the server, which knows it is blocked.
    answer("GET", ME, refusal(401, "device.blocked"));

    renderApp();

    expect(await lockTitle()).toBeDefined();
    expect(screen.getByRole("banner").textContent).not.toContain("MPC");
  });

  it("speaks English after the switch, with no Swahili left", async () => {
    setLanguage("en");
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, refusal(401, "device.blocked"));

    const { container } = renderApp();

    expect(await screen.findByText("This device is blocked")).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });

  it("leaves the page alone while the device works", async () => {
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });

    renderApp();

    expect(await screen.findByText("screen")).toBeDefined();
    expect(screen.queryByText("Kifaa hiki kimezuiwa")).toBeNull();
  });
});
