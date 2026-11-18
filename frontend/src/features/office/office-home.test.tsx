// office-home.test.tsx — the office's home page greets the person, with a big button for each office
// screen they may open (UI-5), Mipangilio ya duka (SHOP-5) and Wafanyakazi (PPL-6) among them.
import { QueryClientProvider } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import { WHO_IS_HERE } from "@/features/people/who-is-here";
import { DAWA, whoIsHere } from "@/test/devices";
import { answer, refusal } from "@/test/fake-server";
import { render } from "@/test/render";
import { MANAGER } from "@/test/workers";

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

  it("opens Hali ya vifaa for someone who manages devices (SYNC-14)", async () => {
    // Keeping the shop's laptops working is theirs: which one is cut off, behind, or not syncing.
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["device.manage"] }]),
    });

    render(<OfficeHome />);

    const link = await screen.findByRole("link", { name: "Hali ya vifaa" });
    expect(link.getAttribute("href")).toMatch(/^\/device-health\/?$/);
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

  it("offers no screen someone may not open", async () => {
    // A seller logged in by password sees no Vifaa: registering and blocking devices isn't theirs.
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["sale.create"] }]),
    });

    render(<OfficeHome />);

    await screen.findByRole("link", { name: "Mipangilio ya duka" });
    expect(screen.queryByRole("link", { name: "Vifaa" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Hali ya vifaa" })).toBeNull();
  });

  it("opens Mipangilio ya duka for anyone who works on a side (SHOP-5)", async () => {
    // Reading the shop's rules needs no key: every one already travels to every laptop of the shop.
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["sale.create"] }]),
    });

    render(<OfficeHome />);

    const link = await screen.findByRole("link", {
      name: "Mipangilio ya duka",
    });
    expect(link.getAttribute("href")).toMatch(/^\/settings\/?$/);
  });

  it("opens Wafanyakazi for whoever holds staff.manage on the whole shop (PPL-6)", async () => {
    answer("GET", ME, { status: 200, body: MANAGER });

    render(<OfficeHome />);

    const link = await screen.findByRole("link", { name: "Wafanyakazi" });
    expect(link.getAttribute("href")).toMatch(/^\/workers\/?$/);
  });

  it("offers no Wafanyakazi for staff.manage on one side alone", async () => {
    // A worker belongs to the shop, not a side: the routes ask the key on the whole shop (PPL-4), so a key
    // held on Dawa alone opens nothing there.
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["staff.manage"] }]),
    });

    render(<OfficeHome />);

    await screen.findByRole("link", { name: "Mipangilio ya duka" });
    expect(screen.queryByRole("link", { name: "Wafanyakazi" })).toBeNull();
  });

  it("says when there is nothing to open, for someone who works on no side", async () => {
    // Logged in, with no role on any side yet: no office work, not even the shop's rules.
    answer("GET", ME, { status: 200, body: whoIsHere([]) });

    render(<OfficeHome />);

    expect(
      await screen.findByText(
        "Bado hakuna kazi ya ofisi unayoweza kufungua hapa.",
      ),
    ).toBeTruthy();
    expect(
      screen.queryByRole("link", { name: "Mipangilio ya duka" }),
    ).toBeNull();
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
