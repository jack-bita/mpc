// page-news.ts — the one line a form's own page leaves for the worker's page it lands on (UI-11): "Juma ameongezwa…"
// after Ongeza, "Taarifa za Juma zimehifadhiwa." after Badilisha. Since UI-11 the four long forms are pages of their
// own, so the line that says what a change did is written on one page and shown on the next, on the card it belongs to,
// as it was when the forms opened inside the worker's page.
//
// Kept in the tab's memory, a value in this file, not in the address nor in sessionStorage (a default of the card):
// moving between the app's pages keeps the app loaded, so the note survives the move; a refresh loads the app afresh,
// so the line never shows a second time, as news of a moment should not. Nothing of it reaches the server.
//
// Shown once: the next worker's page to open reads it as it draws, then forgets it once it is on the screen, whoever it
// names, and shows it only if it is that worker's (worker-page.tsx). So a note whose page never came, as when the
// person left by another way, never shows later on. Read and forgotten in two steps, as React's rule is that a draw
// changes nothing outside it: React may draw a page more than once before it is on the screen (twice on each draw, in
// development), and a read that also forgot could leave a later draw with nothing.

/** Which of the worker's cards shows the line: Taarifa zake, or Cheo. */
export type NewsCard = "details" | "roles";

/** The line, the worker whose page shows it, and on which card. */
export type PageNews = { worker: string; card: NewsCard; sentence: string };

/** The note waiting for the next worker's page; null when none waits. */
let waiting: PageNews | null = null;

/** A form's page, as it moves to the worker's page: the line to show there. A second note replaces the first. */
export function leaveNews(news: PageNews): void {
  waiting = news;
}

/** The worker's page, as it draws: the note left for it, if any, still kept. */
export function peekNews(): PageNews | null {
  return waiting;
}

/** The worker's page, once it is on the screen: the note is spent. */
export function forgetNews(): void {
  waiting = null;
}
