// devices.ts — a made-up registered device, for tests: the server's answer, and the copy the app keeps
// of it (UI-3). Tests only. Fake data: "MPC" is the shop the project is built for, and every id and
// name here is made up.
import type { components } from "@/api/schema";
import type { ThisDevice } from "@/features/devices/this-device";

/** What GET /api/devices/v1/me/ answers for the Dawa side's laptop. */
export const DAWA_LAPTOP_ANSWER: components["schemas"]["DeviceMe"] = {
  device: {
    id: "019a5e00-0000-7000-8000-000000000001",
    name: "Laptop Dawa",
    code: 1,
    status: "active",
  },
  home_side: {
    id: "019a5e00-0000-7000-8000-0000000000d1",
    code: "D",
    name: "Dawa",
  },
  shop: {
    id: "019a5e00-0000-7000-8000-0000000000a1",
    name: "MPC",
    code: "MPC",
  },
};

/** The same device, as the app keeps it (this-device.ts). */
export const DAWA_LAPTOP: ThisDevice = {
  id: "019a5e00-0000-7000-8000-000000000001",
  name: "Laptop Dawa",
  code: 1,
  shop: {
    id: "019a5e00-0000-7000-8000-0000000000a1",
    name: "MPC",
    code: "MPC",
  },
  homeSide: {
    id: "019a5e00-0000-7000-8000-0000000000d1",
    code: "D",
    name: "Dawa",
  },
};
