// worker-form.test.tsx — Ongeza (PPL-6): a new worker joins the shop. Juma's four boxes go under the form's own id;
// the first day starts at today, and a day far from it is asked about once; what the form can see is said at once,
// beside its box, and nothing is sent; a nickname taken shows beside Jina la kuitwa; a try sent again keeps its id, a
// changed one gets a new id (ADR-0007).
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { STAFF, worker } from "@/test/workers";

import { WorkerForm } from "./worker-form";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

/** The shop's today in these tests: Wednesday 18 Nov 2026. */
const TODAY = "2026-11-18";

/** The form, opened on the shop's today. */
function openForm() {
  const onSaved = vi.fn();
  const onCancel = vi.fn();
  render(<WorkerForm today={TODAY} onSaved={onSaved} onCancel={onCancel} />);
  return { onSaved, onCancel };
}

/** What the app sent to add a worker, as the server would read it. */
async function sentBodies(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map((request) => request.json() as Promise<Record<string, unknown>>),
  );
}

/** The error beside a box: the one its aria-describedby names, after its hint (field.tsx). */
function errorOf(box: HTMLElement): string {
  const ids = box.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

/** Types `text` into a box, in place of what was there. A date box takes the day as "2026-11-20". */
function typeInto(box: HTMLElement, text: string) {
  fireEvent.change(box, { target: { value: text } });
}

function tap(element: HTMLElement) {
  fireEvent.click(element);
}

const fullNameBox = () => screen.getByLabelText("Jina kamili");
const nicknameBox = () => screen.getByLabelText("Jina la kuitwa");
const jobTitleBox = () => screen.getByLabelText("Kazi");
const firstDayBox = () => screen.getByLabelText("Siku ya kwanza");
const save = () => screen.getByRole("button", { name: "Hifadhi" });

/** Juma, typed in: his names and his title, starting today. */
function typeJuma() {
  typeInto(fullNameBox(), "Juma Mfano");
  typeInto(nicknameBox(), "Juma");
  typeInto(jobTitleBox(), "Muuzaji wa dawa");
}

describe("Ongeza", () => {
  it("sends Juma's four boxes under the form's own id (the card's second Done when)", async () => {
    const juma = worker();
    answer("POST", STAFF, { status: 201, body: juma });
    const { onSaved } = openForm();

    typeInto(fullNameBox(), "  Juma Mfano ");
    typeInto(nicknameBox(), " Juma");
    typeInto(jobTitleBox(), "Muuzaji wa dawa ");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(juma));
    const [body] = await sentBodies();
    // The spaces around each off, as the server keeps them; the first day today, as the box started.
    expect(body).toEqual({
      id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      full_name: "Juma Mfano",
      display_name: "Juma",
      job_title: "Muuzaji wa dawa",
      started_on: TODAY,
    });
  });

  it("starts the first day at today, and the keyboard in Jina kamili", () => {
    // Most workers are added the morning they start.
    openForm();

    expect((firstDayBox() as HTMLInputElement).value).toBe(TODAY);
    expect(document.activeElement).toBe(fullNameBox());
  });

  it("sends an empty job title, as many workers have none beyond their role", async () => {
    answer("POST", STAFF, { status: 201, body: worker() });
    const { onSaved } = openForm();

    typeInto(fullNameBox(), "Juma Mfano");
    typeInto(nicknameBox(), "Juma");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [body] = await sentBodies();
    expect(body).toMatchObject({ job_title: "" });
  });

  it("says an empty name and nickname at once, beside their boxes, and sends nothing", async () => {
    openForm();

    // Spaces alone are no name, as the server says too.
    typeInto(nicknameBox(), "   ");
    tap(save());

    expect(errorOf(fullNameBox())).toBe("Sehemu hii haiwezi kuwa tupu.");
    expect(errorOf(nicknameBox())).toBe("Sehemu hii haiwezi kuwa tupu.");
    expect(await sentBodies()).toEqual([]);
  });

  it("says an emptied first day at once, and sends nothing", async () => {
    openForm();

    typeJuma();
    typeInto(firstDayBox(), "");
    tap(save());

    expect(errorOf(firstDayBox())).toBe("Jaza sehemu hii.");
    expect(await sentBodies()).toEqual([]);
  });

  it("asks once about a first day far from today, and sends it on the second Hifadhi", async () => {
    // 2025 for 2026: a year typed wrong would start every count in the wrong place.
    answer("POST", STAFF, { status: 201, body: worker() });
    const { onSaved } = openForm();

    typeJuma();
    typeInto(firstDayBox(), "2025-11-18");
    tap(save());

    expect(screen.getByRole("status").textContent).toBe(
      "18/11/2025 iko mbali na leo. Kama ni sahihi, bonyeza Hifadhi tena.",
    );
    expect(await sentBodies()).toEqual([]);

    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [body] = await sentBodies();
    expect(body).toMatchObject({ started_on: "2025-11-18" });
  });

  it("asks again about a different far day, and never about a day within a month", async () => {
    openForm();

    typeJuma();
    typeInto(firstDayBox(), "2025-11-18");
    tap(save());
    // Changed to another far day: the owner's yes was to the first one only.
    typeInto(firstDayBox(), "2027-01-04");
    expect(screen.getByRole("status").textContent).toBe("");
    tap(save());

    expect(screen.getByRole("status").textContent).toBe(
      "04/01/2027 iko mbali na leo. Kama ni sahihi, bonyeza Hifadhi tena.",
    );
    expect(await sentBodies()).toEqual([]);
  });

  it("sends a first day within a month of today at once", async () => {
    // Thirty days back: a worker added late, in his first month.
    answer("POST", STAFF, { status: 201, body: worker() });
    const { onSaved } = openForm();

    typeJuma();
    typeInto(firstDayBox(), "2026-10-19");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("shows a nickname another worker has beside Jina la kuitwa, though it is the whole request's code", async () => {
    // The database's rule is of lower(display_name), no field (PPL-4); the owner fixes it in that box.
    answer("POST", STAFF, refusal(400, "staff.display_name_taken"));
    openForm();

    typeJuma();
    tap(save());

    await waitFor(() =>
      expect(errorOf(nicknameBox())).toBe(
        "Mfanyakazi mwingine tayari ana jina hili la kuitwa. Chagua jingine.",
      ),
    );
    // Said beside its box only: no alert repeats it above the buttons.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the server's refusal of a box beside it", async () => {
    answer(
      "POST",
      STAFF,
      refusal(400, "invalid", {}, { full_name: ["blank"] }),
    );
    openForm();

    typeJuma();
    tap(save());

    await waitFor(() =>
      expect(errorOf(fullNameBox())).toBe("Sehemu hii haiwezi kuwa tupu."),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows an id another shop holds above the buttons, as no box owns it", async () => {
    answer("POST", STAFF, refusal(409, "id.taken"));
    openForm();

    typeJuma();
    tap(save());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Namba ya utambulisho imeshatumika. Jaribu tena.",
    );
  });

  it("sends a try again under the same id, so a lost answer never makes a second Juma", async () => {
    // The first send's answer is lost on the way back; the owner taps Hifadhi again.
    let tries = 0;
    answer("POST", STAFF, () => {
      tries += 1;
      if (tries === 1) throw new TypeError("Failed to fetch");
      return Response.json(worker(), { status: 201 });
    });
    const { onSaved } = openForm();

    typeJuma();
    tap(save());
    await screen.findByRole("alert");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [first, second] = await sentBodies();
    expect(second?.id).toBe(first?.id);
  });

  it("sends a changed nickname under a new id, so the server never answers with the stored worker", async () => {
    let tries = 0;
    answer("POST", STAFF, () => {
      tries += 1;
      if (tries === 1) throw new TypeError("Failed to fetch");
      return Response.json(worker(), { status: 201 });
    });
    const { onSaved } = openForm();

    typeJuma();
    tap(save());
    await screen.findByRole("alert");
    typeInto(nicknameBox(), "Juma M");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [first, second] = await sentBodies();
    expect(second?.id).not.toBe(first?.id);
  });

  it("switches Hifadhi off while there is no network, so nothing waits unsent while it looks saved", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    openForm();

    expect((save() as HTMLButtonElement).disabled).toBe(true);
  });

  it("closes on Ghairi, with nothing sent", async () => {
    const { onCancel } = openForm();

    typeJuma();
    tap(screen.getByRole("button", { name: "Ghairi" }));

    expect(onCancel).toHaveBeenCalled();
    expect(await sentBodies()).toEqual([]);
  });
});
