// shop-lists.ts — a made-up shop's lists as the sync routes send them: the bootstrap's answer, and
// records for pull pages (SYNC-7). Tests only. Fake data: every id, name and number here is made up.
import type { components } from "@/api/schema";

import { DAWA, DAWA_LAPTOP } from "./devices";

type Schemas = components["schemas"];

export const DAWA_SIDE: Schemas["SideRecord"] = {
  id: DAWA.id,
  code: "D",
  name: "Dawa",
  sale_flow: "one_screen",
  is_live: true,
};

export const DAWA_DRAWER: Schemas["PaymentAccountRecord"] = {
  id: "019a5e00-0000-7000-8000-0000000000e1",
  kind: "cash_drawer",
  name: "Droo ya Dawa",
  provider: "",
  number: "",
  sides: [DAWA.id],
};

export const ASHA: Schemas["StaffRecord"] = {
  id: "019a5e00-0000-7000-8000-0000000000c2",
  full_name: "Asha Mfano",
  display_name: "Asha",
  status: "active",
  pin_changed_at: null,
  language: "sw",
  font: "default",
  permissions: { every_side: [], sides: [] },
};

/** The shop's idle lock: 15 minutes from 1 November, for the whole shop. */
export const IDLE_15: Schemas["SettingRecord"] = {
  id: "019a5e00-0000-7000-8000-000000000101",
  key: "session.idle_minutes",
  side: null,
  value: "15",
  effective_from: "2026-11-01",
};

export const IDLE_RULE: Schemas["SettingKeyRecord"] = {
  key: "session.idle_minutes",
  kind: "whole",
  scope: "shop",
  default: "10",
};

/** What GET /api/sync/v1/bootstrap/ answers for that shop, the Dawa laptop's, valid at change 120, to a
 * laptop whose last record was #57. */
export const BOOTSTRAP: Schemas["BootstrapAnswer"] = {
  shop: DAWA_LAPTOP.shop.id,
  cursor: 120,
  last_device_seq: 57,
  side: [DAWA_SIDE],
  payment_account: [DAWA_DRAWER],
  staff: [ASHA],
  setting: [IDLE_15],
  setting_keys: [IDLE_RULE],
};
