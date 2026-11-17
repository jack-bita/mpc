// alert.test.tsx — the message box speaks as loudly as its news, and in full colour (UI-8, ADR-0039).
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Alert, ALERT_KINDS, AlertDescription, AlertTitle } from "./alert";

function renderAlert(kind?: (typeof ALERT_KINDS)[number]) {
  render(
    <Alert kind={kind}>
      <AlertTitle>Inahitaji mtandao</AlertTitle>
      <AlertDescription>
        Ukurasa huu unafanya kazi ukiwa mtandaoni.
      </AlertDescription>
    </Alert>,
  );
}

describe("the message box", () => {
  it("tells news politely, when the screen reader is free", () => {
    // role="status": an offline note shouldn't cut into what is being read out. It is said when its
    // text changes, so news that comes and goes keeps the box on the page (alert.tsx).
    renderAlert("info");
    expect(screen.getByRole("status").textContent).toContain(
      "Inahitaji mtandao",
    );
  });

  it("says something went wrong at once", () => {
    renderAlert("danger");
    expect(screen.getByRole("alert").textContent).toContain(
      "Inahitaji mtandao",
    );
  });

  it("is info unless told otherwise", () => {
    renderAlert();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status")).toBeDefined();
  });

  it.each(ALERT_KINDS)("%s: no faded text", (kind) => {
    // A faded colour (text-destructive/90) is no token, so no contrast check covers it. dark: classes
    // never apply (UI-7) and are left out.
    renderAlert(kind);
    const box = screen.getByText("Inahitaji mtandao")
      .parentElement as HTMLElement;
    const description = screen.getByText(/mtandaoni/);
    const faded = [...box.classList, ...description.classList].filter(
      (name) => !name.startsWith("dark:") && /text-[\w-]+\/\d+/.test(name),
    );
    expect(faded).toEqual([]);
  });

  it("paints danger in the faded red, its description too", () => {
    // Whole class names, not text inside the class string: "text-destructive" is also part of the
    // description's rule, and a substring match would pass with the title's own red gone.
    renderAlert("danger");
    const classes = screen.getByRole("alert").className.split(/\s+/);
    expect(classes).toContain("border-destructive");
    expect(classes).toContain("text-destructive");
    // The description sets its own colour (alert.tsx), so the red reaches it only through this rule.
    expect(classes).toContain(
      "*:data-[slot=alert-description]:text-destructive",
    );
  });

  it("paints info with a blue edge and the normal text colour", () => {
    renderAlert("info");
    const classes = screen.getByRole("status").className.split(/\s+/);
    expect(classes).toContain("border-secondary");
    expect(classes).toContain("text-foreground");
    expect(classes).not.toContain("text-destructive");
  });
});
