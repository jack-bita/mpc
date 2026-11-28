// whole-month.spec.ts — a whole month approved on the demo, end to end (DATA-2): Meneja opens Mishahara on his phone, goes
// back to last month, which the demo always holds whole and over, as the seed starts on its 1st, and approves it for
// everyone, Idhinisha with the month's name; the page then says who approved it and offers no approval. Then Chapisha
// orodha opens the month's sheet (WAGE-5): each of the seed's three with Hajalipwa, as nobody is paid yet, and Jumla ya
// wote, the total the page read before the approval. Through the real server: the seed's days from the 1st of last month
// (backend/apps/demo/services.py), the book, the sum, the approval (approve_month) and the sheet's page.
//
// On a month's first working days the newest days to decide, counted back from yesterday, fall in last month, and the
// sheet names them, Amua siku hii kwanza, in place of a working Idhinisha: the test opens each, decides it a full day with
// the demo's ready reason, as a visitor would, and comes back. Other tests may have decided some already; on any other
// day none waits.
//
// It runs last of the tests that touch last month, by its name, as the tests run one at a time, file by file in their
// names' order (playwright.config.ts): an approved month takes no change, so a test after it that decided, typed or
// crossed out anything of it would fail. Only workers.spec.ts runs after it, which reads no month. An approval is never
// taken back: the demo's next reset makes the month open again.
import type { Page } from "@playwright/test";

import sw from "../messages/sw.json";

import {
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const APPROVAL = sw.pay.approval;
const MONTH = sw.attendanceMonth;
const PAY = sw.pay;
const WORKER = sw.attendanceWorker;

/** A regular expression that matches `text` as it is, its dots and brackets too. */
function exactly(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** A sentence of the book with each {name} matching `pattern`: "Idhinisha {month}" → /^Idhinisha \S+ \d{4}$/. */
function shaped(sentence: string, pattern: string): RegExp {
  const parts = sentence.split(/\{\w+\}/).map(exactly);
  return new RegExp(`^${parts.join(pattern)}$`);
}

/** Both forms of a plural sentence of the book, "{count, plural, one {…} other {…}}", as the screen shows one of them. */
function eitherForm(sentence: string): RegExp {
  const forms = [...sentence.matchAll(/(?:one|other) \{([^}]*)\}/g)].map(
    (form) => exactly(form[1] ?? ""),
  );
  return new RegExp(`^(${forms.join("|")})$`);
}

// "Oktoba 2026": a month's name, whatever month the test runs in.
const A_MONTH = "\\S+ \\d{4}";
// The month's button and its sheet's title, "Idhinisha Oktoba 2026": never Idhinisha malipo ya Neema, a leaver's.
const APPROVE_MONTH = shaped(APPROVAL.monthButton, A_MONTH);
// "Amua siku hii kwanza:" or "Amua siku hizi kwanza:", the days the month waits for.
const WAITING = eitherForm(APPROVAL.waiting);
// "Amua siku ya Asha", the sheet a day is decided in (ATT-6), whoever's day.
const DECIDE = shaped(WORKER.sheetTitle, "\\S+");
// An amount as the page writes it, "TSh 986,500": Intl puts a hard space after TSh, which \s matches.
const AN_AMOUNT = /TSh\s[\d,]+/;

/** The amount in a line of the page, its spaces made plain, so the screen's and the paper's compare. */
function amountIn(text: string): string {
  return (AN_AMOUNT.exec(text)?.[0] ?? "").replace(/\s/g, " ");
}

/** The back arrow, to the page before. */
async function back(phone: Page) {
  await phone.getByRole("button", { name: sw.pageHeader.back }).click();
}

test("Meneja approves last month for everyone on the demo, and prints its sheet", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  const approveButton = phone.getByRole("button", { name: APPROVE_MONTH });
  const approveSheet = phone.getByRole("dialog", { name: APPROVE_MONTH });
  const totalOfAll = phone.locator("p").filter({ hasText: PAY.totalOfAll });

  await test.step("Meneja logs in on the phone and opens Mishahara on last month", async () => {
    await phone.goto("/login/");
    await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
    // exact: the eye beside the box is labelled "Onyesha nenosiri", which holds the word too (the-shop.ts).
    await phone
      .getByLabel(sw.login.password.password, { exact: true })
      .fill(MANAGER_PASSWORD);
    await phone
      .getByRole("button", { name: sw.login.password.send, exact: true })
      .click();
    await phone.getByRole("link", { name: PAY.title, exact: true }).click();
    await expect(
      phone.getByRole("heading", { name: PAY.title, level: 1, exact: true }),
    ).toBeVisible();
    await phone
      .getByRole("button", { name: MONTH.before, exact: true })
      .click();
    // Over and open: its Idhinisha is at the foot, for Meneja, who holds the approval's keys (WAGE-3).
    await expect(approveButton).toBeVisible();
  });

  const read =
    await test.step("on a month's first days, each of its newest days to decide is decided first", async () => {
      // At most the seed's three, then the sheet with nothing to wait for. Each round reads the total before the sheet
      // opens, as the sheet approves what the page showed then.
      for (let round = 0; round < 4; round += 1) {
        const total = amountIn(await totalOfAll.innerText());
        await approveButton.click();
        await expect(approveSheet).toBeVisible();
        const waiting = approveSheet.getByRole("list", { name: WAITING });
        if ((await waiting.count()) === 0) return total;
        // Its first day opens under its worker's calendar, where it is decided, as a person mends it.
        await waiting.getByRole("link").first().click();
        await phone
          .getByRole("button", { name: WORKER.decide, exact: true })
          .click();
        const decide = phone.getByRole("dialog", { name: DECIDE });
        await decide
          .getByText(WORKER.decision.on_time, { exact: true })
          .click();
        // On the demo, the reason is one of the ready ones to tap (ATT-6), never typed.
        await decide
          .getByText(WORKER.readyReason.forgot_toka, { exact: true })
          .click();
        await decide
          .getByRole("button", { name: WORKER.save, exact: true })
          .click();
        await expect(decide).toBeHidden();
        // Back to Mishahara, on the same month, which the address keeps; and read again. Coming back, the page first
        // shows its saved answer, from before the decision, while it asks the server afresh: read then, the day would
        // still wait, and the total be the old one, which the sheet would hold as moved (DATA-2's review).
        await back(phone);
        await phone.reload();
        await expect(approveButton).toBeVisible();
      }
      throw new Error(
        "The month still waits for a day after the seed's three.",
      );
    });

  await test.step("Idhinisha approves the month as read, and the page says who approved it", async () => {
    expect(read).not.toBe("");
    await approveSheet
      .getByRole("button", { name: APPROVAL.action, exact: true })
      .click();
    await expect(approveSheet).toBeHidden();
    const approvedBy = shaped(
      words(APPROVAL.approvedBy, { by: "Meneja" }),
      ".+",
    );
    await expect(phone.getByText(approvedBy)).toBeVisible();
    await expect(approveButton).toHaveCount(0);
    // Read again from the server, its payslips say the same.
    await phone.reload();
    await expect(phone.getByText(approvedBy)).toBeVisible();
    expect(amountIn(await totalOfAll.innerText())).toBe(read);
  });

  await test.step("Chapisha orodha opens the month's sheet: the three, Hajalipwa, and the total read", async () => {
    await phone
      .getByRole("link", { name: PAY.papers.printSheet, exact: true })
      .click();
    const paper = phone.locator("section");
    await expect(paper.getByRole("heading", { level: 2 })).toHaveText(
      shaped(PAY.sheet.heading, A_MONTH),
    );
    const rows = paper
      .getByRole("table", { name: PAY.workersLabel })
      .getByRole("row");
    // The seed's three, each not paid yet: nobody may pay Meneja on the demo, as nobody marks their own pay paid.
    for (const name of ["Asha", "Baraka", "Meneja"]) {
      await expect(
        rows.filter({ has: phone.getByText(name, { exact: true }) }),
      ).toContainText(sw.pay.payment.notPaid);
    }
    const total = paper.getByText(shaped(PAY.sheet.total, ".+"));
    await expect(total).toBeVisible();
    expect(amountIn(await total.innerText())).toBe(read);
  });
});
