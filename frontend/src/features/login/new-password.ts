// new-password.ts — the two boxes every form that sets a new password asks for, and their one rule: the
// new password typed the same twice (UI-5). Choosing your own after a temporary one uses them
// (choose-password.tsx), and so does the email link's form (password-reset.tsx).
//
// Typed twice, as a password box hides what is typed: a typo nobody can see would lock the person out
// until they see the owner again (ADR-0038). Only this, and "not empty": whether the new password is good
// enough is the server's checker's to say (too short, too common, only numbers, too like the person, or
// the temporary one), and it says so beside the new box.
import { z } from "zod";

/** The forms' own word for a new password typed differently twice. Not a server's code, so its sentence
 * lives in the forms' book (password.notTheSame), not beside the server's (errors.test.ts lists only
 * those). */
export const NOT_THE_SAME = "not_the_same";

/** The two boxes, for a form's z.object(). Each names what is wrong by a code, as the server does. */
export const NEW_PASSWORD = {
  fresh: z.string().min(1, { error: "required" }),
  again: z.string().min(1, { error: "required" }),
};

/** The rule, for the form's .refine(...TYPED_THE_SAME): the same password both times, said beside the
 * second box. */
export const TYPED_THE_SAME: [
  (form: { fresh: string; again: string }) => boolean,
  { path: string[]; error: string },
] = [
  (form) => form.fresh === form.again,
  { path: ["again"], error: NOT_THE_SAME },
];
