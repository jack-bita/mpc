// card-heading.tsx — the heading row of a card on a worker's own page (UI-10): the card's <h2> on the left, and on the
// right the one button that changes what the whole card is about: Badilisha on Taarifa zake, Ongeza kazi on Cheo,
// Badilisha malipo on Malipo kwa siku. Jack asked for a page that reads "professional" on a phone (20 Nov 2026): each
// card named, and its button beside its name, as an app's settings page does, so a manager finds a change where the
// thing it changes is.
//
// The row wraps: on a narrow phone, a long Swahili heading and its button would squeeze each other, so the button goes
// under the heading instead. A card with no such button (Kuingia, whose two buttons sit under the PIN's line) still
// draws its heading here, so all four look alike.
//
// The card's section names itself by this heading (`aria-labelledby` with the same `id`), so a screen reader says
// which card a button belongs to.
import type { ReactNode } from "react";

export function CardHeading({
  id,
  title,
  children,
}: {
  /** The heading's id, which the card's section names itself by. */
  id: string;
  title: string;
  /** The card's button, if any: drawn on the right, or under the heading on a narrow phone. */
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
      <h2 id={id} className="text-lg font-semibold">
        {title}
      </h2>
      {children}
    </div>
  );
}
