// last-person.ts — what the last person left in the store of server answers, for tests that check a
// login or a logout forgets it (UI-5's review). Tests only.
//
// "`me` was asked again" proves too little: marking every answer old (invalidateQueries) asks `me` again
// too, yet keeps the last person's rows for the next one to see. So a test leaves an answer and a change
// of theirs in the store, and checks both are gone (forgetTheLastPerson, src/api/query-client.ts).
import type { QueryClient } from "@tanstack/react-query";

// An answer only the last person's screen asked for: the shop's devices, say.
const THEIR_ANSWER = ["devices", "list"] as const;
// A change of theirs, waiting in the store's list of changes: a device's new name.
const THEIR_CHANGE = ["devices", "rename"] as const;

/** Puts an answer and a change of the last person's in the store. */
export function leaveTheLastPersonsAnswers(store: QueryClient): void {
  store.setQueryData(THEIR_ANSWER, [
    { id: "laptop-dawa", name: "Laptop Dawa" },
  ]);
  store.getMutationCache().build(store, { mutationKey: THEIR_CHANGE });
}

/** Whether the store still holds anything of the last person's: their answer, or their change. */
export function stillHoldsTheirs(store: QueryClient): boolean {
  const change = store
    .getMutationCache()
    .getAll()
    .some((mutation) => mutation.options.mutationKey?.[1] === THEIR_CHANGE[1]);
  return store.getQueryData(THEIR_ANSWER) !== undefined || change;
}

/** Whether any change in the store still holds `secret` among what it was sent with: a password, once
 * its form has its answer, must be gone, on a laptop the next person uses (UI-5's review). */
export function stillHoldsTheSecret(
  store: QueryClient,
  secret: string,
): boolean {
  return store
    .getMutationCache()
    .getAll()
    .some((mutation) =>
      JSON.stringify(mutation.state.variables ?? null).includes(secret),
    );
}
