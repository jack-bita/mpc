// staff-picker.tsx — the PIN screen's first step on a shared laptop: "Wewe ni nani?", with a tile for each
// person who works at the shop, and a tap on your own (UI-4, 03 §5.9). The PIN pad comes next.
//
// The people come from the device's own route, GET /api/devices/v1/staff/, asked with its key: names only,
// A to Z, and only those who can log in today. Sync will keep a copy on the device, so the picker works
// offline too (SYNC-2, SYNC-10); until then it needs the network, as the PIN login itself does.
//
// A tile shows the full name in large letters with the nickname under it, until photos come (PPL-4; 02 §5).
//
// "use client": it asks the server and its words, both in the browser only.
"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";

/** One person, as the server sends a tile's worth: id, full name, nickname. */
export type PinScreenStaff = components["schemas"]["PinScreenStaff"];

/** The list's place in the store of server answers. */
export const SHOP_STAFF = ["devices", "staff"] as const;

/** Who works here, asked with the device's key. */
function useShopStaff() {
  return useQuery({
    queryKey: SHOP_STAFF,
    queryFn: () => answerOf(api.GET("/api/devices/v1/staff/")),
  });
}

export function StaffPicker({
  onPick,
}: {
  /** Called with the person whose tile was tapped. */
  onPick: (person: PinScreenStaff) => void;
}) {
  const t = useTranslations("login.picker");
  const staff = useShopStaff();
  // Empty while the answer is on its way, and when the read failed with nothing read before it.
  const people = staff.data;

  return (
    <div className="grid gap-6">
      {/* The heading of this step of the login screen: the PIN pad's step has the person's name. */}
      <h1 className="text-3xl font-semibold">{t("title")}</h1>
      {/* Nothing while there is no error. Above the tiles, not in their place: if a refresh fails, the
          people last read stay, with the reason above them. */}
      <ApiErrorAlert error={staff.error} />
      {/* A new shop, before the owner adds its people: the reason, not an empty screen. */}
      {people?.length === 0 && <p>{t("empty")}</p>}
      {people && people.length > 0 && (
        // A list, so a screen reader says how many people there are. role="list" written out: Safari with
        // VoiceOver stops calling a <ul> a list once Tailwind styles its bullets away.
        <ul role="list" className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {people.map((person) => (
            <li key={person.id}>
              {/* The shop's button, so a tile has its colours, focus ring and press look, all checked in
                  button.test.tsx. Two lines don't fit its 52 px, so it grows (h-auto), and never shrinks
                  below a finger's size (min-h, from the same token). */}
              <Button
                kind="second"
                className="h-auto min-h-(--control-big) w-full flex-col gap-1 py-4 whitespace-normal"
                onClick={() => onPick(person)}
              >
                <span className="text-2xl">{person.full_name}</span>
                {/* A space between the two names, so a screen reader says "Asha Mfano Asha", not
                    "Asha MfanoAsha". Invisible: the tile sets its lines one under the other. */}{" "}
                <span className="text-lg font-normal">
                  {person.display_name}
                </span>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
