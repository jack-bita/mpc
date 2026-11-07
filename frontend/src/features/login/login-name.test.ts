// login-name.test.ts — what a person types to log in becomes the email or the phone allauth takes
// (UI-5, AUTH-3).
import { describe, expect, it } from "vitest";

import { loginName } from "./login-name";

describe("the name a person logs in with", () => {
  it.each([
    // As people in the shop write a number: allauth takes only +255…, and refuses 0712… (AUTH-3).
    ["0712345678", "+255712345678"],
    // With spaces, which allauth refuses too (AUTH-3's review).
    ["0712 345 678", "+255712345678"],
    ["+255 712 345 678", "+255712345678"],
    ["0712-345-678", "+255712345678"],
    // The country's code without its plus.
    ["255712345678", "+255712345678"],
    // Already in full.
    ["+255712345678", "+255712345678"],
    // A space before or after, as a phone's keyboard adds.
    [" 0712345678 ", "+255712345678"],
  ])("reads %j as the phone %s", (typed, phone) => {
    expect(loginName(typed)).toEqual({ phone });
  });

  it("leaves anything else for the server to judge", () => {
    // The server's cleaner knows the numbering plan; the form doesn't guess (apps/core/phones.py).
    expect(loginName("712345678")).toEqual({ phone: "712345678" });
  });

  it("reads anything with an @ as an email, as it was typed", () => {
    // The server finds an email in any case (AUTH-3), so a capital letter is left as it is.
    expect(loginName(" Neema@Example.com ")).toEqual({
      email: "Neema@Example.com",
    });
  });
});
