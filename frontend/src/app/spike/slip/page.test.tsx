// page.test.tsx — what the throwaway slip page must show and do (SPIKE-2).
//
// The page exists only to answer the card's question: can Chrome print a readable slip on the
// shop's printer in one click? The spike's second pull request removes it, with these tests.
// How the slip looks on paper can't be checked here: jsdom has no printer and lays nothing out,
// so that check is Chrome's print preview and the shop's printer (docs/spikes/02-printing.md).
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SlipPage from "./page";

afterEach(() => {
  // Put the real window.print back after the test that replaces it.
  vi.restoreAllMocks();
});

describe("SlipPage", () => {
  it("the slip's words are in Swahili", () => {
    render(<SlipPage />);

    // The words themselves, not the message keys: a wrong translation in messages/sw.json fails
    // here too. A pattern (/…/), not an exact string, so a word may share its line with a value,
    // as in "Namba ya mauzo: D2-0457".
    expect(screen.getByText(/Namba ya mauzo/)).toBeTruthy();
    expect(screen.getByText(/Jumla/)).toBeTruthy();
    expect(screen.getByText(/Asante, karibu tena/)).toBeTruthy();
  });

  it("the total is bold", () => {
    render(<SlipPage />);

    // <strong> means "this matters", and the browser draws it bold with no class needed, on
    // screen and on paper. A class like font-bold would look the same but say nothing a test
    // (or a screen reader) can find.
    const totalLine = screen.getByText(/Jumla/).closest("strong");
    expect(totalLine).not.toBeNull();
    // The amount sits in the same bold line as the word: the number the customer pays stands out.
    expect(totalLine?.textContent).toMatch(/\d/);
  });

  it("the button prints", () => {
    // jsdom has no printer: its window.print only reports "not implemented". The spy takes its
    // place and counts the calls.
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    render(<SlipPage />);

    fireEvent.click(screen.getByRole("button", { name: "Chapisha" }));

    expect(print).toHaveBeenCalledOnce();
  });
});
