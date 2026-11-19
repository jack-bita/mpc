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
    band: "blue",
  },
  shop: {
    id: "019a5e00-0000-7000-8000-0000000000a1",
    name: "MPC",
    code: "MPC",
    timezone: "Africa/Dar_es_Salaam",
    currency: "TZS",
    default_language: "sw",
    demo: false,
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
    timezone: "Africa/Dar_es_Salaam",
    currency: "TZS",
    language: "sw",
    demo: false,
  },
  homeSide: {
    id: "019a5e00-0000-7000-8000-0000000000d1",
    code: "D",
    name: "Dawa",
    band: "blue",
  },
};

/** The look of the band under the top bar, or null when it shows none (SideBand's `data-look`). */
export function bandUnderTheBar(): string | null {
  return (
    document.querySelector("header [data-look]")?.getAttribute("data-look") ??
    null
  );
}

/** The Dawa and Vyakula sides, as `me` names them, each with its band: Vyakula striped, like the Foods bags
 * (SHOP-4). */
export const DAWA = {
  id: DAWA_LAPTOP.homeSide.id,
  code: "D",
  name: "Dawa",
  band: "blue" as const,
};
export const VYAKULA = {
  id: "019a5e00-0000-7000-8000-0000000000f1",
  code: "F",
  name: "Vyakula",
  band: "striped" as const,
};

/** What GET /api/auth/me/ answers for someone at MPC on their own phone, holding `keys` on each side
 * named. Fake people: made-up names. */
export function whoIsHere(
  keys: {
    side: {
      id: string;
      code: string;
      name: string;
      band: components["schemas"]["SideBandEnum"];
    };
    permissions: string[];
  }[],
): components["schemas"]["WhoIsHere"] {
  return {
    user: {
      id: "019a5e00-0000-7000-8000-0000000000b1",
      full_name: "Neema Mfano",
      language: "sw",
      font: "default",
    },
    staff: {
      id: "019a5e00-0000-7000-8000-0000000000c1",
      display_name: "Neema",
      job_title: "Meneja",
    },
    shop: DAWA_LAPTOP_ANSWER.shop,
    device: null,
    home_side: null,
    must_change_password: false,
    // The shop's minutes, which a shared laptop's screen locks by; a phone that is only the person's own
    // never shows that screen (UI-4).
    idle_minutes: 15,
    permissions: {
      whole_shop: [],
      sides: keys.map(({ side, permissions }) => ({ ...side, permissions })),
    },
  };
}
