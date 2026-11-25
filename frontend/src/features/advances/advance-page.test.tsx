// advance-page.test.tsx — one advance's own page (WAGE-8): whose, how much, the day, what it was for, who typed it and
// when; Batilisha, never on one's own; and, crossed out, struck through with who, when and why.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  advance,
  type AdvancePage,
  advancePageOf,
  advanceRoute,
  MENEJA,
} from "@/test/advances";
import { whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { router } from "@/test/router";

import { AdvanceScreen } from "./advance-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const JUMAS = advance();
const CROSSED = {
  ...JUMAS,
  voided: {
    by: "Baba",
    at: "2026-11-25T16:00:00Z",
    reason: "Sifuri moja zaidi",
  },
};

function thePageIs(body: AdvancePage) {
  answer("GET", ME, { status: 200, body: MENEJA });
  answer("GET", advanceRoute(body.advance.id), { status: 200, body });
}

function wordsOf(part: Element | null): string {
  return (part?.textContent ?? "").replace(/ /g, " ");
}

/** What the page says of it, line by line, its button too. */
async function facts(): Promise<string[]> {
  const card = await screen.findByRole("region", { name: "Advansi" });
  return [...card.querySelectorAll("p, button")].map(wordsOf);
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-25T09:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("one advance", () => {
  it("shows Juma's as Jack drew it", async () => {
    thePageIs(advancePageOf(JUMAS));

    render(<AdvanceScreen id={JUMAS.id} />);

    expect(await facts()).toEqual([
      "TSh 20,000",
      "Jumatano 25/11/2026",
      "Ada ya shule",
      "Imeandikwa na Meneja · 25/11/2026 10:42 asubuhi",
      "Batilisha",
    ]);
    expect(
      screen.getByRole("heading", { level: 1, name: "Advansi ya Juma" }),
    ).toBeTruthy();
  });

  it("leaves out what it was for when nobody said", async () => {
    thePageIs(advancePageOf({ ...JUMAS, note: "" }));

    render(<AdvanceScreen id={JUMAS.id} />);

    expect(await facts()).toEqual([
      "TSh 20,000",
      "Jumatano 25/11/2026",
      "Imeandikwa na Meneja · 25/11/2026 10:42 asubuhi",
      "Batilisha",
    ]);
  });

  it("shows one crossed out struck through, with who, when and why, and no Batilisha", async () => {
    thePageIs(advancePageOf(CROSSED));

    render(<AdvanceScreen id={JUMAS.id} />);

    expect(await facts()).toEqual([
      "TSh 20,000",
      "Jumatano 25/11/2026",
      "Ada ya shule",
      "Imeandikwa na Meneja · 25/11/2026 10:42 asubuhi",
      "Imebatilishwa na Baba, 25/11/2026",
      "Sababu: Sifuri moja zaidi",
    ]);
    expect([...document.querySelectorAll("s")].map(wordsOf)).toEqual([
      "TSh 20,000",
    ]);
  });

  it("says a ready reason's code in words, on the demo", async () => {
    thePageIs(
      advancePageOf(
        { ...CROSSED, voided: { ...CROSSED.voided, reason: "wrong_amount" } },
        { ready_void_reasons: ["wrong_amount"] },
      ),
    );

    render(<AdvanceScreen id={JUMAS.id} />);

    expect((await facts()).at(-1)).toBe("Sababu: Kiasi kimekosewa");
  });

  it("offers no Batilisha on one's own, and says who may", async () => {
    // Meneja's own 50,000, typed by Baba: nobody erases what they took (Jack: A).
    thePageIs(advancePageOf(JUMAS, { own: true }));

    render(<AdvanceScreen id={JUMAS.id} />);

    expect((await facts()).at(-1)).toBe(
      "Hii ni advansi yako. Mtu mwingine ndiye anayeweza kuibatilisha.",
    );
    expect(screen.queryByRole("button", { name: "Batilisha" })).toBeNull();
  });

  it("says nothing of who may on one's own that is crossed out already", async () => {
    thePageIs(advancePageOf(CROSSED, { own: true }));

    render(<AdvanceScreen id={JUMAS.id} />);

    expect((await facts()).at(-1)).toBe("Sababu: Sifuri moja zaidi");
  });

  it("offers no Batilisha once the pay it came off is approved, and says why", async () => {
    thePageIs(advancePageOf(JUMAS, { closed: true }));

    render(<AdvanceScreen id={JUMAS.id} />);

    expect((await facts()).at(-1)).toBe(
      "Malipo yake ya mwezi huo yamefungwa, kwa hiyo advansi hii haibatilishwi.",
    );
    expect(screen.queryByRole("button", { name: "Batilisha" })).toBeNull();
  });

  it("says the pay is approved on one's own too, not that someone else may", async () => {
    // Nobody may cross it out now, so "someone else" would send Meneja to ask Baba for nothing.
    thePageIs(advancePageOf(JUMAS, { own: true, closed: true }));

    render(<AdvanceScreen id={JUMAS.id} />);

    expect((await facts()).at(-1)).toMatch(/yamefungwa/);
    expect(screen.queryByText(/Hii ni advansi yako/)).toBeNull();
  });

  it("says nothing of the pay on one crossed out before it was approved", async () => {
    thePageIs(advancePageOf(CROSSED, { closed: true }));

    render(<AdvanceScreen id={JUMAS.id} />);

    expect((await facts()).at(-1)).toBe("Sababu: Sifuri moja zaidi");
  });

  it("crosses it out from its button, and shows it struck through with the keyboard on it", async () => {
    thePageIs(advancePageOf(JUMAS));
    render(<AdvanceScreen id={JUMAS.id} />);
    await facts();
    answer("POST", `${advanceRoute(JUMAS.id)}void/`, {
      status: 200,
      body: CROSSED,
    });
    thePageIs(advancePageOf(CROSSED));

    fireEvent.click(screen.getByRole("button", { name: "Batilisha" }));
    const sheet = screen.getByRole("dialog", {
      name: /^Batilisha TSh\s20,000$/,
    });
    fireEvent.change(within(sheet).getByLabelText("Sababu"), {
      target: { value: "Sifuri moja zaidi" },
    });
    fireEvent.click(within(sheet).getByRole("button", { name: "Batilisha" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect((await facts()).slice(-2)).toEqual([
      "Imebatilishwa na Baba, 25/11/2026",
      "Sababu: Sifuri moja zaidi",
    ]);
    // Its button is gone, so the keyboard is on the amount itself.
    await waitFor(() =>
      expect(wordsOf(document.activeElement)).toBe("TSh 20,000"),
    );
  });

  it("shows it crossed out when the answer was lost, and gives the keyboard to it on Ghairi", async () => {
    thePageIs(advancePageOf(JUMAS));
    render(<AdvanceScreen id={JUMAS.id} />);
    await facts();
    answer(
      "POST",
      `${advanceRoute(JUMAS.id)}void/`,
      refusal(503, "server_error"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Batilisha" }));
    const sheet = screen.getByRole("dialog");
    fireEvent.change(within(sheet).getByLabelText("Sababu"), {
      target: { value: "Sifuri moja zaidi" },
    });
    thePageIs(advancePageOf(CROSSED));
    fireEvent.click(within(sheet).getByRole("button", { name: "Batilisha" }));
    await within(sheet).findByRole("alert");
    await waitFor(() => expect(document.querySelectorAll("s")).toHaveLength(1));

    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));

    await waitFor(() =>
      expect(wordsOf(document.activeElement)).toBe("TSh 20,000"),
    );
  });

  it("closes the sheet, its reason with it, when the address moves to another advance", async () => {
    // The browser's back and forward move ?id= with the page still on the screen: Juma's reason never goes to Asha's
    // (the review).
    const hers = advance({ display_name: "Asha" });
    thePageIs(advancePageOf(JUMAS));
    thePageIs(advancePageOf(hers));
    // Both read already, as a person who went back and forth has, so the page has no wait between them.
    const { rerender } = render(<AdvanceScreen id={hers.id} />);
    await screen.findByRole("heading", { level: 1, name: "Advansi ya Asha" });
    rerender(<AdvanceScreen id={JUMAS.id} />);
    await screen.findByRole("heading", { level: 1, name: "Advansi ya Juma" });
    fireEvent.click(screen.getByRole("button", { name: "Batilisha" }));
    expect(screen.getByRole("dialog")).toBeTruthy();

    rerender(<AdvanceScreen id={hers.id} />);

    await screen.findByRole("heading", { level: 1, name: "Advansi ya Asha" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("gives the keyboard back to Batilisha on Ghairi", async () => {
    thePageIs(advancePageOf(JUMAS));
    render(<AdvanceScreen id={JUMAS.id} />);
    await facts();
    const button = screen.getByRole("button", { name: "Batilisha" });
    fireEvent.click(button);

    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Ghairi",
      }),
    );

    await waitFor(() => expect(document.activeElement).toBe(button));
  });

  it("says when the address names none, and asks nothing of it", async () => {
    answer("GET", ME, { status: 200, body: MENEJA });

    render(<AdvanceScreen id={null} />);

    expect(
      await screen.findByText("Hakuna advansi iliyochaguliwa."),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 1, name: "Advansi" }),
    ).toBeTruthy();
    expect(
      sent.filter((request) => request.url.includes("/advances/")),
    ).toEqual([]);
  });

  it("shows the server's refusal: no key, or one the shop doesn't have", async () => {
    for (const reply of [
      refusal(403, "permission_denied"),
      refusal(404, "not_found"),
    ]) {
      answer("GET", ME, { status: 200, body: whoIsHere([]) });
      answer("GET", advanceRoute(JUMAS.id), reply);

      const shown = render(<AdvanceScreen id={JUMAS.id} />);

      expect(await screen.findByRole("alert")).toBeTruthy();
      expect(screen.queryByRole("region", { name: "Advansi" })).toBeNull();
      shown.unmount();
    }
  });

  it("sends the arrow from a fresh tab to its own month's list", async () => {
    vi.spyOn(window.history, "length", "get").mockReturnValue(1);
    thePageIs(advancePageOf({ ...JUMAS, date: "2026-10-30" }));
    render(<AdvanceScreen id={JUMAS.id} />);
    await facts();

    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));

    expect(router.push).toHaveBeenCalledWith("/advances/?month=2026-10");
    vi.restoreAllMocks();
  });
});
