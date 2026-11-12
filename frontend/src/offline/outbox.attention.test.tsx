// outbox.attention.test.tsx — the needs-attention list (SYNC-8): the records the server refused, set
// aside by the push with its reason, read live from the laptop's database. SYNC-11 shows it on a screen.
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { DAWA_LAPTOP } from "@/test/devices";
import { ASHA } from "@/test/shop-lists";

import {
  saveDocument,
  useNeedsAttention,
  type Draft,
  type SavedDocument,
} from "./outbox";
import { LAST_DEVICE_SEQ } from "./sync/meta";
import { shopDatabase } from "./this-shop";

const CLOCK_IN: Draft = {
  type: "clock",
  schema_version: 1,
  created_by: ASHA.id,
  payload: { kind: "in", last_server_time: "2026-11-12T04:58:00Z" },
};

const db = () => shopDatabase(DAWA_LAPTOP.shop.id);

/** What the push writes for an invalid answer (push.ts). */
async function setAside(saved: SavedDocument, reason: string): Promise<void> {
  await db().outbox.update(saved.id, {
    status: "needs_attention",
    last_error: reason,
  });
}

// The Dawa laptop, registered and filled, its last record #57, with three clock-ins: #58, #59, #60.
let made: SavedDocument[];
beforeEach(async () => {
  saveDevice(DAWA_LAPTOP);
  await db().meta.put({ key: LAST_DEVICE_SEQ, value: 57 });
  made = [];
  for (let i = 0; i < 3; i++) made.push(await saveDocument(db(), CLOCK_IN));
});

describe("the needs-attention list", () => {
  it("lists the records set aside, in number order, each with its reason", async () => {
    const [first, second, third] = made;
    await setAside(third!, "document.maker_unknown");
    await setAside(first!, "document.type_unknown");

    const { result } = renderHook(() => useNeedsAttention());

    // #59 still waits to go: it isn't on the list. Each document as its drawer keeps it, with no number
    // (its outbox row keeps that): toEqual passes over a key whose value is undefined.
    await waitFor(() =>
      expect(result.current).toEqual([
        {
          document: { ...first, device_seq: undefined },
          device_seq: 58,
          reason: "document.type_unknown",
        },
        {
          document: { ...third, device_seq: undefined },
          device_seq: 60,
          reason: "document.maker_unknown",
        },
      ]),
    );
    expect(result.current?.map((record) => record.document.id)).not.toContain(
      second!.id,
    );
  });

  it("redraws by itself when the push sets one aside", async () => {
    const { result } = renderHook(() => useNeedsAttention());
    await waitFor(() => expect(result.current).toEqual([]));

    await act(() => setAside(made[1]!, "document.type_unknown"));

    await waitFor(() =>
      expect(result.current?.map((record) => record.device_seq)).toEqual([59]),
    );
  });

  it("is nothing on a laptop not registered", async () => {
    saveDevice(null);

    const { result } = renderHook(() => useNeedsAttention());

    // No shop, so no database to read.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(result.current).toBeUndefined();
  });
});
