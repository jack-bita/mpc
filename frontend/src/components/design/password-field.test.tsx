// password-field.test.tsx — a password box hides what is typed until its eye is pressed, and shows it
// until pressed again (UI-5, ADR-0039).
import { fireEvent, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import { render } from "@/test/render";

import { PasswordField } from "./password-field";

const box = () => screen.getByLabelText("Nenosiri") as HTMLInputElement;
const eye = () => screen.getByRole("button", { name: "Onyesha nenosiri" });

describe("a password field", () => {
  it("hides what is typed until its eye is pressed", () => {
    render(<PasswordField label="Nenosiri" />);

    expect(box().type).toBe("password");
    expect(eye().getAttribute("aria-pressed")).toBe("false");
  });

  it("shows what is typed when its eye is pressed, and hides it again on the next press", () => {
    render(<PasswordField label="Nenosiri" />);

    fireEvent.click(eye());
    expect(box().type).toBe("text");
    // One name, pressed or not: a screen reader says "Onyesha nenosiri, pressed".
    expect(eye().getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(eye());
    expect(box().type).toBe("password");
    expect(eye().getAttribute("aria-pressed")).toBe("false");
  });

  it("never sends the form it sits in", () => {
    const send = vi.fn((event: SubmitEvent) => event.preventDefault());
    render(
      <form onSubmit={(event) => send(event.nativeEvent as SubmitEvent)}>
        <PasswordField label="Nenosiri" />
      </form>,
    );

    fireEvent.click(eye());

    expect(send).not.toHaveBeenCalled();
  });

  it("keeps the box tied to its label, hint and error", () => {
    render(
      <PasswordField
        label="Nenosiri"
        hint="Herufi 8 au zaidi"
        error="Nenosiri ni fupi mno."
      />,
    );

    expect(box().getAttribute("aria-invalid")).toBe("true");
    const named = (box().getAttribute("aria-describedby") ?? "")
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent);
    expect(named).toEqual(["Herufi 8 au zaidi", "Nenosiri ni fupi mno."]);
  });

  it("never lets the browser check or change a password's spelling, shown or not", () => {
    // Shown, the box is plain text: a browser's spelling check could send what is typed to a server.
    render(<PasswordField label="Nenosiri" />);
    fireEvent.click(eye());

    expect(box().getAttribute("spellcheck")).toBe("false");
    expect(box().getAttribute("autocorrect")).toBe("off");
    expect(box().getAttribute("autocapitalize")).toBe("none");
  });

  it("hands its box the ref a form library gives it", () => {
    // react-hook-form's register() moves the keyboard to a refused box through it.
    const ref = createRef<HTMLInputElement>();
    render(<PasswordField label="Nenosiri" ref={ref} />);

    expect(ref.current).toBe(box());
  });

  it("makes its eye as wide as the box is high, and leaves the typing room", () => {
    const { unmount } = render(<PasswordField label="Nenosiri" />);
    expect(eye().className.split(/\s+/)).toContain("w-(--control-big)");
    expect(box().className.split(/\s+/)).toContain("pr-(--control-big)");
    unmount();

    render(<PasswordField label="Nenosiri" size="normal" />);
    expect(eye().className.split(/\s+/)).toContain("w-(--control-normal)");
    expect(box().className.split(/\s+/)).toContain("pr-(--control-normal)");
  });

  it("keeps the focus ring at full strength on its eye", () => {
    render(<PasswordField label="Nenosiri" />);

    expect(eye().className.split(/\s+/)).toContain("focus-visible:ring-ring");
  });
});
