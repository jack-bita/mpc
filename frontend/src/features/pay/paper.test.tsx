// paper.test.tsx — a page printed on A4 (WAGE-5): Chapisha prints it, but only once every signature on it has come
// or failed, as an empty box where Asha signed would make the sheet worth nothing to NSSF; and nothing of the screen
// goes on paper. jsdom loads no picture and prints nothing, so a picture's `complete` is set by the test, and paper is
// checked by the classes the browser reads when it prints, as the update bar's test does.
import { fireEvent, screen, waitFor } from "@testing-library/react";
import Image from "next/image";
import { afterEach, describe, expect, it, vi } from "vitest";

import { render } from "@/test/render";

import { Paper, PaperSheet } from "./paper";

/** Whether the pictures have come, as the browser would say it (`complete`); false until a test says so. */
let arrived = false;

function picturesArrive(yes: boolean) {
  arrived = yes;
  vi.spyOn(HTMLImageElement.prototype, "complete", "get").mockImplementation(
    () => arrived,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

/** The sheet as the screens draw it: a signature is Next's Image, unoptimized, as on the payslip. */
function aSheet(withPicture: boolean, printable = true) {
  return (
    <Paper title="Orodha ya malipo" printable={printable}>
      <PaperSheet>
        <p>Asha 152,000</p>
        {withPicture ? (
          <Image
            unoptimized
            src="/api/v1/control/attachments/1/"
            alt="Sahihi ya Asha"
            width={600}
            height={160}
          />
        ) : null}
      </PaperSheet>
    </Paper>
  );
}

describe("a page printed on A4", () => {
  it("prints the paper when Chapisha is tapped", () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    render(aSheet(false));

    expect(
      screen.getByRole("heading", { level: 1, name: "Orodha ya malipo" }),
    ).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Chapisha" }));

    expect(print).toHaveBeenCalledOnce();
  });

  it("waits for a signature, and says why", () => {
    picturesArrive(false);
    render(aSheet(true));

    expect(screen.getByRole("button", { name: "Chapisha" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(screen.getByRole("status").textContent).toBe(
      "Sahihi bado zinapakia, subiri kidogo.",
    );

    arrived = true;
    fireEvent.load(screen.getByRole("img", { name: "Sahihi ya Asha" }));

    expect(screen.getByRole("button", { name: "Chapisha" })).toHaveProperty(
      "disabled",
      false,
    );
    expect(screen.getByRole("status").textContent).toBe("");
  });

  it("prints once a signature fails too: its box says so on the paper itself", () => {
    // A picture that never comes is `complete` as well, in a browser; the payslip's foot then says it in words.
    picturesArrive(false);
    render(aSheet(true));

    arrived = true;
    fireEvent.error(screen.getByRole("img", { name: "Sahihi ya Asha" }));

    expect(screen.getByRole("button", { name: "Chapisha" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("waits again for a signature that comes with the rows, once the read answers", async () => {
    picturesArrive(false);
    const { rerender } = render(aSheet(false));
    expect(screen.getByRole("button", { name: "Chapisha" })).toHaveProperty(
      "disabled",
      false,
    );

    rerender(aSheet(true));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Chapisha" })).toHaveProperty(
        "disabled",
        true,
      ),
    );
  });

  it("offers no Chapisha while there is nothing to print, and says nothing of pictures", () => {
    // A read on its way, a refusal, or a month still open: the screen says why in words that never print, so Chapisha
    // would print a blank page (WAGE-5's review).
    render(aSheet(false, false));

    expect(screen.getByRole("button", { name: "Chapisha" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(screen.getByRole("status").textContent).toBe("");
  });

  it("puts nothing of the screen on paper, and gives each sheet a page of its own", () => {
    render(
      <Paper title="Hati za malipo" printable>
        <PaperSheet>
          <p>Asha</p>
        </PaperSheet>
        <PaperSheet>
          <p>Baraka</p>
        </PaperSheet>
      </Paper>,
    );

    // The arrow, the title, Chapisha and the waiting line sit in one part that paper never shows.
    const screenParts = screen
      .getByRole("button", { name: "Chapisha" })
      .closest(".print\\:hidden");
    expect(screenParts).not.toBeNull();
    expect(
      screenParts?.contains(screen.getByRole("heading", { level: 1 })),
    ).toBe(true);
    expect(screenParts?.contains(screen.getByRole("status"))).toBe(true);
    // Each sheet ends its page, but the last, which would leave a blank page after it.
    const sheet = screen.getByText("Asha").closest("section");
    expect(sheet?.className).toContain("break-after-page");
    expect(sheet?.className).toContain("last:break-after-auto");
    // A sheet longer than a page gets its padding again on each page it runs onto (WAGE-5's review).
    expect(sheet?.className).toContain("box-decoration-clone");
  });

  it("asks for A4, with no margin left for Chrome's own header and footer", () => {
    const { container } = render(aSheet(false));

    expect(container.querySelector("style")?.textContent).toBe(
      "@page { size: A4; margin: 0; }",
    );
  });
});
