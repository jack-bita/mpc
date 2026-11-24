// refused-record.ts — why the server refused a record a laptop sent, in the shop's words (SYNC-11, CTRL-4). It owns the
// list of the push's reasons and their words, for the two places that say one: the counter's own warning
// (needs-attention.tsx) and the flag's page in the office, *Tofauti* (flag-words.ts), so the two never differ.
//
// The reasons get words of their own, not a form's (errors.*): those end with "try again" or "look at the marked boxes",
// which can't mend a record already refused. A code the app has no words for, as a newer server may send, is named by the
// code itself, so the manager can still look it up.
//
// Here, beside the word books, not in src/api/: the counter lock keeps counter screens out of src/api/ (rule 5).
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

/** The server's reasons the app has words for (PushedAnswer's codes, apps/sync/push.py), by the key
 * of their words: a key of the word book can't hold the code's dot. */
const REASONS = {
  "document.type_unknown": "typeUnknown",
  "document.version_unknown": "versionUnknown",
  "document.maker_unknown": "makerUnknown",
  // A record a rescue file carried here (SYNC-12): named as made on no other laptop of the shop, or loaded
  // by someone not of it. A file edited by hand, most likely: the manager decides.
  "document.carried_from_unknown": "carriedFromUnknown",
  "document.loaded_by_unknown": "loadedByUnknown",
  // Its payload isn't in its type's shape: a bug in the app, or a file edited by hand.
  invalid: "shapeWrong",
  "id.taken": "idTaken",
  // A clock-in whose photo's label the server's photo row refused (ATT-3): a bug in the camera's code, as
  // labelPhoto refuses the same at the counter, so the tap waits for a manager like any other refused.
  "attachment.not_an_image": "photoNotAnImage",
  "attachment.too_big": "photoTooBig",
  "attachment.empty": "photoEmpty",
  "attachment.sha256_invalid": "photoLabelBroken",
} as const;

function knownReason(code: string): code is keyof typeof REASONS {
  return Object.hasOwn(REASONS, code);
}

/** The words for a reason the server refused a record for. */
export function useRefusedRecordWords(): (code: string) => string {
  const t = useTranslations("needsAttention.reasons");
  return (code) =>
    knownReason(code) ? t(REASONS[code]) : t("other", { code });
}
