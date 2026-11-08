// follow-the-person.test.tsx — the app shows whoever is logged in in their own language and font, and the
// laptop's own once nobody is (UI-9, ADR-0039).
import { describe, expect, it } from "vitest";
import { useTranslations } from "use-intl";

import { setLanguage, STORAGE_KEY } from "@/i18n/language";
import { DAWA, whoIsHere } from "@/test/devices";
import { render } from "@/test/render";

import { useFollowThePerson } from "./follow-the-person";
import type { WhoIsHere } from "./who-is-here";

// Neema as she saved her choices: English, in the second font. Fake people.
const NEEMA = whoIsHere([{ side: DAWA, permissions: [] }]);
const NEEMA_IN_ENGLISH: WhoIsHere = {
  ...NEEMA,
  user: { ...NEEMA.user, language: "en", font: "second" },
};

/** A frame in miniature: it follows whoever it is handed, and shows one word from the open book. */
function Frame({ here }: { here: WhoIsHere | undefined }) {
  useFollowThePerson(here);
  const t = useTranslations("login");
  return <p>{t("logout")}</p>;
}

const page = document.documentElement;

describe("following the person", () => {
  it("opens the person's language, and sets their font on the page", () => {
    render(<Frame here={NEEMA_IN_ENGLISH} />);

    expect(document.body.textContent).toContain("Log out");
    expect(page.lang).toBe("en");
    expect(page.dataset.font).toBe("second");
  });

  it("names the default font too, for someone who keeps it", () => {
    render(<Frame here={NEEMA} />);

    expect(document.body.textContent).toContain("Toka");
    expect(page.dataset.font).toBe("default");
  });

  it("goes back to the laptop's own once nobody is here", () => {
    // Neema presses Toka: the tiles are for whoever is next, in the laptop's language.
    const { rerender } = render(<Frame here={NEEMA_IN_ENGLISH} />);

    rerender(<Frame here={undefined} />);

    expect(document.body.textContent).toContain("Toka");
    expect(page.dataset.font).toBeUndefined();
  });

  it("goes back to the laptop's own language, whichever it is", () => {
    // The laptop was switched to English from the bar while nobody was logged in; Neema reads Swahili.
    setLanguage("en");
    const { rerender } = render(
      <Frame here={{ ...NEEMA, user: { ...NEEMA.user, language: "sw" } }} />,
    );
    expect(document.body.textContent).toContain("Toka");

    rerender(<Frame here={undefined} />);

    expect(document.body.textContent).toContain("Log out");
  });

  it("never saves the person's language as the laptop's own", () => {
    // Saved on the browser, Neema's English would greet the next person at the tiles.
    const { rerender } = render(<Frame here={NEEMA_IN_ENGLISH} />);
    rerender(<Frame here={undefined} />);

    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("goes back to the laptop's own when the frame leaves the page", () => {
    // A blocked laptop's lock takes the place of every page (DeviceLock): the frame goes, and with it the
    // last person's choices, or the lock's own language button would seem to do nothing.
    function Lock() {
      const t = useTranslations("login");
      return <p>{t("logout")}</p>;
    }
    const { rerender } = render(<Frame here={NEEMA_IN_ENGLISH} />);

    rerender(<Lock />);

    expect(document.body.textContent).toContain("Toka");
    expect(page.lang).toBe("sw");
    expect(page.dataset.font).toBeUndefined();
  });

  it("follows the next person at once, on a quick switch", () => {
    const { rerender } = render(<Frame here={NEEMA_IN_ENGLISH} />);

    rerender(<Frame here={NEEMA} />);

    expect(document.body.textContent).toContain("Toka");
    expect(page.dataset.font).toBe("default");
  });
});
