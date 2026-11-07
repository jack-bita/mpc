// device-check.test.tsx — the device asks the server who it is, keeps a yes, forgets a "not registered",
// and keeps its last answer when the server can't be reached; the top bar then names its shop (UI-3).
import { act, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/api/provider";
import { ApiRefusal, NoConnection } from "@/api/refusal";
import OfficeLayout from "@/app/(office)/layout";
import { DAWA_LAPTOP, DAWA_LAPTOP_ANSWER } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import {
  checkThisDevice,
  DEVICE_CHECK_EVERY,
  DeviceCheck,
} from "./device-check";
import {
  saveBlocked,
  savedBlocked,
  saveDevice,
  savedDevice,
} from "./this-device";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/devices/v1/me/";

afterEach(() => {
  vi.useRealTimers();
});

describe("checkThisDevice", () => {
  it("keeps a registered device's answer", async () => {
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });

    expect(await checkThisDevice()).toEqual(DAWA_LAPTOP);
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
  });

  it("forgets the saved copy when the server knows no device by this key", async () => {
    // A key still waiting for the manager, or a browser whose key is gone: 401 not_authenticated.
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, refusal(401, "not_authenticated"));

    expect(await checkThisDevice()).toBeNull();
    expect(savedDevice()).toBeNull();
  });

  it("keeps a block, and the device it was known as", async () => {
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, refusal(401, "device.blocked"));

    await expect(checkThisDevice()).rejects.toBeInstanceOf(ApiRefusal);
    expect(savedBlocked()).toBe(true);
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
  });

  it("lifts a block when the server names the device again", async () => {
    // The manager unblocked it: the same key works again (AUTH-1).
    saveDevice(DAWA_LAPTOP);
    saveBlocked();
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });

    await checkThisDevice();

    expect(savedBlocked()).toBe(false);
  });

  it("keeps the saved copy when no answer comes", async () => {
    // Offline, the laptop is still the Dawa laptop.
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, () => {
      throw new TypeError("Failed to fetch");
    });

    await expect(checkThisDevice()).rejects.toBeInstanceOf(NoConnection);
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
  });

  it("keeps the saved copy when the server has a problem", async () => {
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, refusal(500, "server_error"));

    await expect(checkThisDevice()).rejects.toBeInstanceOf(ApiRefusal);
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
  });
});

describe("DeviceCheck", () => {
  it("asks when the app opens, and the top bar names the shop and the home side", async () => {
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });

    render(
      <QueryProvider>
        <OfficeLayout>
          <p>screen</p>
        </OfficeLayout>
        <DeviceCheck />
      </QueryProvider>,
    );

    expect(await screen.findByText("MPC · Dawa")).toBeDefined();
    // Words only: no side says which band it gets yet (04 §20, item 19).
    expect(document.querySelector("[data-look]")).toBeNull();
  });

  it("asks again every 5 minutes, so a rename on the manager's phone shows", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
    render(
      <QueryProvider>
        <DeviceCheck />
      </QueryProvider>,
    );
    await vi.waitFor(() => expect(savedDevice()).toEqual(DAWA_LAPTOP));

    const renamed = {
      ...DAWA_LAPTOP_ANSWER,
      device: { ...DAWA_LAPTOP_ANSWER.device, name: "Laptop ya Dawa" },
    };
    answer("GET", ME, { status: 200, body: renamed });
    await act(() => vi.advanceTimersByTimeAsync(DEVICE_CHECK_EVERY));

    await vi.waitFor(() => expect(savedDevice()?.name).toBe("Laptop ya Dawa"));
    expect(sent.length).toBe(2);
  });
});
