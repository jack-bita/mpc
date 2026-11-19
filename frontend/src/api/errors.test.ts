// errors.test.ts — every code the API sends has a sentence in both word books, and a failed call is
// shown in the shop's words (UI-2, ADR-0040).
//
// CODES_THE_API_SENDS is kept by hand: some codes are built as the server runs (`f"{secret}.own"`,
// apps/people/services.py), so no test can find them all in the backend. It holds every code a route,
// or a model rule behind it, can send today, and those of the screen that sets a PIN (PPL-12). Codes that
// only stop a bug, like device.key_not_hashed, are left to the general sentence. A card that adds a code
// adds it here, with its two sentences; the third test fails on a sentence whose code left the list.
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
  "not_a_dict",
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
  // PIN login (AUTH-4), and the screen that sets a PIN (PPL-12).
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
  // Jaribu demo, tapped where the demo shop isn't the only shop, or with no demo shop yet (OPS-3).
  "demo.closed",
  // The demo's logins stay as the seed made them (DATA-1): a PIN, a temporary password and a person's own.
  "demo.logins_fixed",
  // The demo's sides stay as the seed made them, switched on and named, so every visitor's one tap works (SHOP-3,
  // and a rename or a new side since SHOP-5's review).
  "demo.sides_fixed",
  // The demo's people stay as the seed made them, so no visitor takes Asha or Baraka off another's PIN tiles; a
  // worker a visitor added can be changed (PPL-4).
  "demo.people_fixed",
  // And no worker gets a phone there, so no stranger's real number is shown to every visitor (PPL-10).
  "demo.phones_fixed",
  // On the demo, a visitor's rule starts tomorrow or later, after the night's seed, and keeps no note, which every
  // reader would see under the rule (SHOP-5's second review).
  "demo.rules_from_tomorrow",
  "demo.no_note",
  // And a visitor's closure, its cancel or its new last day touches only days from tomorrow on (ATT-8).
  "demo.closures_from_tomorrow",
  // Days the shop is closed (ATT-8): add_closure's own date_past, Closure.clean()'s two (name_blank,
  // ends_before_it_starts), the table's exclusion rule (overlaps), and its status rule, which only code that skips
  // the services could break; it has its words all the same, as setting.key_invalid has.
  "closure.date_past",
  "closure.ends_before_it_starts",
  "closure.name_blank",
  "closure.overlaps",
  "closure.status_unknown",
  // And its two changes' (cancel_closure, change_last_day): a reason always, a closure already cancelled, and a
  // cancel of one already started, whose last day is moved instead; a moved last day refused for a day before
  // today is date_past above.
  "closure.reason_required",
  "closure.not_active",
  "closure.started",
  // A photo's file, sent by a laptop after the record that named it (CTRL-3): an id this shop doesn't hold, or whose
  // record hasn't arrived yet; over 1 MB; not a JPEG or a WebP by its first bytes; or not the file its record named.
  "attachment.not_found",
  "attachment.too_big",
  "attachment.not_an_image",
  "attachment.file_differs",
  // A photo sent with no length (in pieces, as a proxy may send it): never read, and sent again (411).
  "attachment.length_required",
  // And on an office screen (CTRL-3's GET): a photo whose record came but whose file the laptop hasn't sent yet, and a
  // photo whose file was removed, 90 days after its pay run (ATT-7).
  "attachment.file_waiting",
  "attachment.file_removed",
  // And from the push (ATT-3): a clock-in whose photo's label the photo's row refuses, the whole tap refused under
  // the photo's code (_refused_label, apps/staffpay/documents.py). too_big and not_an_image are above; these two
  // only a bug in the laptop's code could send, as labelPhoto writes the label.
  "attachment.empty",
  "attachment.sha256_invalid",
  "staff.left",
  "staff.other_shop",
  "staff.reason_required",
  "staff.temporary_password_open",
  // Who may suspend a person, bring them back or mark them left: the PIN's rule, with codes of its own (PPL-4).
  "staff.own",
  "staff.superuser_only",
  "staff.more_keys",
  // Adding a worker (PPL-4): two current workers never share a nickname, whatever the letter case.
  "staff.display_name_taken",
  // Suspending, bringing back and marking left from the office (PPL-4): a person already suspended, one not
  // suspended, and a last day ahead of today or before the first day.
  "staff.not_active",
  "staff.not_suspended",
  "staff.left_in_future",
  "staff.left_before_start",
  // A worker who comes back (PPL-11): hired again from a job that hasn't ended, by someone back already, by someone
  // working at another shop now, from before the last day; and Ongeza's phone of a worker who left, which the form
  // shows in its own words, with Mwajiri tena.
  "staff.not_left",
  "staff.already_member",
  "staff.works_elsewhere",
  "staff.back_before_left",
  "staff.left_here",
  // Giving and taking away roles and extra keys from the office (PPL-7): the same one twice on a side, one already
  // taken away, and the Owner role, the superuser's alone. Who may take one away answers with the staff.* codes above.
  "role.already_given",
  "role.already_ended",
  "role.superuser_only",
  "permission.already_given",
  "permission.already_ended",
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
  // A pushed document set aside (SYNC-4): its type or version the server doesn't take, or a maker not of this
  // shop. The laptop shows these beside the document under "needs attention".
  "document.type_unknown",
  "document.version_unknown",
  "document.maker_unknown",
  // A record a rescue file carried from another laptop (SYNC-12): named as made on a laptop that is no other
  // laptop of this shop, or loaded by someone not of this shop.
  "document.carried_from_unknown",
  "document.loaded_by_unknown",
  // A rule's new value, refused (SHOP-3): set_setting's own two (date_past, side_required), Setting.clean()'s
  // three (key_unknown, side_not_allowed, value_invalid), and the table's own two rules (key_invalid, value_blank).
  // Those last two never come through set_setting today, as a field's own check or clean() answers first and
  // full_clean then skips that field's table rules; they have their words all the same, in case a route ever sends one.
  // And set_setting's third (ATT-2): a time of the attendance day out of the day's order, beside the value's box.
  "setting.date_past",
  "setting.key_invalid",
  "setting.key_unknown",
  "setting.out_of_order",
  "setting.side_not_allowed",
  "setting.side_required",
  "setting.value_blank",
  "setting.value_invalid",
  // Sides (CORE-6), and a side's band (SHOP-4).
  "side.band_unknown",
  "side.code_invalid",
  "side.code_taken",
  "side.name_blank",
  "side.sale_flow_unknown",
  // allauth's password routes (AUTH-3, AUTH-6), read into the one shape by src/api/allauth.ts. Beside
  // `required` and the checker's codes above: the login's, the reset link's, the change's, and our
  // adapter's two (apps/people/accounts.py).
  "email_password_mismatch",
  "phone_password_mismatch",
  "invalid_phone",
  "phone.invalid",
  // A fix that would take off the only phone someone with a password logs in by (PPL-10's review).
  "phone.needed_to_log_in",
  "too_many_login_attempts",
  "invalid_password_reset",
  "enter_current_password",
  "password.same_as_temporary",
  // Two the app names itself, for a status allauth sends with no code (UI-5): a login while this
  // browser holds a session (409), and a switched-off person with the right password (401).
  "login.already_in",
  "login.switched_off",
  // One the laptop says itself, at a PIN login with no network: no check of this PIN here (SYNC-10).
  "pin.offline_first",
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
