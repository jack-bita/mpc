// new-worker-screen.test.tsx — Mfanyakazi mpya, Ongeza's form on a page of its own (UI-11): its title, the shop's today,
// no Ghairi, and Hifadhi landing on the new worker's page in its place, with the line that says he was added. And
// Mwajiri tena Baraka, the same page for a worker who left (PPL-11, UI-11): the boxes from his old job, what is sent,
// the landing on his new job's page with "Baraka ameajiriwa tena.", and what the page says when there is nobody to hire
// again. The form's own checks are worker-form.test.tsx's.
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import { DAWA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { router } from "@/test/router";
import { MANAGER, STAFF, worker } from "@/test/workers";

import { NewWorkerScreen } from "./new-worker-screen";
import { forgetNews, peekNews } from "./page-news";
import { workerKey, workerPage, WORKERS } from "./workers";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";

/** Juma, as the server answers the add. */
const JUMA = worker({ display_name: "Juma", full_name: "Juma Mfano" });

afterEach(() => {
  // A note left by a test is never read by the next one's page.
  forgetNews();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** Types Juma's names, once the form is on the page. */
async function typeJuma() {
  fireEvent.change(await screen.findByLabelText("Jina kamili"), {
    target: { value: "Juma Mfano" },
  });
  fireEvent.change(screen.getByLabelText("Jina la kuitwa"), {
    target: { value: "Juma" },
  });
}

/** What the page sent to add a worker: a request's url is the whole address, so its path is compared. */
const adds = () =>
  sent.filter(
    (request) =>
      request.method === "POST" && new URL(request.url).pathname === STAFF,
  );

describe("Mfanyakazi mpya", () => {
  it("is titled Mfanyakazi mpya, its one heading, and its arrow leads to the list from a bookmark", async () => {
    answer("GET", ME, { status: 200, body: MANAGER });
    // A tab with no page before this one: the page was opened from a bookmark.
    vi.spyOn(window.history, "length", "get").mockReturnValue(1);
    render(<NewWorkerScreen />);

    await screen.findByLabelText("Jina kamili");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Mfanyakazi mpya",
    );
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(router.push).toHaveBeenCalledWith("/workers/");
  });

  it("adds Juma and lands on his page in its own place, with the line that says he gets a tile with a PIN (the card's first Done when)", async () => {
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("POST", STAFF, { status: 201, body: JUMA });
    const store = makeQueryClient();
    render(
      <QueryClientProvider client={store}>
        <NewWorkerScreen />
      </QueryClientProvider>,
    );

    await typeJuma();
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    // In this page's place, so the arrow on his page leads to the list, never back into the form already sent.
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith(workerPage(JUMA.id)),
    );
    expect(router.push).not.toHaveBeenCalled();
    // The line waits for his page, on Taarifa zake, where Kuingia's Weka PIN is under it.
    expect(peekNews()).toEqual({
      worker: JUMA.id,
      card: "details",
      sentence:
        "Juma ameongezwa. Jina lake litaonekana kwenye kompyuta za duka baada ya kupewa PIN.",
    });
    // His page shows him at once, from the server's answer, before it asks again (keepWorker).
    expect(store.getQueryData(workerKey(JUMA.id))).toEqual(JUMA);
  });

  it("stays, and leaves no line, when the server refuses", async () => {
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("POST", STAFF, refusal(400, "staff.display_name_taken"));
    render(<NewWorkerScreen />);

    await typeJuma();
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    // Beside Jina la kuitwa, where the owner fixes it (worker-form.tsx).
    expect(
      await screen.findByText(
        "Mfanyakazi mwingine tayari ana jina hili la kuitwa. Chagua jingine.",
      ),
    ).toBeTruthy();
    expect(router.replace).not.toHaveBeenCalled();
    expect(peekNews()).toBeNull();
  });

  it("starts the first day at the shop's today", async () => {
    answer("GET", ME, { status: 200, body: MANAGER });
    vi.useFakeTimers({
      now: Date.parse("2026-11-18T21:30:00Z"),
      toFake: ["Date"],
    });
    render(<NewWorkerScreen />);

    // 21:30 UTC is 00:30 on the 19th in Dar es Salaam: the shop's day, whatever the phone's zone.
    expect(
      ((await screen.findByLabelText("Siku ya kwanza")) as HTMLInputElement)
        .value,
    ).toBe("2026-11-19");
  });

  it("has no Ghairi: the arrow is the way out, with nothing sent (Jack's yes to the screens)", async () => {
    answer("GET", ME, { status: 200, body: MANAGER });
    render(<NewWorkerScreen />);

    await typeJuma();
    expect(screen.queryByRole("button", { name: "Ghairi" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(adds()).toEqual([]);
  });

  it("says a missing key in the server's own sentence, with no form, to someone without staff.manage on the whole shop", async () => {
    // staff.manage on Dawa alone: a worker belongs to the shop, not to a side.
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["staff.manage"] }]),
    });
    render(<NewWorkerScreen />);

    expect(
      await screen.findByText("Huna ruhusa ya kufanya hili."),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Jina kamili")).toBeNull();
    expect(screen.queryByRole("button", { name: "Hifadhi" })).toBeNull();
  });

  it("keeps Simu off on the demo, and says why (PPL-10, PPL-11: no phone there)", async () => {
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("GET", "/api/devices/v1/demo/open/", {
      status: 200,
      body: { open: true },
    });
    render(<NewWorkerScreen />);

    await waitFor(async () =>
      expect(
        ((await screen.findByLabelText("Simu")) as HTMLInputElement).disabled,
      ).toBe(true),
    );
    expect(
      screen.getByText(/Kwenye demo, wafanyakazi hawawekewi namba/),
    ).toBeTruthy();
  });
});

/** Baraka, a seller who worked here from 2 Jan 2025 until 12 Mar 2026. */
const BARAKA = worker({
  full_name: "Baraka Mfano",
  display_name: "Baraka",
  job_title: "Muuzaji wa dawa",
  started_on: "2025-01-02",
  status: "left",
  left_on: "2026-03-12",
});

/** His new job, as the server answers the hire again. */
const BACK = worker({
  full_name: "Baraka Mfano",
  display_name: "Baraka",
  job_title: "Muuzaji",
  started_on: "2026-11-18",
});

/** The manager is logged in, and the server holds Baraka's old job as `old`. */
function theServerHas(old: typeof BARAKA) {
  answer("GET", ME, { status: 200, body: MANAGER });
  answer("GET", `${STAFF}${old.id}/`, { status: 200, body: old });
}

/** The error beside a box: the one its aria-describedby names, after its hint (field.tsx). */
function errorOf(box: HTMLElement): string {
  const ids = box.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

const firstDayBox = () =>
  screen.getByLabelText("Siku ya kwanza") as HTMLInputElement;

/** What the page sent, as the server would read it. */
async function addsSent(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    adds().map((request) => request.json() as Promise<Record<string, unknown>>),
  );
}

describe("Mwajiri tena", () => {
  // Wednesday 18 Nov 2026 in Dar es Salaam: the shop's today. Only the date is faked.
  beforeEach(() => {
    vi.useFakeTimers({
      now: Date.parse("2026-11-18T09:00:00Z"),
      toFake: ["Date"],
    });
  });

  it("opens Ongeza's boxes filled from his old job, titled Mwajiri tena Baraka, with today as the first day and no full name, phone nor Ghairi", async () => {
    theServerHas(BARAKA);

    render(<NewWorkerScreen again={BARAKA.id} />);

    expect(
      ((await screen.findByLabelText("Jina la kuitwa")) as HTMLInputElement)
        .value,
    ).toBe("Baraka");
    // The page's own title, its one heading, where it was an <h2> inside his old page (UI-11).
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Mwajiri tena Baraka",
    );
    expect((screen.getByLabelText("Kazi") as HTMLInputElement).value).toBe(
      "Muuzaji wa dawa",
    );
    expect(firstDayBox().value).toBe("2026-11-18");
    // The person keeps his own full name and phone: Badilisha fixes them (PPL-10).
    expect(screen.queryByLabelText("Jina kamili")).toBeNull();
    expect(screen.queryByLabelText("Simu")).toBeNull();
    expect(screen.queryByRole("button", { name: "Ghairi" })).toBeNull();
  });

  it("hires him again as the same person, and lands on his new job's page with Baraka ameajiriwa tena (the card's third Done when)", async () => {
    theServerHas(BARAKA);
    answer("POST", STAFF, { status: 201, body: BACK });
    render(<NewWorkerScreen again={BARAKA.id} />);

    fireEvent.change(await screen.findByLabelText("Kazi"), {
      target: { value: "Muuzaji" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    // In this page's place: the arrow on his new page leads to his old one, never back into the form.
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith(workerPage(BACK.id)),
    );
    expect(peekNews()).toEqual({
      worker: BACK.id,
      card: "details",
      sentence: "Baraka ameajiriwa tena.",
    });
    // The old job's id, and the new job's own (ADR-0007): no full name nor phone, as he keeps his own.
    expect(await addsSent()).toEqual([
      {
        id: expect.stringMatching(/^[0-9a-f-]{36}$/),
        hire_again: BARAKA.id,
        display_name: "Baraka",
        job_title: "Muuzaji",
        started_on: "2026-11-18",
      },
    ]);
  });

  it("says a first day before his last day at once, beside its box, and sends nothing", async () => {
    theServerHas(BARAKA);
    render(<NewWorkerScreen again={BARAKA.id} />);

    fireEvent.change(await screen.findByLabelText("Siku ya kwanza"), {
      target: { value: "2026-03-11" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    expect(errorOf(firstDayBox())).toBe(
      "Siku ya kwanza haiwezi kuwa kabla ya siku yake ya mwisho ya kazi iliyopita.",
    );
    expect(adds()).toEqual([]);
  });

  it("shows the server's refusal of the first day beside its box, as when a later job ended after it", async () => {
    theServerHas(BARAKA);
    answer(
      "POST",
      STAFF,
      refusal(400, "invalid", {}, { started_on: ["staff.back_before_left"] }),
    );
    render(<NewWorkerScreen again={BARAKA.id} />);

    await screen.findByLabelText("Siku ya kwanza");
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    await waitFor(() =>
      expect(errorOf(firstDayBox())).toBe(
        "Siku ya kwanza haiwezi kuwa kabla ya siku yake ya mwisho ya kazi iliyopita.",
      ),
    );
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("says another manager hired him first, and stays, leaving no line", async () => {
    theServerHas(BARAKA);
    answer("POST", STAFF, refusal(400, "staff.already_member"));
    render(<NewWorkerScreen again={BARAKA.id} />);

    await screen.findByLabelText("Kazi");
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Mtu huyu tayari anafanya kazi hapa.",
    );
    expect(router.replace).not.toHaveBeenCalled();
    expect(peekNews()).toBeNull();
  });

  it("says he is back already, with a link to his new job's page, and offers no form", async () => {
    const now = "019a8302-0000-7000-8000-00000000fffe";
    theServerHas({ ...BARAKA, hired_again_as: now });

    render(<NewWorkerScreen again={BARAKA.id} />);

    expect(await screen.findByText("Baraka amerudi kazini.")).toBeTruthy();
    // The app is built with trailing slashes; Next.js's Link in a test drops them (text-link.test.tsx).
    expect(
      screen
        .getByRole("link", { name: "Fungua ukurasa wake wa sasa" })
        .getAttribute("href"),
    ).toMatch(new RegExp(`^/workers/view/?\\?id=${now}$`));
    expect(screen.queryByLabelText("Kazi")).toBeNull();
  });

  it("says a worker still here hasn't left, and offers no form", async () => {
    theServerHas({ ...BARAKA, status: "active", left_on: null });

    render(<NewWorkerScreen again={BARAKA.id} />);

    expect(
      await screen.findByText("Mfanyakazi huyu hajaondoka kazini."),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Kazi")).toBeNull();
  });

  it("opens on his old job's own read, never the list's older copy, which didn't know he is back", async () => {
    const now = "019a8302-0000-7000-8000-00000000fffe";
    const store = makeQueryClient();
    store.setQueryData(WORKERS, [BARAKA]);
    theServerHas({ ...BARAKA, hired_again_as: now });
    render(
      <QueryClientProvider client={store}>
        <NewWorkerScreen again={BARAKA.id} />
      </QueryClientProvider>,
    );

    // The title from the list's copy at once; the form waits for his own read, which says he is back.
    expect(screen.getByText("Subiri kidogo…")).toBeTruthy();
    expect(await screen.findByText("Baraka amerudi kazini.")).toBeTruthy();
    expect(screen.queryByLabelText("Kazi")).toBeNull();
  });

  it("leads from a bookmark to his old job's page, where Mwajiri tena is", async () => {
    theServerHas(BARAKA);
    vi.spyOn(window.history, "length", "get").mockReturnValue(1);
    render(<NewWorkerScreen again={BARAKA.id} />);

    await screen.findByLabelText("Kazi");
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));

    expect(router.push).toHaveBeenCalledWith(workerPage(BARAKA.id));
  });
});

describe("Mwajiri tena from Ongeza itself", () => {
  it("lands on his new job's page with Baraka ameajiriwa tena, when the phone typed was his (PPL-11)", async () => {
    // Baba, who forgot Baraka worked here, types him in as new with his phone; the server names his old job.
    answer("GET", ME, { status: 200, body: MANAGER });
    let tries = 0;
    answer("POST", STAFF, () => {
      tries += 1;
      return tries === 1
        ? Response.json(
            refusal(400, "staff.left_here", {
              staff: BARAKA.id,
              full_name: "Baraka Mfano",
              left_on: "2026-03-12",
            }).body,
            { status: 400 },
          )
        : Response.json(BACK, { status: 201 });
    });
    render(<NewWorkerScreen />);

    fireEvent.change(await screen.findByLabelText("Jina kamili"), {
      target: { value: "Baraka Mfano" },
    });
    fireEvent.change(screen.getByLabelText("Jina la kuitwa"), {
      target: { value: "Baraka" },
    });
    fireEvent.change(screen.getByLabelText("Simu"), {
      target: { value: "0712 345 678" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Mwajiri tena" }),
    );

    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith(workerPage(BACK.id)),
    );
    expect(peekNews()?.sentence).toBe("Baraka ameajiriwa tena.");
  });
});
