// login-name.ts — what a person types to log in, turned into the email or the phone allauth's login
// takes (UI-5, AUTH-3, 03 §5.9).
//
// The login form has one box, Simu au barua pepe: most of the shop's people have a phone and no email
// (ADR-0038), and nobody should have to pick which one first. allauth's login takes a phone only written
// in full, +255712345678: it refuses 0712…, and spaces too, before it asks our cleaner. People in the
// shop write 0712 345 678. So the form writes the number out in full before it sends it.
//
// Only the writing, not the checking: the server's cleaner knows the numbering plan, and refuses a
// wrong number with phone.invalid (apps/core/phones.py). A number with no 0, no 255 and no plus is sent
// as it is, and allauth asks for the whole number (invalid_phone).

/** What allauth's login takes beside the password: an email, or a phone. */
export type LoginName = { email: string } | { phone: string };

// The country a number written without its code belongs to: Tanzania, as the server's cleaner assumes
// (normalise_phone, region "TZ"). The login comes before the app knows any shop, so it can't ask one.
const COUNTRY_CODE = "255";

// The marks people put between a number's digits: spaces, dashes, dots and brackets.
const BETWEEN_DIGITS = /[\s\-.()]/g;

// Marks nobody sees, which text copied from another app carries: WhatsApp wraps a number in direction
// marks (U+202A … U+202C), and others bring a left-to-right mark or a zero-width space. Unicode calls
// them "format" characters (\p{Cf}); none belongs in an email or a phone.
const UNSEEN = /\p{Cf}/gu;

/** The email or the phone in what was typed. Anything with an @ is an email, as typed; anything else is
 * a phone, written out in full. */
export function loginName(typed: string): LoginName {
  const value = typed.replace(UNSEEN, "").trim();
  // The server finds an email in any case (AUTH-3): the form leaves it as typed.
  if (value.includes("@")) return { email: value };

  const phone = value.replace(BETWEEN_DIGITS, "");
  if (phone.startsWith("+")) return { phone };
  if (phone.startsWith("0"))
    return { phone: `+${COUNTRY_CODE}${phone.slice(1)}` };
  if (phone.startsWith(COUNTRY_CODE)) return { phone: `+${phone}` };
  return { phone };
}
