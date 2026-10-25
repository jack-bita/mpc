// service-worker.test.tsx — the Toleo jipya bar shows only when a new version is ready, and its button
// switches to it (SPIKE-1, 03 §6.8).
//
// The real registration is swapped for a fake (vi.mock), so these tests check only what the bar shows
// and does. When a version counts as ready is checked in src/offline/service-worker.test.ts.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  type ApplyUpdate,
  registerServiceWorker,
} from "@/offline/service-worker";

import { ServiceWorker } from "./service-worker";

vi.mock("@/offline/service-worker", () => ({ registerServiceWorker: vi.fn() }));

/** Plays the browser's part: a new version is ready, and `apply` switches to it. */
function newVersionReady(apply: ApplyUpdate) {
  const onUpdateReady = vi.mocked(registerServiceWorker).mock.calls[0]![0];
  // act: let React finish redrawing before the test looks at the page.
  act(() => onUpdateReady(apply));
}

beforeEach(() => {
  vi.mocked(registerServiceWorker).mockClear();
});

describe("ServiceWorker", () => {
  it("shows nothing while there is no new version", () => {
    render(<ServiceWorker />);

    expect(registerServiceWorker).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the bar once a new version is ready", () => {
    render(<ServiceWorker />);
    newVersionReady(vi.fn());

    // The words themselves, not the message keys: a wrong translation fails here too.
    expect(screen.getByText("Toleo jipya liko tayari")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sasisha" })).toBeTruthy();
  });

  it("switches to the new version when Sasisha is tapped", () => {
    render(<ServiceWorker />);
    const apply = vi.fn();
    newVersionReady(apply);

    fireEvent.click(screen.getByRole("button", { name: "Sasisha" }));

    expect(apply).toHaveBeenCalledOnce();
  });
});
