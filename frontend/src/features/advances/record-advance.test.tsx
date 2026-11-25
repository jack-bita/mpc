// record-advance.test.tsx — Andika advansi (WAGE-8): the button, and the sheet that types money given to a worker before
// payday; what the sheet sees itself is said at once, beside its box, and nothing is sent; the server's refusals show
// beside theirs; a try sent again carries the same id; and once saved, a line says what was written, with the keyboard
// on it.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  advance,
  ADVANCES_ROUTE,
  AdvancesAsked,
  advancesAreAnswered,
  advancesMonth,
  type AdvanceWorker,
  ASHA,
  JUMA,
  TODAY,
} from "@/test/advances";
import { answer, refusal, sent } from "@/test/fake-server";
import { PayAsked, payIsAnswered } from "@/test/pay";
import { render } from "@/test/render";

import { RecordAdvance } from "./record-advance";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

/** What the app sent, each as the server would read it. */
async function sentBodies(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map((request) => request.json() as Promise<Record<string, unknown>>),
  );
}

/** The error beside a box or a group: the one its aria-describedby names (field.tsx, choice.tsx). */
function errorOf(element: HTMLElement): string {
  const ids = element.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

const button = () => screen.getByRole("button", { name: "Andika advansi" });
const sheet = () => screen.getByRole("dialog", { name: "Andika advansi" });
const box = (label: string) => within(sheet()).getByLabelText(label);
const value = (label: string) => (box(label) as HTMLInputElement).value;
const save = () => within(sheet()).getByRole("button", { name: "Hifadhi" });
const workers = () =>
  within(sheet()).getByRole("radiogroup", { name: "Mfanyakazi" });

function type(label: string, typed: string) {
  fireEvent.change(box(label), { target: { value: typed } });
}

function pick(name: string) {
  fireEvent.click(within(workers()).getByRole("radio", { name }));
}

/** November's answer, as the page hands it down, unless told otherwise. */
const month = (offered: AdvanceWorker[], of = "2026-11") =>
  advancesMonth([], { month: of, workers: offered });

function openSheet({
  of = "2026-11",
  offered = [ASHA, JUMA],
}: { of?: string; offered?: AdvanceWorker[] } = {}) {
  const shown = render(<RecordAdvance month={month(offered, of)} />);
  fireEvent.click(button());
  return shown;
}

describe("Andika advansi", () => {
  it("sends who, the day, the amount and what it was for, then says what was written", async () => {
    answer("POST", ADVANCES_ROUTE, async (request) => {
      const body = (await request.clone().json()) as Record<string, string>;
      return Response.json(advance({ id: body.id, date: body.date }), {
        status: 201,
      });
    });
    openSheet();
    expect(value("Siku")).toBe(TODAY);

    pick("Juma");
    type("Kiasi (TSh)", "20,000");
    type("Maelezo (si lazima)", "Ada ya shule");
    fireEvent.click(save());

    const said = await screen.findByText(
      "Imeandikwa: TSh 20,000, Juma, Jumatano 25/11/2026.",
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    const [body, ...more] = await sentBodies();
    expect(more).toEqual([]);
    expect(body).toEqual({
      id: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-7/),
      staff: JUMA.staff,
      date: TODAY,
      amount: "20000",
      note: "Ada ya shule",
    });
    // The keyboard is on the line, so a screen reader says what was written.
    await waitFor(() =>
      expect(document.activeElement?.contains(said)).toBe(true),
    );
  });

  it.each([
    ["saved", 201],
    ["no answer", 503],
  ])(
    "asks the advances and the pay again, as both move: %s",
    async (_how, status) => {
      const asked = advancesAreAnswered();
      answer("POST", ADVANCES_ROUTE, { status, body: advance() });
      const payAsked = payIsAnswered();
      render(
        <>
          <AdvancesAsked />
          <PayAsked />
          <RecordAdvance month={month([JUMA])} />
        </>,
      );
      await waitFor(() => expect([asked(), payAsked()]).toEqual([1, [1, 1]]));
      fireEvent.click(button());

      pick("Juma");
      type("Kiasi (TSh)", "20000");
      fireEvent.click(save());

      await waitFor(() => expect([asked(), payAsked()]).toEqual([2, [2, 2]]));
    },
  );

  it("offers whom the server named, none picked, and says who left", () => {
    // Nobody's money goes to the first name by a careless tap. A person hired again has two jobs of one name, so the one
    // that ended says when.
    openSheet({
      offered: [ASHA, JUMA, { ...JUMA, staff: "old", left_on: "2026-11-14" }],
    });

    const rows = within(workers()).getAllByRole("radio");
    expect(rows.map((row) => row.getAttribute("aria-checked"))).toEqual([
      "false",
      "false",
      "false",
    ]);
    expect(within(workers()).getByRole("radio", { name: "Asha" })).toBeTruthy();
    expect(
      within(workers()).getByRole("radio", {
        name: "Juma (aliondoka 14/11/2026)",
      }),
    ).toBeTruthy();
  });

  it("says when there is nobody else to pick, and holds the main button", () => {
    // Meneja alone is paid by the day, and isn't offered their own: "nobody is paid by the day" would be untrue (the
    // review).
    openSheet({ offered: [] });

    expect(
      within(sheet()).getByText(
        "Hakuna mfanyakazi mwingine anayelipwa kwa siku katika mwezi huu.",
      ),
    ).toBeTruthy();
    expect((save() as HTMLButtonElement).disabled).toBe(true);
  });

  it("starts on no day for a month gone by, as today isn't in it, and offers no day to come", () => {
    openSheet({ of: "2026-10" });

    expect(value("Siku")).toBe("");
    expect(box("Siku").getAttribute("max")).toBe(TODAY);
  });

  it("waits, on the page, while the month it would type for is on its way", () => {
    // ‹ to a month not read yet: the button stays, held, and the line of the last save with it (the review).
    const { rerender } = render(<RecordAdvance month={undefined} />);
    expect((button() as HTMLButtonElement).disabled).toBe(true);

    rerender(<RecordAdvance month={month([JUMA])} />);

    expect((button() as HTMLButtonElement).disabled).toBe(false);
  });

  it("keeps an open sheet, and what is typed in it, while the month behind it changes", () => {
    // Midnight of the 1st crossed with the sheet open moves the page to another month: nothing typed is thrown away.
    const { rerender } = openSheet();
    pick("Juma");
    type("Kiasi (TSh)", "20000");

    rerender(<RecordAdvance month={undefined} />);

    expect(value("Kiasi (TSh)")).toBe("20000");
    expect(
      within(workers())
        .getByRole("radio", { name: "Juma" })
        .getAttribute("aria-checked"),
    ).toBe("true");
  });

  it("takes the shop's new today once the page reads it, the sheet still open", () => {
    // Opened at 23:59, sent at 00:01: the first of the two dates is no longer the last it may be (the review).
    const { rerender } = openSheet();
    expect(box("Siku").getAttribute("max")).toBe(TODAY);

    rerender(
      <RecordAdvance
        month={advancesMonth([], { today: "2026-11-26", workers: [JUMA] })}
      />,
    );

    expect(box("Siku").getAttribute("max")).toBe("2026-11-26");
  });

  it.each([
    ["", "20000", "Siku", "Jaza sehemu hii."],
    ["2026-11-26", "20000", "Siku", "Siku hii bado haijafika."],
    [
      TODAY,
      "",
      "Kiasi (TSh)",
      "Andika kiasi cha shilingi nzima, zaidi ya sifuri.",
    ],
    [
      TODAY,
      "0",
      "Kiasi (TSh)",
      "Andika kiasi cha shilingi nzima, zaidi ya sifuri.",
    ],
    [
      TODAY,
      "20000.50",
      "Kiasi (TSh)",
      "Andika kiasi cha shilingi nzima, zaidi ya sifuri.",
    ],
  ])(
    "says a wrong box at once, and sends nothing: %s, %s",
    async (day, amount, label, sentence) => {
      openSheet();

      pick("Juma");
      type("Siku", day);
      type("Kiasi (TSh)", amount);
      fireEvent.click(save());

      await waitFor(() => expect(errorOf(box(label))).toBe(sentence));
      expect(sent).toEqual([]);
    },
  );

  it("says it when nobody is picked, and sends nothing", async () => {
    openSheet();

    type("Kiasi (TSh)", "20000");
    fireEvent.click(save());

    await waitFor(() => expect(errorOf(workers())).toBe("Jaza sehemu hii."));
    expect(sent).toEqual([]);
  });

  it("takes a Sunday, as money is asked for on any day", async () => {
    answer("POST", ADVANCES_ROUTE, { status: 201, body: advance() });
    openSheet();

    pick("Juma");
    type("Siku", "2026-11-22");
    type("Kiasi (TSh)", "20000");
    fireEvent.click(save());

    await waitFor(() => expect(sent).toHaveLength(1));
  });

  it("shows the server's refusals beside their boxes", async () => {
    answer(
      "POST",
      ADVANCES_ROUTE,
      refusal(
        400,
        "invalid",
        {},
        {
          staff: ["advance.not_paid_by_day"],
          date: ["advance.outside_job"],
          amount: ["advance.amount_too_big"],
          note: ["demo.no_note"],
        },
      ),
    );
    openSheet();

    pick("Juma");
    type("Kiasi (TSh)", "50000000");
    fireEvent.click(save());

    await waitFor(() =>
      expect(errorOf(box("Kiasi (TSh)"))).toBe(
        "Kiasi hiki ni kikubwa mno. Angalia sifuri zake.",
      ),
    );
    expect(errorOf(workers())).toBe("Mfanyakazi huyu halipwi kwa siku.");
    expect(errorOf(box("Siku"))).toBe(
      "Siku hii ni kabla ya siku yake ya kwanza kazini, au baada ya siku yake ya mwisho.",
    );
    expect(errorOf(box("Maelezo (si lazima)"))).toBe(
      "Kwenye demo, maelezo hayahifadhiwi. Acha kisanduku hiki wazi.",
    );
  });

  it("shows a refusal of the whole request, and of a field with no box, above the buttons", async () => {
    // One's own, sent all the same; or the id clashes, which no box is about.
    answer("POST", ADVANCES_ROUTE, refusal(400, "advance.own"));
    openSheet();
    pick("Juma");
    type("Kiasi (TSh)", "20000");
    fireEvent.click(save());
    await waitFor(() =>
      expect(within(sheet()).getByRole("alert").textContent).toContain(
        "Huwezi kuandika wala kubatilisha advansi yako mwenyewe.",
      ),
    );

    answer(
      "POST",
      ADVANCES_ROUTE,
      refusal(400, "invalid", {}, { id: ["id.taken"] }),
    );
    fireEvent.click(save());
    await waitFor(() =>
      expect(within(sheet()).getByRole("alert").textContent).toContain(
        "Namba ya utambulisho imeshatumika",
      ),
    );
  });

  it("shows only what the last try found, never the one before's refusal", async () => {
    answer("POST", ADVANCES_ROUTE, refusal(400, "advance.own"));
    openSheet();
    pick("Juma");
    type("Kiasi (TSh)", "20000");
    fireEvent.click(save());
    await within(sheet()).findByRole("alert");

    type("Kiasi (TSh)", "");
    fireEvent.click(save());

    await waitFor(() =>
      expect(errorOf(box("Kiasi (TSh)"))).toBe(
        "Andika kiasi cha shilingi nzima, zaidi ya sifuri.",
      ),
    );
    expect(within(sheet()).queryByRole("alert")).toBeNull();
  });

  it("sends the same try again under the same id, and a changed one under a new id", async () => {
    // The answer was lost on the way: the same try must find the row the first made, never give the money twice. Another
    // worker is another row, for the list to show beside the first.
    answer("POST", ADVANCES_ROUTE, refusal(503, "server_error"));
    openSheet();
    pick("Juma");
    type("Kiasi (TSh)", "20000");
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(1));
    await within(sheet()).findByRole("alert");
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(2));
    await waitFor(() => expect(save().getAttribute("disabled")).toBeNull());
    pick("Asha");
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(3));

    const ids = (await sentBodies()).map((body) => body.id);
    expect(ids[0]).toBe(ids[1]);
    expect(ids[2]).not.toBe(ids[0]);
  });

  it("closes on Ghairi with nothing sent, the keyboard back on the button", async () => {
    openSheet();
    pick("Juma");
    type("Kiasi (TSh)", "20000");

    fireEvent.click(within(sheet()).getByRole("button", { name: "Ghairi" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(sent).toEqual([]);
    await waitFor(() => expect(document.activeElement).toBe(button()));
    // Opened again, the boxes are empty: nothing half-typed is kept.
    fireEvent.click(button());
    expect(value("Kiasi (TSh)")).toBe("");
  });

  it("holds the main button with no network, so nothing waits unsent", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    openSheet();

    expect((save() as HTMLButtonElement).disabled).toBe(true);
  });
});
