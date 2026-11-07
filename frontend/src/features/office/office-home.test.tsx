// office-home.test.tsx — the office's home page greets the person, with a big button for each office
// screen they may open (UI-5).
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DAWA, whoIsHere } from "@/test/devices";
import { answer, refusal } from "@/test/fake-server";
import { render } from "@/test/render";

import { OfficeHome } from "./office-home";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";

describe("the office's home page", () => {
  it("greets the person, and opens Vifaa for someone who manages devices", async () => {
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["device.manage"] }]),
    });

    render(<OfficeHome />);

    expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe(
      "Karibu, Neema",
    );
    const link = screen.getByRole("link", { name: "Vifaa" });
    // The end slash comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(link.getAttribute("href")).toMatch(/^\/devices\/?$/);
  });

  it("offers no screen someone may not open, and says so", async () => {
    // A seller logged in by password sees no Vifaa: registering and blocking devices isn't theirs.
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["sale.create"] }]),
    });

    render(<OfficeHome />);

    expect(
      await screen.findByText(
        "Bado hakuna kazi ya ofisi unayoweza kufungua hapa.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("says why when the server refuses the person", async () => {
    answer("GET", ME, refusal(403, "staff.suspended"));

    render(<OfficeHome />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Umesimamishwa",
    );
  });
});
