// office-home.test.tsx — the office's home page greets the person, with a big button for each office
// screen they may open (UI-5), Mipangilio ya duka (SHOP-5), Wafanyakazi (PPL-6) and Mahudhurio ya mwezi (ATT-5)
// among them.
import { QueryClientProvider } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import { WHO_IS_HERE } from "@/features/people/who-is-here";
import { MENEJA } from "@/test/advances";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal } from "@/test/fake-server";
import { WITH_THE_KEY } from "@/test/meals";
import { OWNER } from "@/test/pay";
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

  it("opens Tofauti for whoever may close a flag on some side (CTRL-4)", async () => {
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["flag.review"] }]),
    });

    render(<OfficeHome />);

    const link = await screen.findByRole("link", { name: "Tofauti" });
    expect(link.getAttribute("href")).toMatch(/^\/flags\/?$/);
  });

  it("offers no Tofauti to someone who may close none", async () => {
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["sale.write"] }]),
    });

    render(<OfficeHome />);

    await screen.findByRole("link", { name: "Mipangilio ya duka" });
    expect(screen.queryByRole("link", { name: "Tofauti" })).toBeNull();
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

  it("opens Mahudhurio ya mwezi for whoever holds attendance.manage on the whole shop (ATT-5)", async () => {
    // The owner and the managers fix attendance; the month is the whole shop's, Asha of Dawa beside Baraka of Vyakula.
    answer("GET", ME, {
      status: 200,
      body: {
        ...whoIsHere([]),
        permissions: {
          whole_shop: ["attendance.manage"],
          sides: [
            { ...DAWA, permissions: ["attendance.manage"] },
            { ...VYAKULA, permissions: ["attendance.manage"] },
          ],
        },
      },
    });

    render(<OfficeHome />);

    const link = await screen.findByRole("link", {
      name: "Mahudhurio ya mwezi",
    });
    expect(link.getAttribute("href")).toMatch(/^\/attendance-month\/?$/);
  });

  it("offers no Mahudhurio ya mwezi to a seller, nor for attendance.manage on one side alone", async () => {
    // Asha sells on Dawa: whose day was late is not hers to see. Hamisi fixes attendance on Dawa alone: the month is
    // the whole shop's, so the server would refuse him, and the button stays off his page.
    for (const permissions of [["sale.create"], ["attendance.manage"]]) {
      answer("GET", ME, {
        status: 200,
        body: whoIsHere([{ side: DAWA, permissions }]),
      });
      const shown = render(<OfficeHome />);
      await screen.findByRole("link", { name: "Mipangilio ya duka" });
      expect(
        screen.queryByRole("link", { name: "Mahudhurio ya mwezi" }),
      ).toBeNull();
      shown.unmount();
    }
  });

  it("opens Hela ya chakula for whoever the owner gave its key on the whole shop (WAGE-7)", async () => {
    answer("GET", ME, { status: 200, body: WITH_THE_KEY });

    render(<OfficeHome />);

    const link = await screen.findByRole("link", { name: "Hela ya chakula" });
    expect(link.getAttribute("href")).toMatch(/^\/meal-money\/?$/);
  });

  it("offers no Hela ya chakula without its key, nor for the key on one side alone", async () => {
    // A manager the owner hasn't given it: it is his to give (Jack, 15 Nov 2026). And the meals are the whole shop's, so
    // the server would refuse a key held on Dawa alone.
    for (const permissions of [["attendance.manage"], ["meals.record"]]) {
      answer("GET", ME, {
        status: 200,
        body: whoIsHere([{ side: DAWA, permissions }]),
      });
      const shown = render(<OfficeHome />);
      await screen.findByRole("link", { name: "Mipangilio ya duka" });
      expect(
        screen.queryByRole("link", { name: "Hela ya chakula" }),
      ).toBeNull();
      shown.unmount();
    }
  });

  it("opens Advansi for whoever may give a worker money before payday (WAGE-8)", async () => {
    // Meneja, with money.advance on the whole shop and neither key of pay: no Mishahara beside it.
    answer("GET", ME, { status: 200, body: MENEJA });

    render(<OfficeHome />);

    const link = await screen.findByRole("link", { name: "Advansi" });
    expect(link.getAttribute("href")).toMatch(/^\/advances\/?$/);
    expect(screen.queryByRole("link", { name: "Mishahara" })).toBeNull();
  });

  it("offers no Advansi without its key, nor for the key on one side alone", async () => {
    // Whoever sees the pay gives no money by it; and a worker's pay is the whole shop's, so the server would refuse a key
    // held on Dawa alone.
    for (const permissions of [
      ["settings.manage", "staff.manage"],
      ["money.advance"],
    ]) {
      answer("GET", ME, {
        status: 200,
        body: whoIsHere([{ side: DAWA, permissions }]),
      });
      const shown = render(<OfficeHome />);
      await screen.findByRole("link", { name: "Mipangilio ya duka" });
      expect(screen.queryByRole("link", { name: "Advansi" })).toBeNull();
      shown.unmount();
    }
  });

  it("opens Mishahara for whoever may see a worker's pay (WAGE-2)", async () => {
    answer("GET", ME, { status: 200, body: OWNER });

    render(<OfficeHome />);

    const link = await screen.findByRole("link", { name: "Mishahara" });
    expect(link.getAttribute("href")).toMatch(/^\/pay\/?$/);
  });

  it("offers no Mishahara without both keys of pay on the whole shop", async () => {
    // A manager who prepares the pay sees nobody's rate, and the pay shows it ("14 × 10,000"); nor one handed the shop's
    // rules alone, or the workers alone (Jack, WAGE-1); nor someone who holds both on Dawa alone.
    const both = ["settings.manage", "staff.manage"];
    for (const whole_shop of [["pay.run"], both.slice(0, 1), both.slice(1)]) {
      answer("GET", ME, {
        status: 200,
        body: {
          ...whoIsHere([]),
          permissions: {
            whole_shop,
            sides: [{ ...DAWA, permissions: whole_shop }],
          },
        },
      });
      const shown = render(<OfficeHome />);
      await screen.findByRole("link", { name: "Mipangilio ya duka" });
      expect(screen.queryByRole("link", { name: "Mishahara" })).toBeNull();
      shown.unmount();
    }
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: both }]),
    });
    render(<OfficeHome />);
    await screen.findByRole("link", { name: "Mipangilio ya duka" });
    expect(screen.queryByRole("link", { name: "Mishahara" })).toBeNull();
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

  it("opens Siku na malipo yangu for everyone, beside Mipangilio yangu: their own need no key (Jack: A, WAGE-4)", async () => {
    // Juma, a manager paid by the day, on his own phone with his password: his own days and pay are one tap away.
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["sale.create"] }]),
    });

    render(<OfficeHome />);

    const link = await screen.findByRole("link", {
      name: "Siku na malipo yangu",
    });
    expect(link.getAttribute("href")).toMatch(/^\/my-days-and-pay\/?$/);
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
