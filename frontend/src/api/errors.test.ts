// errors.test.ts — every code the API sends has a sentence in both word books, and a failed call is
// shown in the shop's words (UI-2, ADR-0040).
//
// CODES_THE_API_SENDS is kept by hand: some codes are built as the server runs (`f"{secret}.own"`,
// apps/people/services.py), so no test can find them all in the backend. It holds every code a route,
// or a model rule behind it, can send today, and those of the PIN screen to come (PPL-4). Codes that
// only stop a bug, like device.key_not_hashed, are left to the general sentence. A card that adds a code adds it here, with
// its two sentences; the second test fails on a sentence whose code left the list.
import { createTranslator } from "use-intl/core";
import { describe, expect, it } from "vitest";

import type { Words } from "@/i18n/codes";
import { LANGUAGES, MESSAGES, type Language } from "@/i18n/language";
import { sentences } from "@/test/language";

import { apiErrorMessage, apiFieldMessages } from "./errors";
import { ApiRefusal, NoConnection } from "./refusal";

const CODES_THE_API_SENDS = [
  // The one shape's own codes, and what every route can answer (apps/core/api/errors.py).
  "invalid",
  "bad_request",
  "version_conflict",
  "server_error",
  "not_found",
  "not_authenticated",
  "authentication_failed",
  "permission_denied",
  "method_not_allowed",
  "not_acceptable",
  "unsupported_media_type",
  "parse_error",
  "throttled",
  // DRF's codes beside a field.
  "required",
  "null",
  "blank",
  "max_length",
  "min_length",
  "max_value",
  "min_value",
  "max_digits",
  "max_decimal_places",
  "max_whole_digits",
  "invalid_choice",
  "does_not_exist",
  "incorrect_type",
  "unique",
  "not_a_list",
  "empty",
  "max_string_length",
  "null_characters_not_allowed",
  "surrogate_characters_not_allowed",
  // Ids the app makes for new rows (03 §5.10).
  "id.taken",
  "id.not_uuid7",
  // Asked on every visit (apps/people/selectors.py, authentication.py).
  "device.blocked",
  "session.wrong_device",
  "shop.suspended",
  "staff.suspended",
  "staff.choose_shop",
  "password.must_change",
  // PIN login (AUTH-4), and the screen that sets a PIN (PPL-4).
  "pin.wrong",
  "pin.locked",
  "pin.own",
  "pin.superuser_only",
  "pin.more_keys",
  "pin.not_four_digits",
  "pin.too_easy",
  // A temporary password (AUTH-6), and the password checker's codes.
  "password.own",
  "password.superuser_only",
  "password.more_keys",
  "password.no_login_name",
  "password_too_short",
  "password_too_common",
  "password_entirely_numeric",
  "password_too_similar",
  "staff.left",
  "staff.other_shop",
  "staff.reason_required",
  "staff.temporary_password_open",
  // Devices and pairing (AUTH-5).
  "device.name_blank",
  "device.name_taken",
  "device.reason_required",
  "device.not_active",
  "device.not_blocked",
  "pairing.code_invalid",
  "pairing.code_unknown",
  "pairing.code_used",
  "pairing.code_expired",
  "pairing.already_paired",
  // Sides (CORE-6).
  "side.code_invalid",
  "side.code_taken",
  "side.name_blank",
  "side.sale_flow_unknown",
];

function wordsIn(language: Language): Words {
  // The same book a screen gets; onError throws, so a sentence that can't be filled in fails the test.
  const t = createTranslator({
    locale: language,
    messages: MESSAGES[language],
    onError: (error) => {
      throw error;
    },
  });
  return t as unknown as Words;
}

function refusal(code: string, extra: Partial<ApiRefusal["body"]> = {}) {
  return new ApiRefusal(400, {
    code,
    message: "",
    fields: {},
    params: {},
    ...extra,
  });
}

const swahili = wordsIn("sw");

describe("the word books", () => {
  it("hold no code twice on the list", () => {
    expect(new Set(CODES_THE_API_SENDS).size).toBe(CODES_THE_API_SENDS.length);
  });

  it.each(LANGUAGES)(
    "%s: hold a sentence for every code the API sends",
    (language) => {
      const book = sentences(MESSAGES[language]);
      const missing = CODES_THE_API_SENDS.filter(
        (code) => !book.has(`errors.${code}`),
      );
      expect(missing).toEqual([]);
    },
  );

  it.each(LANGUAGES)(
    "%s: hold no sentence for a code off the list",
    (language) => {
      const listed = new Set(
        CODES_THE_API_SENDS.map((code) => `errors.${code}`),
      );
      const extra = [...sentences(MESSAGES[language]).keys()].filter(
        (key) => key.startsWith("errors.") && !listed.has(key),
      );
      expect(extra).toEqual([]);
    },
  );
});

describe("apiErrorMessage", () => {
  it("shows a refusal in Swahili", () => {
    expect(apiErrorMessage(swahili, refusal("version_conflict"))).toBe(
      "Mtu mwingine amebadilisha hiki wakati huo huo. Fungua upya, kisha ujaribu tena.",
    );
  });

  it("shows the same refusal in English after the switch", () => {
    expect(apiErrorMessage(wordsIn("en"), refusal("version_conflict"))).toBe(
      "Someone else changed this at the same time. Reload it, then try again.",
    );
  });

  it("fills in a refusal's values, as its code's sentence asks", () => {
    // How a code's sentence is filled in is src/i18n/codes.test.ts's; here, that a refusal's params reach it.
    const locked = refusal("pin.locked", { params: { wait: 300 } });

    expect(apiErrorMessage(swahili, locked)).toBe(
      "PIN zimekosewa mara nyingi. Jaribu tena baada ya dakika 5.",
    );
  });

  it("says the server couldn't be reached when no answer came", () => {
    // What the client throws when fetch got no answer at all (client.ts).
    const dropped = new NoConnection(new TypeError("Failed to fetch"));

    expect(apiErrorMessage(swahili, dropped)).toBe(
      "Imeshindwa kufika kwenye seva. Angalia mtandao, kisha ujaribu tena.",
    );
  });

  it("doesn't blame the network for a bug", () => {
    // A bug in a screen throws a TypeError too, as fetch does when the network drops: only the client's
    // NoConnection means no answer came.
    const bug = new TypeError("ask is not a function");

    expect(apiErrorMessage(swahili, bug)).toBe("Kuna hitilafu. Jaribu tena.");
  });

  it("still says something for anything else that was thrown", () => {
    expect(apiErrorMessage(swahili, new Error("a bug"))).toBe(
      "Kuna hitilafu. Jaribu tena.",
    );
  });
});

describe("apiFieldMessages", () => {
  it("gives each wrong field the sentence for its first code", () => {
    const wrong = refusal("invalid", {
      fields: {
        name: ["blank"],
        "lines.1.quantity": ["required", "max_value"],
      },
    });

    expect(apiFieldMessages(swahili, wrong)).toEqual({
      name: "Sehemu hii haiwezi kuwa tupu.",
      "lines.1.quantity": "Jaza sehemu hii.",
    });
  });

  it("gives nothing when no field was wrong", () => {
    expect(apiFieldMessages(swahili, refusal("pin.wrong"))).toEqual({});
    expect(apiFieldMessages(swahili, new NoConnection(undefined))).toEqual({});
  });
});
