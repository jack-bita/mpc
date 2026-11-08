// office-home.test.tsx — the office's home page greets the person, with a big button for each office
// screen they may open (UI-5).
import { QueryClientProvider } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import { WHO_IS_HERE } from "@/features/people/who-is-here";
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

  it("moves focus to its welcome as it opens, where the form that sent the person here had it", async () => {
    // After a login, or Chagua nenosiri lako's Hifadhi, the button that had focus is gone: the welcome
    // takes it, so a screen reader says where the person is, and Tab goes on to the screens.
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["device.manage"] }]),
    });

    render(<OfficeHome />);

    const welcome = await screen.findByRole("heading", {
      name: "Karibu, Neema",
    });
    expect(document.activeElement).toBe(welcome);
  });

  it("says to wait while it asks who is here, so the page is never blank", () => {
    // Drawn before `me` answers, the page was empty: CI's every-page-in-English test caught it (UI-5's PR).
    answer("GET", ME, () => new Promise<Response>(() => undefined));

    render(<OfficeHome />);

    const line = screen.getByText("Subiri kidogo…");
    expect(line.getAttribute("role")).toBe("status");
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
    expect(screen.queryByRole("link", { name: "Vifaa" })).toBeNull();
  });

  it("opens Mipangilio yangu for everyone, who needs no key for their own", async () => {
    // A seller with no office work still has a language and a font of her own (UI-9).
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["sale.create"] }]),
    });

    render(<OfficeHome />);

    const link = await screen.findByRole("link", { name: "Mipangilio yangu" });
    expect(link.getAttribute("href")).toMatch(/^\/my-settings\/?$/);
  });

  it("greets nobody the server refused since, though the store still holds their answer", async () => {
    // TanStack keeps the last answer beside a refusal: read first, it would greet a suspended person.
    const store = makeQueryClient();
    store.setQueryData(
      WHO_IS_HERE,
      whoIsHere([{ side: DAWA, permissions: ["device.manage"] }]),
    );
    answer("GET", ME, refusal(403, "staff.suspended"));

    render(
      <QueryClientProvider client={store}>
        <OfficeHome />
      </QueryClientProvider>,
    );

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Umesimamishwa",
    );
    expect(screen.queryByRole("heading", { name: "Karibu, Neema" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Vifaa" })).toBeNull();
  });

  it("says why when the server refuses the person", async () => {
    answer("GET", ME, refusal(403, "staff.suspended"));

    render(<OfficeHome />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Umesimamishwa",
    );
  });
});
