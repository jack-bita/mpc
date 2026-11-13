// this-laptop.test.tsx — the Kompyuta hii screen (SYNC-12): what it says for each of the browser's answers.
// The browser's storage is a stand-in: jsdom has none to ask.
import { act, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  forgetKeepData,
  type InstallPromptEvent,
  watchInstall,
} from "@/offline/keep-data";
import { render } from "@/test/render";

import { ThisLaptopScreen } from "./this-laptop";

afterEach(() => {
  forgetKeepData();
  vi.unstubAllGlobals();
});

/** The browser's storage, answering as told. */
function browserKeeps(yes: boolean) {
  vi.stubGlobal("navigator", {
    ...navigator,
    storage: {
      persisted: async () => yes,
      persist: async () => yes,
    },
  });
}

describe("keeping the data", () => {
  it("says the browser keeps it", async () => {
    browserKeeps(true);
    render(<ThisLaptopScreen />);
    expect(
      await screen.findByText(
        "Kivinjari kimekubali kuhifadhi data za duka kwenye kompyuta hii kwa kudumu.",
      ),
    ).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("warns when it doesn't, and says how to get a yes", async () => {
    browserKeeps(false);
    render(<ThisLaptopScreen />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Sakinisha programu hii",
    );
  });

  it("warns that a browser with no such question can't keep it", async () => {
    vi.stubGlobal("navigator", { ...navigator, storage: undefined });
    render(<ThisLaptopScreen />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Tumia Chrome au Edge",
    );
  });
});

describe("the install", () => {
  it("shows the menu's steps when the browser offers nothing", () => {
    render(<ThisLaptopScreen />);
    expect(
      screen.getByText(
        "Fungua menyu ya kivinjari (⋮ au ⋯), kisha chagua Sakinisha.",
      ),
    ).toBeDefined();
  });

  it("has a button that opens the browser's own question", () => {
    const stop = watchInstall();
    render(<ThisLaptopScreen />);
    const event = new Event("beforeinstallprompt", {
      cancelable: true,
    }) as InstallPromptEvent;
    event.prompt = vi.fn(async () => {});
    event.userChoice = Promise.resolve({ outcome: "accepted" });
    act(() => {
      window.dispatchEvent(event);
    });

    act(() => screen.getByRole("button", { name: "Sakinisha" }).click());
    expect(event.prompt).toHaveBeenCalledOnce();
    stop();
  });

  it("says when the app is installed", () => {
    const stop = watchInstall();
    render(<ThisLaptopScreen />);
    act(() => {
      window.dispatchEvent(new Event("appinstalled"));
    });
    expect(
      screen.getByText("Programu imesakinishwa kwenye kompyuta hii."),
    ).toBeDefined();
    stop();
  });
});
