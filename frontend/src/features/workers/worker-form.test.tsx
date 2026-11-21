// worker-form.test.tsx — Ongeza (PPL-6): a new worker joins the shop. Juma's four boxes go under the form's own id;
// the first day starts at today, and a day far from it is asked about once; what the form can see is said at once,
// beside its box, and nothing is sent; a nickname taken shows beside Jina la kuitwa; a try sent again keeps its id, a
// changed one gets a new id (ADR-0007). And Simu (PPL-11): a new worker's phone; a phone in use beside its box; the
// phone of a worker who left, which names him and offers Mwajiri tena; and no phone on the demo.
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

/** The form, opened on the shop's today, as Mfanyakazi mpya draws it, with no Ghairi (UI-11); on the demo if told
 * so. */
function openForm({ demo = false }: { demo?: boolean } = {}) {
  const onSaved = vi.fn();
  render(<WorkerForm today={TODAY} demo={demo} onSaved={onSaved} />);
  return { onSaved };
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
const phoneBox = () => screen.getByLabelText("Simu") as HTMLInputElement;
/** The question about a far first day: the first of the form's two lines in words, under Siku ya kwanza (the second,
 * under Simu, names a worker who left). */
const dayQuestion = () => screen.getAllByRole("status")[0]!;
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

    expect(dayQuestion().textContent).toBe(
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
    expect(dayQuestion().textContent).toBe("");
    tap(save());

    expect(dayQuestion().textContent).toBe(
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

  it("has no Ghairi on a page of its own, whose arrow leaves (UI-11)", () => {
    openForm();

    expect(screen.queryByRole("button", { name: "Ghairi" })).toBeNull();
  });

  it("closes on Ghairi, with nothing sent, where a worker's page asks for one (Mwajiri tena, until it has a page)", async () => {
    const onCancel = vi.fn();
    render(<WorkerForm today={TODAY} onSaved={vi.fn()} onCancel={onCancel} />);

    typeJuma();
    tap(screen.getByRole("button", { name: "Ghairi" }));

    expect(onCancel).toHaveBeenCalled();
    expect(await sentBodies()).toEqual([]);
  });
});

/** Baraka's job that ended on 12 Mar 2026, as the server names it when his phone is typed (staff.left_here). */
const BARAKAS_OLD_JOB = "019a8302-0000-7000-8000-0000000000aa";

/** The server's answer to Baraka's phone typed on Ongeza: nothing made, and his old job named. */
const HIS_PHONE = refusal(400, "staff.left_here", {
  staff: BARAKAS_OLD_JOB,
  full_name: "Baraka Mfano",
  left_on: "2026-03-12",
});

/** Baba, who forgot Baraka worked here, types him in as new, with his phone. */
function typeBaraka() {
  typeInto(fullNameBox(), "Baraka Mfano");
  typeInto(nicknameBox(), "Baraka");
  typeInto(jobTitleBox(), "Muuzaji");
  typeInto(phoneBox(), "0712 345 678");
}

describe("Simu on Ongeza", () => {
  it("sends a new worker's phone as typed, for the server to store in its one form (the card's third Done when)", async () => {
    answer("POST", STAFF, { status: 201, body: worker() });
    const { onSaved } = openForm();

    typeJuma();
    typeInto(phoneBox(), " 0754 000 111 ");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [body] = await sentBodies();
    expect(body?.phone).toBe("0754 000 111");
  });

  it("shows a phone in use beside Simu, saying nothing of whose", async () => {
    answer("POST", STAFF, refusal(400, "invalid", {}, { phone: ["unique"] }));
    openForm();

    typeJuma();
    typeInto(phoneBox(), "0754 000 111");
    tap(save());

    await waitFor(() => expect(errorOf(phoneBox())).toBe("Hiki tayari kipo."));
  });

  it("names the worker who left whose phone it is, and offers Mwajiri tena, without saying it in red", async () => {
    answer("POST", STAFF, HIS_PHONE);
    openForm();

    typeBaraka();
    tap(save());

    expect(
      await screen.findByText(
        "Simu hii ni ya Baraka Mfano, aliyeondoka 12/03/2026.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Mwajiri tena" })).toBeTruthy();
    // A question, not a refusal: no alert above the buttons.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("hires him again with the boxes typed, his old job named, and no second person (the card's second Done when)", async () => {
    const back = worker({ full_name: "Baraka Mfano", display_name: "Baraka" });
    let tries = 0;
    answer("POST", STAFF, () => {
      tries += 1;
      return tries === 1
        ? Response.json(HIS_PHONE.body, { status: 400 })
        : Response.json(back, { status: 201 });
    });
    const { onSaved } = openForm();

    typeBaraka();
    tap(save());
    tap(await screen.findByRole("button", { name: "Mwajiri tena" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(back));
    const [, again] = await sentBodies();
    // The same person keeps his own full name and phone: neither is sent.
    expect(again).toEqual({
      id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      hire_again: BARAKAS_OLD_JOB,
      display_name: "Baraka",
      job_title: "Muuzaji",
      started_on: TODAY,
    });
  });

  it("says a first day before his last day at once, beside its box, and hires nobody", async () => {
    answer("POST", STAFF, HIS_PHONE);
    openForm();

    typeBaraka();
    typeInto(firstDayBox(), "2026-03-01");
    tap(save());
    // Far from today: asked about once first, as for any new worker.
    tap(save());
    tap(await screen.findByRole("button", { name: "Mwajiri tena" }));

    expect(errorOf(firstDayBox())).toBe(
      "Siku ya kwanza haiwezi kuwa kabla ya siku yake ya mwisho ya kazi iliyopita.",
    );
    expect((await sentBodies()).length).toBe(1);
  });

  it("keeps Mwajiri tena after a hire again whose answer was lost, and sends it again under the same id (the review)", async () => {
    // The network drops on the way back: the server may have hired him. Tried again, the same id gets the job the
    // first made, never a second (ADR-0007), and Baba is never left with only Hifadhi, a new add, to try.
    const back = worker({ full_name: "Baraka Mfano", display_name: "Baraka" });
    let tries = 0;
    answer("POST", STAFF, () => {
      tries += 1;
      if (tries === 1) return Response.json(HIS_PHONE.body, { status: 400 });
      if (tries === 2) throw new TypeError("Failed to fetch");
      return Response.json(back, { status: 201 });
    });
    const { onSaved } = openForm();

    typeBaraka();
    tap(save());
    tap(await screen.findByRole("button", { name: "Mwajiri tena" }));
    await screen.findByRole("alert");
    expect(
      screen.getByText("Simu hii ni ya Baraka Mfano, aliyeondoka 12/03/2026."),
    ).toBeTruthy();
    tap(screen.getByRole("button", { name: "Mwajiri tena" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(back));
    const [, lost, again] = await sentBodies();
    expect(again).toEqual(lost);
    expect(again?.hire_again).toBe(BARAKAS_OLD_JOB);
  });

  it("forgets whose phone it was once Simu changes (the review)", async () => {
    answer("POST", STAFF, HIS_PHONE);
    openForm();

    typeBaraka();
    tap(save());
    await screen.findByRole("button", { name: "Mwajiri tena" });
    typeInto(phoneBox(), "0754 000 111");

    expect(screen.queryByRole("button", { name: "Mwajiri tena" })).toBeNull();
    expect(screen.queryByText(/Simu hii ni ya/)).toBeNull();
  });

  it("is off on the demo, and says why where its hint would be (PPL-10: no phone there)", () => {
    openForm({ demo: true });

    expect(phoneBox().disabled).toBe(true);
    expect(
      screen.getByText(/Kwenye demo, wafanyakazi hawawekewi namba/),
    ).toBeTruthy();
  });
});
