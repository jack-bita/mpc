// new-worker-screen.test.tsx — Mfanyakazi mpya, Ongeza's form on a page of its own (UI-11): its title, the shop's today,
// no Ghairi, and Hifadhi landing on the new worker's page in its place, with the line that says he was added. The
// form's own checks are worker-form.test.tsx's.
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import { DAWA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { router } from "@/test/router";
import { MANAGER, STAFF, worker } from "@/test/workers";

import { NewWorkerScreen } from "./new-worker-screen";
import { forgetNews, peekNews } from "./page-news";
import { workerKey, workerPage } from "./workers";

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

/** What the page sent to add a worker. */
const adds = () =>
  sent.filter((request) => request.method === "POST" && request.url === STAFF);

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
