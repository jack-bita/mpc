// update-prompt.test.tsx — the Toleo jipya bar shows only when a new version is ready and no counter
// screen is busy, and its button switches to it (SPIKE-1, SYNC-13, 03 §6.8).
//
// The real registration and the send before the switch are swapped for fakes (vi.mock), so these tests
// check only what the bar shows and does. When a version counts as ready is checked in
// src/offline/service-worker.test.ts, when the counter is busy in src/offline/busy.test.tsx, and how the
// records go in src/offline/sync/before-update.test.ts.
import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ON_GREEN } from "@/components/design/top-bar";
import { setLanguage } from "@/i18n/language";
import { BUSY_LOCK, QUIET_CHECK_EVERY, useCounterBusy } from "@/offline/busy";
import {
  type ApplyUpdate,
  registerServiceWorker,
} from "@/offline/service-worker";
import { sendBeforeUpdate } from "@/offline/sync/before-update";
import { installFakeLocks, removeFakeLocks } from "@/test/locks";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

import { UpdatePrompt } from "./update-prompt";

// Registered at once, with regular looks that a test never needs to stop.
vi.mock("@/offline/service-worker", () => ({
  registerServiceWorker: vi.fn(() => Promise.resolve(() => {})),
}));
// Sent at once, unless a test holds it.
vi.mock("@/offline/sync/before-update", () => ({
  sendBeforeUpdate: vi.fn(),
}));

/** Plays the browser's part: a new version is ready, and `apply` switches to it. */
function newVersionReady(apply: ApplyUpdate) {
  const onUpdateReady = vi.mocked(registerServiceWorker).mock.calls[0]![0];
  // act: let React finish redrawing before the test looks at the page.
  act(() => onUpdateReady(apply));
}

/** A counter screen that is busy while `busy` is true: a sale with items in it. */
function Sale({ busy }: { busy: boolean }) {
  useCounterBusy(busy);
  return null;
}

/** The bar beside a counter screen, as layout.tsx puts it beside every page. */
function Counter({ busy }: { busy: boolean }) {
  return (
    <>
      <Sale busy={busy} />
      <UpdatePrompt />
    </>
  );
}

/** Lets the bar's first look at the counter answer (busy.ts): it shows only after it. */
async function barLooked() {
  await act(async () => {});
}

/** The send before the switch, held until the test lets it go: the records on their way. */
function holdTheSend(): () => void {
  let release = () => {};
  vi.mocked(sendBeforeUpdate).mockReturnValue(
    new Promise<void>((resolve) => {
      release = resolve;
    }),
  );
  return () => release();
}

beforeEach(() => {
  vi.mocked(registerServiceWorker).mockClear();
  vi.mocked(sendBeforeUpdate).mockReset().mockResolvedValue(undefined);
});

afterEach(() => {
  removeFakeLocks();
  vi.useRealTimers();
});

describe("UpdatePrompt", () => {
  it("shows nothing while there is no new version, but keeps its status box", () => {
    render(<UpdatePrompt />);

    expect(registerServiceWorker).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button")).toBeNull();
    // On the page, empty and hidden from the eye, so a screen reader is already listening to it.
    const box = screen.getByRole("status");
    expect(box.textContent).toBe("");
    expect(box.parentElement?.classList.contains("sr-only")).toBe(true);
  });

  it("puts its words into the same status box when a version is ready", async () => {
    render(<UpdatePrompt />);
    const before = screen.getByRole("status");

    newVersionReady(vi.fn());
    await barLooked();

    // The same element, not a new one: a box that appears with its words in it may not be said.
    expect(screen.getByRole("status")).toBe(before);
    expect(before.textContent).toBe("Toleo jipya liko tayari");
  });

  it("sits on the green with the bar's button, and a white focus ring", async () => {
    render(<UpdatePrompt />);
    newVersionReady(vi.fn());
    await barLooked();

    const bar = screen.getByRole("status").parentElement;
    // ON_GREEN paints the green and sets --ring to white for the button on it (top-bar.tsx).
    for (const name of ON_GREEN.split(" "))
      expect(bar?.classList.contains(name)).toBe(true);
    expect(bar?.classList.contains("sr-only")).toBe(false);
    // The bar kind's white edge (button.tsx): the only kind that can sit on green.
    expect(screen.getByRole("button", { name: "Sasisha" }).className).toContain(
      "border-primary-foreground",
    );
  });

  it("shows the bar once a new version is ready", async () => {
    render(<UpdatePrompt />);
    newVersionReady(vi.fn());
    await barLooked();

    // The words themselves, not the message keys: a wrong translation fails here too.
    expect(screen.getByText("Toleo jipya liko tayari")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sasisha" })).toBeTruthy();
  });

  it("speaks English when English is chosen", async () => {
    // The bar sits outside every page, so the check on every page (language.test.tsx) doesn't see it.
    setLanguage("en");
    render(<UpdatePrompt />);
    newVersionReady(vi.fn());
    await barLooked();

    expect(screen.getByText("A new version is ready")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Update" })).toBeTruthy();
    expect(swahiliIn(document.body)).toEqual([]);
  });

  it("stays off the paper when a page is printed", async () => {
    render(<UpdatePrompt />);
    newVersionReady(vi.fn());
    await barLooked();

    // Checked by its class, because jsdom doesn't print. The slip's own button relies on the same class.
    expect(screen.getByRole("status").parentElement?.className).toContain(
      "print:hidden",
    );
  });

  it("switches to the new version when Sasisha is tapped", async () => {
    render(<UpdatePrompt />);
    const apply = vi.fn();
    newVersionReady(apply);
    await barLooked();

    fireEvent.click(screen.getByRole("button", { name: "Sasisha" }));

    await vi.waitFor(() => expect(apply).toHaveBeenCalledOnce());
  });
});

describe("UpdatePrompt beside a busy counter", () => {
  it("stays hidden while a sale is open, and shows once it is finished", async () => {
    // Asha has three items in a sale, and the customer waits. A new version arrives.
    const view = render(<Counter busy />);
    newVersionReady(vi.fn());
    await barLooked();

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("");

    // The sale is finished: the bar shows, with no wait for the next look.
    view.rerender(<Counter busy={false} />);
    expect(await screen.findByRole("button", { name: "Sasisha" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe(
      "Toleo jipya liko tayari",
    );
  });

  it("hides again when a new sale starts before anyone taps", async () => {
    const view = render(<Counter busy={false} />);
    newVersionReady(vi.fn());
    expect(await screen.findByRole("button", { name: "Sasisha" })).toBeTruthy();

    view.rerender(<Counter busy />);
    await vi.waitFor(() => expect(screen.queryByRole("button")).toBeNull());
  });

  it("stays hidden while another tab's sale is open, and shows at its next look after", async () => {
    // The Dawa laptop has the counter open in two tabs, and a sale is open in the other one.
    vi.useFakeTimers();
    const locks = installFakeLocks();
    const other = locks.holdInAnotherTab(BUSY_LOCK, "shared");
    render(<UpdatePrompt />);
    newVersionReady(vi.fn());
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.queryByRole("button")).toBeNull();

    other.release();
    await act(() => vi.advanceTimersByTimeAsync(QUIET_CHECK_EVERY));
    expect(screen.getByRole("button", { name: "Sasisha" })).toBeTruthy();
  });

  it("does nothing when tapped just after another tab's sale started", async () => {
    // The bar showed; then, before its next look, a sale opened in the other tab, and Asha taps here.
    const locks = installFakeLocks();
    render(<UpdatePrompt />);
    const apply = vi.fn();
    newVersionReady(apply);
    const button = await screen.findByRole("button", { name: "Sasisha" });
    const other = locks.holdInAnotherTab(BUSY_LOCK, "shared");
    await other.granted;

    fireEvent.click(button);
    await barLooked();

    expect(apply).not.toHaveBeenCalled();
    other.release();
  });
});

describe("UpdatePrompt sends the records first", () => {
  it("sends what waits, then switches", async () => {
    // Asha's clock-in still waits in the outbox when she taps Sasisha.
    render(<UpdatePrompt />);
    const apply = vi.fn();
    newVersionReady(apply);
    const release = holdTheSend();

    fireEvent.click(await screen.findByRole("button", { name: "Sasisha" }));

    // On its way: the bar says so, the button can't be tapped twice, and nothing has switched yet.
    expect(await screen.findByText("Inatuma kumbukumbu kwanza…")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Sasisha" }).hasAttribute("disabled"),
    ).toBe(true);
    expect(sendBeforeUpdate).toHaveBeenCalledOnce();
    expect(apply).not.toHaveBeenCalled();

    release();
    await vi.waitFor(() => expect(apply).toHaveBeenCalledOnce());
  });

  it("doesn't switch when a sale opened while the records were going", async () => {
    const view = render(<Counter busy={false} />);
    const apply = vi.fn();
    newVersionReady(apply);
    const release = holdTheSend();
    fireEvent.click(await screen.findByRole("button", { name: "Sasisha" }));
    await screen.findByText("Inatuma kumbukumbu kwanza…");

    // A customer comes in during the seconds the send takes, and Asha starts the sale.
    view.rerender(<Counter busy />);
    release();
    await barLooked();
    await barLooked();

    expect(apply).not.toHaveBeenCalled();
    expect(screen.queryByRole("button")).toBeNull();

    // The sale is finished: the bar is back, ready for a tap that sends again and switches.
    view.rerender(<Counter busy={false} />);
    expect(await screen.findByText("Toleo jipya liko tayari")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sasisha" }));
    await vi.waitFor(() => expect(apply).toHaveBeenCalledOnce());
    expect(sendBeforeUpdate).toHaveBeenCalledTimes(2);
  });

  it("says it in English when English is chosen", async () => {
    setLanguage("en");
    render(<UpdatePrompt />);
    newVersionReady(vi.fn());
    holdTheSend();

    fireEvent.click(await screen.findByRole("button", { name: "Update" }));

    expect(await screen.findByText("Sending records first…")).toBeTruthy();
    expect(swahiliIn(document.body)).toEqual([]);
  });
});
