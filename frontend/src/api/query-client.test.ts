// query-client.test.ts — which failed reads the store asks again: never a refusal the server meant,
// a few times a dropped network or a broken server (UI-2).
import { describe, expect, it } from "vitest";

import { READ_RETRIES, shouldRetry } from "./query-client";
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
