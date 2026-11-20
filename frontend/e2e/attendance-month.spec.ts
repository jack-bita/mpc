// attendance-month.spec.ts — the month's attendance on the demo, end to end (DATA-8, ATT-5): Meneja opens Mahudhurio
// ya mwezi on his phone and sees the demo's weeks, a line per worker paid by the day, and Asha's day to decide at the
// top. The card's last Done when: through the real server, the demo seed's three weeks of taps (sent by its laptop
// through the push), worked out by the book of days (ATT-10), and the month's route (ATT-5).
//
// The seed gives Asha one day to decide, her latest working day before today, an Ingia with no Toka (DemoPerson in
// backend/apps/demo/services.py). The page opens on this month, whose counts reach yesterday. On a month's first day,
// or a Monday the 2nd after a Sunday the 1st, no working day of it is over yet, and that day falls in the month before:
// the page says so, and the test goes back one month, as a person would. So it never reads the clock of the machine it
// runs on, nor its zone: the page's words decide.
//
// The tests share one database (the-shop.ts). Others clock Asha in today, which no month counts until it is over, and
// none moves a day of the seed's weeks: the seed's people stay as made on the demo (demo.people_fixed).
import sw from "../messages/sw.json";

import {
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const MONTH = sw.attendanceMonth;

/** A sentence of the word book as a pattern, each {name} standing for any words, the rest taken as it is. */
function shaped(sentence: string): RegExp {
  const plain = sentence.replace(/[.*+?^$()|[\]\\]/g, "\\$&");
  return new RegExp(`^${plain.replace(/\{\w+\}/g, ".+")}$`);
}

test("Meneja sees the demo's month, a line per worker and Asha's day to decide", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();

  await test.step("Meneja logs in on the phone and opens Mahudhurio ya mwezi", async () => {
    await phone.goto("/login/");
    await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
    // exact: the eye beside the box is labelled "Onyesha nenosiri", which holds the word too (the-shop.ts).
    await phone
      .getByLabel(sw.login.password.password, { exact: true })
      .fill(MANAGER_PASSWORD);
    await phone
      .getByRole("button", { name: sw.login.password.send, exact: true })
      .click();
    await phone.getByRole("link", { name: MONTH.title, exact: true }).click();
    await expect(
      phone.getByRole("heading", { name: MONTH.title, level: 1 }),
    ).toBeVisible();
  });

  await test.step("on a month's first days, back to the month before", async () => {
    const countedTo = phone.getByText(shaped(MONTH.countedTo));
    const nothingOver = phone.getByText(MONTH.nothingOverYet, { exact: true });
    // One of the two, once the server has answered.
    await expect(countedTo.or(nothingOver)).toBeVisible();
    if (await nothingOver.isVisible()) {
      await phone
        .getByRole("button", { name: MONTH.before, exact: true })
        .click();
      await expect(nothingOver).toBeHidden();
    }
  });

  await test.step("Asha's day to decide is at the top: an Ingia with no Toka", async () => {
    const toDecide = phone.getByRole("list", {
      name: words(MONTH.toDecide, { count: "1" }),
    });
    await expect(toDecide.getByRole("listitem")).toHaveCount(1);
    await expect(toDecide.getByRole("listitem")).toHaveText(
      shaped(
        words(MONTH.dayToDecide, { name: "Asha", why: MONTH.reason.no_out }),
      ),
    );
  });

  await test.step("a line per worker paid by the day, Asha's with her one day to decide", async () => {
    const workers = phone.getByRole("table", { name: MONTH.workersCaption });
    for (const name of ["Asha", "Baraka", "Meneja"]) {
      await expect(
        workers.getByRole("rowheader", { name, exact: true }),
      ).toBeVisible();
    }
    // The line's last count is the days to decide (✓ Ch ½ H !, month-screen.tsx).
    const asha = workers.getByRole("row").filter({
      has: phone.getByRole("rowheader", { name: "Asha", exact: true }),
    });
    await expect(asha.getByRole("cell").last()).toHaveText("1");
  });
});
