// office-frame.test.tsx — the office area's frame names who is logged in and their shop, and sends
// someone who isn't to the way in (UI-5).
import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { DAWA, DAWA_LAPTOP, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { router } from "@/test/router";

import { OfficeFrame } from "./office-frame";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";

function renderTheFrame() {
  return render(
    <OfficeFrame>
      <p>screen</p>
    </OfficeFrame>,
  );
}

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

  it("keeps a person whose session the server refused for a reason, to read why", async () => {
    // A suspension says so on the screen (ApiErrorAlert); sending them to the login would hide it.
    answer("GET", ME, refusal(403, "staff.suspended"));

    renderTheFrame();

    await waitFor(() => expect(sent).toHaveLength(1));
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("stays where it is while there is no network", async () => {
    answer("GET", ME, () => {
      throw new TypeError("Failed to fetch");
    });

    renderTheFrame();

    await waitFor(() => expect(sent.length).toBeGreaterThan(0));
    expect(router.replace).not.toHaveBeenCalled();
  });
});
