// follow-the-person.ts — the app shows whoever is logged in here in their own language and font, and this
// laptop's own once nobody is (UI-9, ADR-0039, 03 §7.4).
//
// Both choices are saved on the person (Mipangilio yangu, my-settings.tsx), and `me` answers them. The two
// places that learn who is here call this with the person they show: the home page of a registered device
// (at-the-device.tsx), after each PIN login, logout and quick switch, and the office's frame
// (office-frame.tsx), after a password's login. Each hands in its own `here`, which is already nobody from
// the press of Toka, and for a session the server refused, so the next person never sees the last one's.
//
//   the language    opened over the laptop's own, in memory only (setPersonsLanguage, i18n/language.ts)
//   the font        set on <html> by its role, data-font="second", which globals.css turns into the font;
//                   the page's font-sans is on <html>, so the whole page follows. Nobody: taken off, so
//                   the page shows the default one
//
// Undone as the frame leaves the page too: a blocked laptop's lock takes the place of every page
// (DeviceLock), and the last person's choices must go with them. Going from one frame to the other (the
// PIN welcome to Mipangilio yangu) undoes and sets again in one go, before the page is drawn, so nothing
// flickers. A reload shows the laptop's own for a moment, until `me` answers: accepted (the UI-9 card).
import { useEffect } from "react";

import { setPersonsLanguage } from "@/i18n/language";

import type { WhoIsHere } from "./who-is-here";

export function useFollowThePerson(here: WhoIsHere | undefined): void {
  // The two values, not the whole answer: a refresh of `me` that changes nothing else redoes nothing.
  const language = here?.user.language;
  const font = here?.user.font;

  useEffect(() => {
    // Nobody here: the laptop's own, which the last person's undoing below has already brought back.
    if (language === undefined || font === undefined) return;
    setPersonsLanguage(language);
    document.documentElement.dataset.font = font;
    return () => {
      setPersonsLanguage(null);
      delete document.documentElement.dataset.font;
    };
  }, [language, font]);
}
