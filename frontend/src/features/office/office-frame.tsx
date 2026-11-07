// office-frame.tsx — the office area's frame: the top bar names who is logged in and their shop, with
// Toka; someone who isn't logged in is sent to the way in; a shared laptop locks itself (UI-5, 03 §7.1).
//
// Every office screen asks the server for everything, and needs a login. So the frame asks `me`
// (useWhoIsHere, one answer shared with the screens), and:
//   someone logged in          their name, their shop and Toka in the bar: a manager's own phone knows no
//                              device, so only the login says which shop it is at
//   nobody (not_authenticated)  away to the way in: the password login on a phone, and the PIN login at
//                              a registered laptop, whose home page it is (UI-4)
//   refused for a reason        stays: each screen shows why (a suspension, a shop switched off)
//   no answer, or a 5xx         stays, as it was: the offline banner says Inahitaji mtandao
//   on a temporary password     Chagua nenosiri lako in place of the screen (choose-password.tsx), as
//                              every office route refuses them until they choose (password.must_change)
//
// `me` alone says whether the password is temporary, as every other office route answers 403 then
// (AUTH-4). A temporary password set later ends the person's sessions (AUTH-6), so every session meets
// the mark at its login, where `me` is asked: the frame never needs to watch the other routes' refusals.
//
// Toka ends the session on the server first, sent again until the server hears it, with the screen
// hidden from the press; then the store forgets the person (forgetTheLastPerson), and they go to the way
// in. The PIN login's Toka works the same way (at-the-device.tsx, UI-4).
//
// "use client": it asks use-intl for words, calls the server, and reads the device's saved copy.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { forgetTheLastPerson, mayPassLater } from "@/api/query-client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { AppFrame } from "@/components/app-frame";
import { Button } from "@/components/design/button";
import { OfflineBanner } from "@/components/offline-banner";
import { useThisDevice } from "@/features/devices/this-device";
import { ChoosePassword } from "@/features/login/choose-password";
import { useIdleLock } from "@/features/login/idle-lock";
import { sideAt, useWhoIsHere } from "@/features/people/who-is-here";

export function OfficeFrame({ children }: { children: ReactNode }) {
  const t = useTranslations("login");
  const me = useWhoIsHere();
  const device = useThisDevice();
  const router = useRouter();
  const store = useQueryClient();
  // The way in: the PIN login at a registered laptop, whose home page it is; the password login on a
  // phone that is only the person's own.
  const wayIn = device ? "/" : "/login/";

  const logout = useMutation({
    // Needs only the session and the CSRF token, so it works for a suspended person too (AUTH-4).
    mutationFn: () => answerOf(api.POST("/api/auth/logout/")),
    // Sent again while no answer comes, with no limit, until the server hears it: given up, the session
    // would outlive the press, on a phone that is lent or a laptop the next person uses (UI-4). A refusal
    // the server meant gets the same no again, so it is never sent twice.
    retry: (_tries, error) => mayPassLater(error),
    onSuccess: async () => {
      await forgetTheLastPerson(store);
      // replace, not push: Back from the login shouldn't open the office again.
      router.replace(wayIn);
    },
  });
  // From the press until the page has moved on, offline too: the person and the screen are hidden. Still
  // true once it worked, while the way in opens: the store has forgotten the screen's answers by then.
  const leaving = logout.isPending || logout.isSuccess;

  // The server refused this browser's session. Under 500 only: a 5xx is the server broken, and says
  // nothing about who is here.
  const refused =
    me.error instanceof ApiRefusal && me.error.status < 500 ? me.error : null;
  // Nobody logged in, and the server says only that: no reason to read. Any other refusal is a reason,
  // which the screen shows, and the person stays to read it.
  const nobody = refused?.body.code === "not_authenticated";
  const hadAnswer = me.data !== undefined;
  useEffect(() => {
    if (!nobody) return;
    // A session that ended while the screen showed its person, at its idle time or by a logout in another
    // tab: TanStack keeps their last answer beside the refusal. Forgotten first, or the login page would
    // read it, and send them straight back here.
    if (hadAnswer) void forgetTheLastPerson(store);
    // replace, not push: Back from the login shouldn't open a screen that sends them to it again.
    router.replace(wayIn);
  }, [nobody, hadAnswer, store, wayIn, router]);

  // Who is logged in, as `me` last said: TanStack keeps the last answer through a dropped network, which
  // leaves the person where they are. Nobody once the server refused them, or from the press of Toka.
  const here = refused || leaving ? undefined : me.data;
  // At a registered laptop, the side the person works on, as the PIN login names it (UI-4); a phone knows
  // no side, and the bar names only the shop.
  const side = here && device ? sideAt(here, device.homeSide.id) : undefined;

  function leave() {
    logout.mutate();
  }

  // A shared laptop locks itself after the shop's idle minutes untouched, a password's session as a
  // PIN's: `me` gives a password the shop's minutes for this (UI-4). A phone that is only the person's own
  // doesn't: nobody else stands at it, and its session ends on the server by itself.
  useIdleLock(device ? here?.idle_minutes : undefined, leave);

  return (
    <AppFrame
      area="office"
      notice={<OfflineBanner />}
      shop={here?.shop.name}
      person={here?.staff.display_name}
      side={side ? { name: side.name } : undefined}
      actions={
        here ? (
          // The bar kind: the only kind that can sit on the green; normal height, as the language button's.
          <Button kind="bar" size="normal" onClick={leave}>
            {t("logout")}
          </Button>
        ) : undefined
      }
    >
      {/* role="status": a screen reader says its words as they change. Always on the page, empty and
          hidden from the eye while there is nothing to say, as one that comes with its words in it often
          goes unsaid (offline-banner.tsx). */}
      <p role="status" className={leaving ? "text-lg" : "sr-only"}>
        {leaving ? t("leaving") : null}
      </p>
      {/* A logout the server refused: why, and the person stays where they are. */}
      <ApiErrorAlert error={logout.error} />
      {leaving ? null : here?.must_change_password ? (
        <ChoosePassword />
      ) : (
        children
      )}
    </AppFrame>
  );
}
