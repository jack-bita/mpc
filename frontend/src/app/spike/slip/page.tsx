// page.tsx — a throwaway slip at /spike/slip/, to test printing on the shop's printer (SPIKE-2).
//
// The card's question: can Chrome print a readable slip on the shop's printer in one click?
// The spike's second pull request removes this page. What it proves goes into
// docs/spikes/02-printing.md, for the real receipts (SALE-9) and slips (R2, 03 §7.5).
//
// "use client": every page in this app is a client component (ADR-0016), and this one needs the
// browser anyway: it measures the slip and listens for printing.
"use client";

import { useEffect, useRef } from "react";

import { pageSizeFor } from "./page-size";

// The text lives in the message files, not here (ADR-0032). UI-1 swaps this direct import
// for next-intl's useTranslations().
import sw from "../../../../messages/sw.json";

// A made-up sale: no real customers, products or prices ever enter the repo (rule 10). In the
// real app these come from the sale itself, so they are data, not screen text for the message
// files. The amounts are ready-made text, not numbers: money is never added up with plain
// JavaScript numbers (rule 3), and this page has nothing to add up.
const SALE = {
  number: "D2-0457",
  date: "26/10/2026",
  time: "14:35",
  lines: [
    {
      item: "Dawa ya minyoo 1L",
      quantity: "2",
      unitPrice: "12,000",
      price: "24,000",
    },
    {
      item: "Chakula cha kuku 5kg",
      quantity: "1",
      unitPrice: "12,500",
      price: "12,500",
    },
    { item: "Sindano 10ml", quantity: "3", unitPrice: "1,500", price: "4,500" },
  ],
  total: "TSh 41,000",
};

// Every cell: space between the rows; a name on two lines keeps its numbers on its first line.
const CELL = "py-[1mm] align-top";
// Number cells: never wrap, and keep the columns apart, so the item's name takes the space left.
const NUMBER_CELL = `${CELL} pl-[3mm] text-right whitespace-nowrap`;

export default function SlipPage() {
  // The slip on screen, measured just before printing.
  const slipRef = useRef<HTMLDivElement>(null);

  // Once, when the page opens in the browser: get ready to size the paper whenever printing starts.
  useEffect(() => {
    const slip = slipRef.current;
    if (!slip) return;

    // The paper size goes into a <style> of this page's own. It is removed when the page
    // closes, so other pages print as before.
    const pageStyle = document.createElement("style");
    document.head.append(pageStyle);

    // Test-day switches in the address, so one deploy is enough in the shop (a deploy takes
    // 5–15 minutes). Example: /spike/slip/?pad=6&size=driver
    const switches = new URLSearchParams(window.location.search);

    // ?pad=6: the side padding in mm, to find the printer's working margins. Without it, the
    // 4 mm of px-[4mm] stay; a value that isn't a number is ignored by the browser.
    const pad = switches.get("pad");
    if (pad !== null) slip.style.paddingInline = `${Number(pad)}mm`;

    // ?size=driver: no paper size of ours, so the size chosen in the print window (from the
    // driver) decides — the card's other option, to compare on test day.
    const driverDecides = switches.get("size") === "driver";

    // Measure first, then cut: the paper is exactly as long as the slip (04 v1.11).
    // An arrow function in a const, not a `function` declaration: a declaration is hoisted
    // (lifted to the top of the effect), so TypeScript can't tell it runs only after the
    // `if (!slip) return` check above; a const is created right here, after it.
    const sizeThePaper = () => {
      if (driverDecides) {
        pageStyle.textContent = "@page { margin: 0; }";
        return;
      }
      const size = pageSizeFor(slip.getBoundingClientRect().height);
      pageStyle.textContent = `@page { size: ${size}; margin: 0; }`;
    };

    // "beforeprint" comes before every way of printing: the button, Ctrl+P and kiosk printing.
    // The write above changes the page directly, not React state, so it is in place before
    // Chrome lays out the paper; a React redraw would come too late.
    window.addEventListener("beforeprint", sizeThePaper);
    return () => {
      window.removeEventListener("beforeprint", sizeThePaper);
      pageStyle.remove();
    };
  }, []);

  return (
    // p-4 on screen only: on paper the slip must start at the very top-left corner, or this
    // space would push its right edge off the 80 mm roll.
    <main className="p-4 print:p-0">
      {/* The slip, 80 mm wide on screen too, so its height on screen is its height on paper.
          Black, not the theme's grey: a receipt printer has only black dots, and grey comes
          out speckled or faint. px-[4mm]: the printer can't print the roll's very edges. */}
      <div
        ref={slipRef}
        className="w-[80mm] bg-white px-[4mm] py-[2mm] text-black"
      >
        <h1 className="text-center text-2xl font-bold">{sw.app.title}</h1>
        {/* One string (a template literal), so each line is one piece of text, as on the home page. */}
        <p>{`${sw.slip.saleNumber}: ${SALE.number}`}</p>
        <p>{`${sw.slip.date}: ${SALE.date}`}</p>
        <p>{`${sw.slip.time}: ${SALE.time}`}</p>
        {/* Idadi × @ (the price for each one) = Bei (the line's amount), as on printed receipts. */}
        <table className="my-2 w-full">
          <thead>
            {/* Lines in black, not the theme's light grey, which prints faint (as the text). */}
            <tr className="border-b border-black">
              <th className={`${CELL} text-left`}>{sw.slip.item}</th>
              <th className={NUMBER_CELL}>{sw.slip.quantity}</th>
              <th className={NUMBER_CELL}>{sw.slip.unitPrice}</th>
              <th className={NUMBER_CELL}>{sw.slip.price}</th>
            </tr>
          </thead>
          <tbody>
            {/* A dashed line between items, so the eye follows each one across; none under the
                last, where the total's solid line comes. */}
            {SALE.lines.map((line) => (
              <tr
                key={line.item}
                className="border-b border-dashed border-black last:border-b-0"
              >
                <td className={CELL}>{line.item}</td>
                <td className={NUMBER_CELL}>{line.quantity}</td>
                <td className={NUMBER_CELL}>{line.unitPrice}</td>
                <td className={NUMBER_CELL}>{line.price}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {/* <strong>: the total is what the customer pays, so it stands out (the card's Build line).
            The solid line above it closes the list of items. */}
        <p className="border-t border-black pt-[1mm] text-xl">
          <strong>{`${sw.slip.total}: ${SALE.total}`}</strong>
        </p>
        <p className="mt-2 text-center">{sw.slip.thanks}</p>
      </div>
      {/* Screen only: on paper the button would only waste paper. print:hidden is
          Tailwind's short way to write @media print { display: none }. */}
      <button
        type="button"
        onClick={() => window.print()}
        className="mt-4 min-h-12 cursor-pointer rounded-md bg-primary px-5 font-semibold text-primary-foreground print:hidden"
      >
        {sw.slip.print}
      </button>
    </main>
  );
}
