// setting-form.test.tsx — Badilisha (SHOP-5): a rule's new value from a day on. The box fits the rule's kind, and
// "1,000" typed goes as "1000" (ADR-0024); the day starts at the shop's today; a box left empty, not a number, or
// a day already past is said at once, beside its box, and nothing is sent; a value the server refuses has its
// Swahili sentence beside its box (the card's third Done when); and a try sent again keeps its id (ADR-0007).
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DAWA } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { line, row, TODAY } from "@/test/settings";

import type { RuleLine } from "./rules";
import { SettingForm, startingText, typedValue } from "./setting-form";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const RULES = "/api/v1/shops/settings/";
const TOMORROW = "2026-11-16";

/** The late fine's line at 1,000, the form opened on it. */
function openOn(
  fine: RuleLine = line(),
  key: Parameters<typeof SettingForm>[0]["ruleKey"] = "attendance.late_fine",
) {
  const onSaved = vi.fn();
  const onCancel = vi.fn();
  render(
    <SettingForm
      ruleKey={key}
      line={fine}
      today={TODAY}
      onSaved={onSaved}
      onCancel={onCancel}
    />,
  );
  return { onSaved, onCancel };
}

/** What the app sent to save a value, as the server would read it. */
async function sentBodies(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map((request) => request.json() as Promise<Record<string, unknown>>),
  );
}

/** The error beside a box: the one its aria-describedby names, after its hint, if it has one (field.tsx). */
function errorOf(box: HTMLElement): string {
  const ids = box.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

/** Types `text` into a box, in place of what was there, as a person who cleared it first. */
function typeInto(box: HTMLElement, text: string) {
  fireEvent.change(box, { target: { value: text } });
}

/** Taps a button, or anything else that takes a tap. */
function tap(element: HTMLElement) {
  fireEvent.click(element);
}

const amountBox = () => screen.getByLabelText("Kiasi kipya (TSh)");
const dayBox = () => screen.getByLabelText("Kuanzia tarehe");
const save = () => screen.getByRole("button", { name: "Hifadhi" });

describe("what is typed, as the server takes it", () => {
  it.each([
    ["money", "1,000", "1000"],
    ["money", "1 000", "1000"],
    ["money", "1,000,000", "1000000"],
    ["money", "1,000.50", "1000.50"],
    ["money", " 1,000 ", "1000"],
    ["money", "2500", "2500"],
    ["money", "0.50", "0.50"],
    ["percent", "2.5", "2.5"],
    ["whole", "1,440", "1440"],
    ["time", "08:00", "08:00"],
    ["yes_no", "true", "true"],
  ] as const)("%s: %s goes as %s", (kind, typed, value) => {
    expect(typedValue(kind, typed)).toBe(value);
  });

  it.each([
    ["money", "elfu moja"],
    ["money", "1000.505"],
    ["money", "-500"],
    ["percent", "2,5.0.1"],
    // A decimal comma, as much of the world writes two and a half: as 25 it would be ten times what was meant.
    ["percent", "2,5"],
    ["money", "12,34"],
    ["money", "1,0000"],
    ["whole", "1,44"],
    ["whole", "1.5"],
    ["time", "8"],
    ["yes_no", "ndiyo"],
  ] as const)("%s: %s is not a value of its kind", (kind, typed) => {
    expect(typedValue(kind, typed)).toBeNull();
  });

  it("starts the box at today's value, the zeros at the end of an amount left off", () => {
    expect(startingText("money", "1000.00")).toBe("1000");
    expect(startingText("money", "0.50")).toBe("0.5");
    expect(startingText("percent", "2.50")).toBe("2.5");
    expect(startingText("whole", "15")).toBe("15");
    expect(startingText("time", "07:35")).toBe("07:35");
  });
});

describe("Badilisha", () => {
  it("sends the late fine's 2,000 from tomorrow, as text with no commas, under its own id", async () => {
    // The card's first Done when: the owner sets the late fine to 2,000 from tomorrow.
    const saved = row({ value: "2000.00", effective_from: TOMORROW });
    answer("POST", RULES, { status: 201, body: saved });
    const { onSaved } = openOn();

    typeInto(amountBox(), "2,000");
    typeInto(dayBox(), TOMORROW);
    typeInto(
      screen.getByLabelText("Maelezo (si lazima)"),
      "Mkutano wa Novemba",
    );
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    const [body] = await sentBodies();
    expect(body).toEqual({
      id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      key: "attendance.late_fine",
      value: "2000",
      effective_from: TOMORROW,
      note: "Mkutano wa Novemba",
    });
    // A shop's rule names no side: the server refuses one (setting.side_not_allowed).
    expect(body).not.toHaveProperty("side");
  });

  it("opens on today's value and the shop's today, and offers no earlier day", () => {
    openOn();

    expect((amountBox() as HTMLInputElement).value).toBe("1000");
    expect((dayBox() as HTMLInputElement).value).toBe(TODAY);
    expect(dayBox().getAttribute("min")).toBe(TODAY);
    // The keypad with a point, on a phone.
    expect(amountBox().getAttribute("inputmode")).toBe("decimal");
  });

  it("names the side of a side's rule", async () => {
    answer("POST", RULES, {
      status: 201,
      body: row({ key: "cash.tolerance", side: DAWA.id, value: "500.00" }),
    });
    const { onSaved } = openOn(
      line({
        key: "cash.tolerance",
        scope: "side",
        side: DAWA.id,
        default: "0.00",
      }),
      "cash.tolerance",
    );

    typeInto(amountBox(), "500");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [body] = await sentBodies();
    expect(body).toMatchObject({
      key: "cash.tolerance",
      side: DAWA.id,
      value: "500",
    });
  });

  it("says an empty box at once, beside it, and sends nothing", async () => {
    openOn();

    typeInto(amountBox(), "");
    tap(save());

    expect(errorOf(amountBox())).toBe("Andika thamani.");
    expect(amountBox().getAttribute("aria-invalid")).toBe("true");
    expect(await sentBodies()).toEqual([]);
  });

  it("says a box that isn't an amount at all, and sends nothing", async () => {
    openOn();

    typeInto(amountBox(), "elfu mbili");
    tap(save());

    expect(errorOf(amountBox())).toBe("Thamani hii haifai kwa kanuni hii.");
    expect(await sentBodies()).toEqual([]);
  });

  it("says a day before today, typed by hand, and sends nothing", async () => {
    openOn();

    typeInto(dayBox(), "2026-11-01");
    tap(save());

    expect(errorOf(dayBox())).toBe("Thamani mpya haiwezi kuanza kabla ya leo.");
    expect(await sentBodies()).toEqual([]);
  });

  it("shows the server's refusal of a value in Swahili, beside its box (the card's third Done when)", async () => {
    // Idle minutes of 0: the server's rule (1 to 1,440) is the server's to check.
    answer(
      "POST",
      RULES,
      refusal(400, "invalid", {}, { value: ["setting.value_invalid"] }),
    );
    openOn(
      line({
        key: "session.idle_minutes",
        kind: "whole",
        default: "15",
        value: "15",
      }),
      "session.idle_minutes",
    );

    const box = screen.getByLabelText("Namba mpya");
    typeInto(box, "0");
    tap(save());

    await waitFor(() =>
      expect(errorOf(box)).toBe("Thamani hii haifai kwa kanuni hii."),
    );
    // Said beside its box only: no second alert repeats it in other words.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the server's refusal of a day beside the date box", async () => {
    // The shop's day turned at midnight while the form was open: the server's today is later than the page's.
    answer(
      "POST",
      RULES,
      refusal(400, "invalid", {}, { effective_from: ["setting.date_past"] }),
    );
    openOn();

    tap(save());

    await waitFor(() =>
      expect(errorOf(dayBox())).toBe(
        "Thamani mpya haiwezi kuanza kabla ya leo.",
      ),
    );
  });

  it("clears the last send's refusal at the next tap, so no old sentence stays beside a box (SHOP-5's review)", async () => {
    // The server refused the day; the owner then empties the amount and taps again. Only the empty box is said now:
    // the day's old refusal was about the last send.
    answer(
      "POST",
      RULES,
      refusal(400, "invalid", {}, { effective_from: ["setting.date_past"] }),
    );
    openOn();
    tap(save());
    await waitFor(() =>
      expect(errorOf(dayBox())).toBe(
        "Thamani mpya haiwezi kuanza kabla ya leo.",
      ),
    );

    typeInto(amountBox(), "");
    tap(save());

    expect(errorOf(amountBox())).toBe("Andika thamani.");
    expect(errorOf(dayBox())).toBe("");
  });

  it("says a refusal about a field it has no place for, never hiding it (SHOP-5's review)", async () => {
    // A newer server refuses a field this app doesn't send or know: the alert says it, in the plain sentence.
    answer(
      "POST",
      RULES,
      refusal(400, "invalid", {}, { unit: ["setting.value_invalid"] }),
    );
    openOn();

    tap(save());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Baadhi ya sehemu si sahihi.",
    );
  });

  it("says a refusal about the rule itself, which no box shows, in its own sentence", async () => {
    // A side the page sent that the server says a shop's rule can't have: the app and the server disagree.
    answer(
      "POST",
      RULES,
      refusal(400, "invalid", {}, { side: ["setting.side_not_allowed"] }),
    );
    openOn();

    tap(save());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Kanuni hii ni moja kwa duka zima, si kwa upande mmoja.",
    );
  });

  it("sends a try again under the same id, so a lost answer never makes a second row", async () => {
    // The first send's answer is lost on the way back; the owner taps Hifadhi again.
    let tries = 0;
    answer("POST", RULES, () => {
      tries += 1;
      if (tries === 1) throw new TypeError("Failed to fetch");
      return Response.json(row({ value: "2000.00" }), { status: 201 });
    });
    const { onSaved } = openOn();

    typeInto(amountBox(), "2000");
    tap(save());
    await screen.findByRole("alert");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [first, second] = await sentBodies();
    expect(second?.id).toBe(first?.id);
  });

  it("sends a changed value under a new id, so the server never answers with the old one (SHOP-5's review)", async () => {
    // 2,000 is saved, but the answer is lost on the way back. The owner makes it 2,500 and taps Hifadhi again. Under the
    // old id, the server would answer with the stored 2,000, and the page would say Imehifadhiwa for 2,500.
    let tries = 0;
    answer("POST", RULES, () => {
      tries += 1;
      if (tries === 1) throw new TypeError("Failed to fetch");
      return Response.json(row({ value: "2500.00" }), { status: 201 });
    });
    const { onSaved } = openOn();

    typeInto(amountBox(), "2000");
    tap(save());
    await screen.findByRole("alert");
    typeInto(amountBox(), "2500");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [first, second] = await sentBodies();
    expect([first?.value, second?.value]).toEqual(["2000", "2500"]);
    expect(second?.id).not.toBe(first?.id);
  });

  it("offers Ndiyo and Hapana for a yes or no, and sends the one picked", async () => {
    answer("POST", RULES, {
      status: 201,
      body: row({ key: "stock.block_negative", side: DAWA.id, value: "true" }),
    });
    const { onSaved } = openOn(
      line({
        key: "stock.block_negative",
        kind: "yes_no",
        scope: "side",
        side: DAWA.id,
        default: "false",
        value: "false",
      }),
      "stock.block_negative",
    );

    tap(screen.getByRole("radio", { name: "Ndiyo" }));
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [body] = await sentBodies();
    expect(body).toMatchObject({ value: "true", side: DAWA.id });
  });

  it("starts the keyboard on a yes or no's picked choice, as on any other box (SHOP-5's review)", () => {
    // The Badilisha button that had the keyboard is gone as the form opens: without this it falls to the page's start.
    openOn(
      line({
        key: "stock.block_negative",
        kind: "yes_no",
        scope: "side",
        side: DAWA.id,
        default: "false",
        value: "false",
      }),
      "stock.block_negative",
    );

    expect(document.activeElement).toBe(
      screen.getByRole("radio", { name: "Hapana" }),
    );
  });

  it("starts the keyboard in the box of any other kind", () => {
    openOn();

    expect(document.activeElement).toBe(amountBox());
  });

  it("gives a time the phone's own clock box", () => {
    openOn(
      line({
        key: "attendance.on_time_until",
        kind: "time",
        default: "07:35",
        value: "07:35",
      }),
      "attendance.on_time_until",
    );

    const box = screen.getByLabelText("Saa mpya");
    expect(box.getAttribute("type")).toBe("time");
    expect((box as HTMLInputElement).value).toBe("07:35");
  });

  it("closes on Ghairi, with nothing sent", async () => {
    const { onCancel } = openOn();

    tap(screen.getByRole("button", { name: "Ghairi" }));

    expect(onCancel).toHaveBeenCalled();
    expect(await sentBodies()).toEqual([]);
  });
});
