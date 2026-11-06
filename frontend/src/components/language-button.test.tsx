// language-button.test.tsx — the button on the top bar names the other language, in that language, and
// switches the whole app to it (UI-1, ADR-0040).
import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { setLanguage } from "@/i18n/language";
import { render } from "@/test/render";

import { LanguageButton } from "./language-button";

describe("the language button", () => {
  it("offers English, as English, while Swahili is open", () => {
    render(<LanguageButton />);

    const button = screen.getByRole("button", { name: "English" });
    // lang="en": a screen reader says the word as English, not with Swahili sounds.
    expect(button.querySelector('[lang="en"]')?.textContent).toBe("English");
  });

  it("switches the app to English, then offers Kiswahili", () => {
    render(<LanguageButton />);

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(document.documentElement.lang).toBe("en");
    const button = screen.getByRole("button", { name: "Kiswahili" });
    expect(button.querySelector('[lang="sw"]')?.textContent).toBe("Kiswahili");
  });

  it("switches back to Swahili", () => {
    act(() => setLanguage("en"));
    render(<LanguageButton />);

    fireEvent.click(screen.getByRole("button", { name: "Kiswahili" }));

    expect(document.documentElement.lang).toBe("sw");
    expect(screen.getByRole("button", { name: "English" })).toBeTruthy();
  });

  it("is the bar kind, the only kind that can sit on the green", () => {
    render(<LanguageButton />);
    // The bar kind's white edge (button.tsx).
    expect(screen.getByRole("button").className).toContain(
      "border-primary-foreground",
    );
  });
});
