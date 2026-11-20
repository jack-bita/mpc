// closures.test.ts — the closures' helpers (ATT-9): a change put into the list at once, in its place, soonest first, or
// out of it once it is over or cancelled (ATT-9's review). The day before a day is src/lib/format.ts's, tested there.
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { closure, closuresAnswer } from "@/test/closures";

import { CLOSURES, dropClosure, keepClosure } from "./closures";

// On the shop's today of the tests, Sunday 15 Nov 2026.
const FUNERAL = closure();
const UHURU = closure({
  first_day: "2026-12-09",
  last_day: "2026-12-09",
  name: "Siku ya Uhuru",
});

/** A store holding the list as given, and a way to read the names in it, in order. */
function storeWith(list = [FUNERAL, UHURU]) {
  const store = new QueryClient();
  store.setQueryData(CLOSURES, closuresAnswer(list));
  const names = () =>
    store
      .getQueryData<ReturnType<typeof closuresAnswer>>(CLOSURES)
      ?.closures.map((each) => `${each.name} ${each.last_day}`);
  return { store, names };
}

describe("keepClosure", () => {
  it("puts a new closure in its place, soonest first", () => {
    const { store, names } = storeWith([UHURU]);

    keepClosure(store, FUNERAL);

    expect(names()).toEqual([
      "Msiba wa bibi 2026-11-24",
      "Siku ya Uhuru 2026-12-09",
    ]);
  });

  it("replaces a moved closure's old copy with its new days", () => {
    const { store, names } = storeWith();

    keepClosure(store, { ...FUNERAL, last_day: "2026-11-22" });

    expect(names()).toEqual([
      "Msiba wa bibi 2026-11-22",
      "Siku ya Uhuru 2026-12-09",
    ]);
  });

  it("takes out a closure that now ends before today, as the server lists none already over", () => {
    const begun = closure({ first_day: "2026-11-13", last_day: "2026-11-17" });
    const { store, names } = storeWith([begun, UHURU]);

    keepClosure(store, { ...begun, last_day: "2026-11-14" });

    expect(names()).toEqual(["Siku ya Uhuru 2026-12-09"]);
  });

  it("leaves a store that holds no list yet as it is", () => {
    const store = new QueryClient();

    keepClosure(store, FUNERAL);

    expect(store.getQueryData(CLOSURES)).toBeUndefined();
  });
});

describe("dropClosure", () => {
  it("takes a cancelled closure out of the list", () => {
    const { store, names } = storeWith();

    dropClosure(store, FUNERAL.id);

    expect(names()).toEqual(["Siku ya Uhuru 2026-12-09"]);
  });
});
