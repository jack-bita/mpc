// query-client.test.ts — which failed reads the store asks again: never a refusal the server meant,
// a few times a dropped network or a broken server (UI-2); and what a login forgets (UI-4).
import {
  MutationObserver,
  onlineManager,
  QueryObserver,
} from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import {
  forgetTheLastPerson,
  makeQueryClient,
  READ_RETRIES,
  shouldRetry,
} from "./query-client";
import { ApiRefusal, NoConnection } from "./refusal";

function refusal(status: number, code: string) {
  return new ApiRefusal(status, { code, message: "", fields: {}, params: {} });
}

describe("shouldRetry", () => {
  it("never asks again after a refusal the server meant", () => {
    for (const error of [
      refusal(400, "invalid"),
      refusal(401, "not_authenticated"),
      refusal(403, "password.must_change"),
      refusal(404, "not_found"),
      refusal(409, "version_conflict"),
      refusal(429, "throttled"),
    ]) {
      expect(shouldRetry(0, error)).toBe(false);
    }
  });

  it("asks again a few times when the network dropped", () => {
    // What the client throws when fetch got no answer at all (client.ts).
    const dropped = new NoConnection(new TypeError("Failed to fetch"));

    expect(shouldRetry(0, dropped)).toBe(true);
    expect(shouldRetry(READ_RETRIES - 1, dropped)).toBe(true);
    expect(shouldRetry(READ_RETRIES, dropped)).toBe(false);
  });

  it("asks again a few times when the server broke", () => {
    // The proxy's 502 while the server restarts, read as server_error (refusal.ts).
    const restarting = refusal(502, "server_error");

    expect(shouldRetry(0, restarting)).toBe(true);
    expect(shouldRetry(READ_RETRIES, restarting)).toBe(false);
  });

  it("never asks again after a bug, which the next try would only repeat", () => {
    expect(shouldRetry(0, new TypeError("ask is not a function"))).toBe(false);
    expect(shouldRetry(0, new Error("a bug"))).toBe(false);
  });
});

describe("forgetTheLastPerson", () => {
  it("forgets every answer and every change done, and asks again for what a screen shows", async () => {
    // Asha has just used the laptop; Juma logs in after her (UI-4).
    const store = makeQueryClient();
    // A list from her last screen, which no screen shows now.
    store.setQueryData(["devices", "list"], ["Laptop Dawa"]);
    // A change she sent: a PIN login keeps its PIN among what it was sent with.
    await new MutationObserver(store, {
      mutationFn: (pin: string) => Promise.resolve(pin),
    }).mutate("4829");
    // A screen on show, which reads who is here: asked once for her.
    let asked = 0;
    const screen = new QueryObserver(store, {
      queryKey: ["auth", "me"],
      queryFn: () => Promise.resolve(`answer ${++asked}`),
    });
    const stop = screen.subscribe(() => {});
    await vi.waitFor(() =>
      expect(screen.getCurrentResult().data).toBe("answer 1"),
    );

    await forgetTheLastPerson(store);

    expect(store.getQueryData(["devices", "list"])).toBeUndefined();
    expect(store.getMutationCache().getAll()).toEqual([]);
    // The screen heard of it and asked again, for Juma. Removed without a word, as clear() removes
    // answers, it would go on showing Asha's.
    expect(asked).toBe(2);
    expect(screen.getCurrentResult().data).toBe("answer 2");
    stop();
  });
  it("keeps a change still on its way in its place, and sends it once the network is back", async () => {
    // Juma logs in on the laptop's own check while Neema's logout waits for the network (SYNC-10's review).
    // Taken off the list, the logout would never be sent, or wake later and end the next person's login;
    // and a change made after it could pass it.
    const store = makeQueryClient();
    store.mount();
    const order: string[] = [];
    const logout = new MutationObserver(store, {
      mutationFn: () => {
        order.push("logout");
        return Promise.resolve();
      },
    });
    const login = new MutationObserver(store, {
      mutationFn: () => {
        order.push("login");
        return Promise.resolve();
      },
    });
    try {
      onlineManager.setOnline(false);
      const leaving = logout.mutate();

      await forgetTheLastPerson(store);
      expect(store.getMutationCache().getAll()).toHaveLength(1);
      const arriving = login.mutate();
      onlineManager.setOnline(true);
      await Promise.all([leaving, arriving]);

      expect(order).toEqual(["logout", "login"]);
    } finally {
      onlineManager.setOnline(true);
      store.unmount();
    }
  });
});

describe("changes", () => {
  it("go one at a time, in the order they were made, offline too", async () => {
    // Asha renames a laptop with no network, then presses Toka. Back online, TanStack would send both
    // at once, and a logout that landed first would leave the rename refused, and lost (UI-5's review).
    const store = makeQueryClient();
    store.mount();
    const order: string[] = [];
    let finishRename = () => undefined as void;
    const rename = new MutationObserver(store, {
      mutationFn: () => {
        order.push("rename starts");
        return new Promise<void>((resolve) => {
          finishRename = () => {
            order.push("rename ends");
            resolve();
          };
        });
      },
    });
    const logout = new MutationObserver(store, {
      mutationFn: () => {
        order.push("logout");
        return Promise.resolve();
      },
    });
    try {
      onlineManager.setOnline(false);
      const renaming = rename.mutate();
      const leaving = logout.mutate();
      expect(order).toEqual([]);

      onlineManager.setOnline(true);
      await vi.waitFor(() => expect(order).toEqual(["rename starts"]));
      finishRename();
      await Promise.all([renaming, leaving]);

      expect(order).toEqual(["rename starts", "rename ends", "logout"]);
    } finally {
      onlineManager.setOnline(true);
      store.unmount();
    }
  });
});
