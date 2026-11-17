// closures-section.tsx — Siku duka limefungwa, on Mipangilio ya duka (ATT-9): the days the whole shop is closed, a
// public holiday or a family funeral, from today on, soonest first. Under the rules and above Pande (Jack's picture,
// 16 Nov 2026). Each closed day is off, and not paid, whatever the reason (02 §12, ATT-8).
//
// An office screen: it asks GET /api/v1/shops/closures/ through the store of server answers (rule 5), in a place of
// its own (closures.ts). Anyone who works on a side may read the closures, as a worker may know when the shop is
// closed (ATT-8's route asks only that the person sees a side).
//
// The server picks the closures and their order (coming_closures, apps/shops/selectors.py): each active one whose last
// day is today or later, soonest first, a funeral that began two days ago among them, as its last day can still move.
// The page keeps that order. A cancelled closure, or one already over, isn't sent: their days can't change any more,
// and the audit trail keeps them.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { formatDay } from "@/lib/format";

import { type Closure, useClosures } from "./closures";

export function ClosuresSection() {
  const t = useTranslations("shopSettings.closures");
  const closures = useClosures();

  return (
    <section aria-labelledby="area-closures" className="grid gap-4">
      <div className="grid gap-2">
        <h2 id="area-closures" className="text-xl font-semibold">
          {t("title")}
        </h2>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {/* A failed read shows above the list, and keeps the last answer under it, as on the rules and Pande. */}
      <ApiErrorAlert error={closures.error} />
      {closures.data ? (
        closures.data.closures.length === 0 ? (
          // Said, not left blank: an empty space would read as a page still waiting.
          <p>{t("none")}</p>
        ) : (
          // role="list" written out, for Safari with VoiceOver (device-list.tsx).
          <ul role="list" className="grid gap-4">
            {closures.data.closures.map((closure) => (
              <li key={closure.id}>
                <ClosureLine closure={closure} />
              </li>
            ))}
          </ul>
        )
      ) : null}
    </section>
  );
}

/** One closure: its name, and its days. */
function ClosureLine({ closure }: { closure: Closure }) {
  const t = useTranslations("shopSettings.closures");
  // One day is one date, "09/12/2026"; a span is its first and last day, "20/11/2026 – 24/11/2026", both closed.
  const days =
    closure.first_day === closure.last_day
      ? formatDay(closure.first_day)
      : t("days", {
          first: formatDay(closure.first_day),
          last: formatDay(closure.last_day),
        });
  return (
    <div className="grid gap-3 rounded-lg border border-input p-4">
      <p className="grid gap-1 text-lg">
        <span className="font-semibold">{closure.name}</span>
        <span>{days}</span>
      </p>
    </div>
  );
}
