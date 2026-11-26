# 01 — Product Spec

**Product:** shop system for agro-vet and farm-supply shops (name to be decided)
**First shop:** MPC — Mabatini Pumba Center, Usa River, Arusha, Tanzania
**Version:** 1.13 · 26 Nov 2026 · Portion 1 of the planning pack
**Status:** living document. Everything here is decided unless marked *(default)*, which means our best guess and is safe to change while building. Open questions are collected in §14. Key decisions are recorded as ADRs in `docs/adr/`.

**Changes in v1.1** (18 Oct 2026): applies the build plan's Appendix A (`04-build-plan.md`). Attendance (R1b) is built and switched on first, then the Drugs side (R1), then the Foods side (R2); every part lives in the one website and is switched on in settings (§7.8, §10, §11, §14 — 04 BP7, ADR-0033). §6 now states the side decision (02 D1, ADR-0001).

**Changes in v1.2** (15 Nov 2026, from Jack): the shop's cook makes the workers' meals, and each worker pays for their own out of their pay. The day's meal money is typed each day and split among the workers who came that day, so a worker who leaves mid-month is paid at once, with nothing to count by hand (§6, §7.8, §8.1; 02 v1.29, 04 v1.78). Marked **(v1.2)**.

**Changes in v1.3** (16 Nov 2026, from the owner, through Jack, OWN-7): the attendance rules in §8.1 are the owner's: two fines, the half days' windows, and *dharura*, a day a manager decides. The fines' amounts are the owner's to type on the real server, so this public spec names none, and the payslip example takes a made-up fine of 500 (02 v1.32, 04 v1.86). Marked **(v1.3)**.

**Changes in v1.4** (16 Nov 2026, from Jack, ATT-8): besides Sundays and public holidays, the owner may close the shop for days of his own, such as a family funeral: each closure runs from a first day to a last, which he may move, and nobody is paid on its days (§8.1; 02 v1.33, 04 v1.89). Marked **(v1.4)**.

**Changes in v1.5** (19 Nov 2026, from Jack, ATT-3): §7.8, a clock-in's photo is decided, no longer a default, and a camera missing or broken never stops a tap. Marked **(v1.5)**.

**Changes in v1.6** (19 Nov 2026, from the owner, through Jack, ATT-4): §8.1, a late arrival who leaves for the morning's half day is paid the half day less the fine of their arrival; the examples gain that row, and pay takes off each day's fine; and Toka ends the day, as nobody taps out for lunch (from Jack, at ATT-4's review) (02 v1.42, 04 v1.128, v1.130). Marked **(v1.6)**.

**Changes in v1.7** (19 Nov 2026, from Jack, ATT-10): §8.1, a worker who clocked in on a closed day all the same has a day that needs review, for the owner or a manager to decide (02 v1.43, 04 v1.138). Marked **(v1.7)**.

**Changes in v1.8** (19 Nov 2026, from Jack, ATT-11): §8.1, a day with a tap in doubt needs review: a tap by a worker who was suspended or had left, a tap whose time a later one disagrees with, and a tap before the worker's first day or after their last (02 v1.46, 04 v1.142). Marked **(v1.8)**.

**Changes in v1.9** (19 Nov 2026, ATT-11's review): §8.1, a tap the server timed itself, sent at once, is never in doubt for a later tap that disagrees with it, as no laptop's clock can make the server's time wrong (02 v1.47, 04 v1.144). Marked **(v1.9)**.

**Changes in v1.10** (25 Nov 2026, from Jack, WAGE-2): §8.1, a fine never takes a day's pay below 0; half a day's pay is rounded once, by itself; and one who leaves is paid for the day they leave as soon as they clock out, with that day's meals (02 v1.66, 04 v1.197). Marked **(v1.10)**.

**Changes in v1.13** (26 Nov 2026, from Jack, WAGE-9): §7.8 and §8.1, an approved month's pay is handed out: the whole of it at once; in cash, the worker signs on the screen first; by M-Pesa or a bank, the transaction number is typed. Nobody marks their own pay paid, and one marked by mistake is crossed out, with a reason, and stays (02 v1.72, 04 v1.209). Marked **(v1.13)**.

**Changes in v1.12** (25 Nov 2026, from Jack, WAGE-3): §7.8 and §8.1, a month's pay is approved once, and then never changes: a payslip per worker, kept; a day that waits refuses it; one who leaves is approved alone, the same evening; a worker who owes is paid 0, and the debt comes off the next month. And each worker signs for their pay, as on paper at MPC today, on the screen with a finger (02 v1.70, 04 v1.205). Marked **(v1.12)**.

**Changes in v1.11** (25 Nov 2026, from Jack, WAGE-8): money given to a worker before payday, an advance, is typed on the day it is given by whoever may give one, never their own, and comes off that month's pay (§7.8, §8.1; 02 v1.68, 04 v1.201). Marked **(v1.11)**.

---

## 1. Summary

A Swahili-first, offline-first web system that runs on a shop's own laptops and phones. It replaces paper books (and SmartMauzo on the Drugs side) for selling, cash-up, credit, stock, services, and staff attendance and pay.

It is built as a **multi-shop product from day one**. MPC is shop #1 and the first real user. It is also Jack's main portfolio project: public code, a live demo shop with fake data, and a case study with real before/after numbers.

## 2. Goals and non-goals

**Goals**
1. Money matches: every drawer reconciles daily, with names on every difference.
2. Attendance and month-end pay are calculated automatically.
3. Product and stock records are reliable, including batches and expiry for drugs.
4. Replace SmartMauzo on the Drugs side, without subscription lock-in.
5. A new worker can use it after 30–60 minutes of training.
6. Keeps working through internet and power cuts.

**Non-goals (for now)**
- Issuing TRA fiscal receipts. MPC records the EFD receipt number; connecting to a VFD is *Later*.
- Full accounting (general ledger, tax returns).
- Delivery tracking. Customers pay delivery people directly.
- A generic POS for every kind of business *(default: focus on agro-vet and farm-supply shops)*.
- Sign-up and billing for other shops, until MPC runs well.

## 3. MPC today (as-is)

**Structure.** Two sides under one roof, each with its own workers and cash drawer:
- **Drugs side** — *Pembejeo za kilimo na mifugo* (farm and livestock inputs, vet drugs). One person (Jack) writes, takes payment and hands over. Uses SmartMauzo: paid every 6 months, only Jack has mastered it, hard to find things, needs English, data visible only while logged in.
- **Foods side** — animal foods and supplements. The busiest side: 50–100+ customers on busy days, big orders. Flow: order writer → cashier → workers who hand over the goods. The cashier sometimes writes; the owner sometimes writes.

The sides cooperate. A customer can take goods from both sides and pay once at either; staff walk over to tell the other side. Some products sell on both sides, at the same price. One TRA EFD machine sits on the Drugs side and serves both; receipts are given on request and for big orders.

**Records.** Paper: delivery notes, proforma and invoice books, exercise books. On the Foods side a cash or Lipa Namba sale leaves no record ("pay, take, go").

**Money.** Cash and Lipa Namba are most common; big amounts come by Lipa Namba or bank. One Lipa Namba serves both sides (to be split later). Payments are confirmed by checking the SMS on the shop phone. If a customer overpays by Lipa Namba, change is given in cash. Expenses are paid from the drawers daily. At closing (18:40, later if a delivery or customers are still in) the money and books are left at the office. The owner, Jack or his siblings count; the owner has the final say.

**Credit (madeni).** Written in a book with date, name, phone and items. Arguments about amounts happen. Repaid in parts or in full; reminders by phone or in person. Usually separate per side, sometimes combined. Estimated open total: TZS 5–10 million.

**Prices.** Bargaining is normal. Anyone except loaders may bargain (loaders don't know buying prices). Jumla and rejareja prices both exist; jumla depends on order size and the customer. Selling prices change very often, by people the owner assigns. Returns: money back, exchange, or a negotiated deal. Wrong orders are rewritten.

**Products and stock.** Many products, constantly added and finished. Sold by bag and by kg (one product can be sold both ways). Loose kg is always weighed; spillage is normal and swept up. Some products have barcodes (unused). For drugs, shelf number, expiry date and location are checked. Stock sits on shelves and in stores, and rarely moves between sides. Low stock is noticed by eye. Full counts are rare.

**Suppliers.** Many: regular suppliers plus one-off sellers offering lower prices. Suppliers give credit, recorded on paper. Deliveries are checked against the supplier's paper.

**Services.** MPC owns mixing and grinding machines. Every machine service is charged per kg, and more services will come. Customers bring their own ingredients, buy them at MPC, or both. *Exchange:* a customer brings whole maize, takes ground maize, and pays the grinding charge. Formulas come from the customer or from MPC, which has some standard formulas. Customers wait or come back later; jobs are paid at any time. MPC also grinds and mixes its own stock.

**Partners.** Trusted people who deliver and provide services. They collect money from customers and bring it to MPC, and may take goods and pay later. Customers sometimes send someone to collect, with or without money.

**Customers.** All types, mostly farmers and livestock keepers; few institutions and other shops. About 50 regulars. Phone calls are the main channel besides walking in; WhatsApp and messengers are also normal. 8–9 in 10 have smartphones. They ask about prices, stock, advice and their debt.

**Staff.** Workers write their names in a notebook for attendance; month-end pay and late deductions are counted by hand. Staff change often. When the owner is away, Jack or his siblings are in charge; otherwise the cashier or order writer. Some workers have no smartphone.

**Devices and power.** Phones and laptops. One small printer, wired to a laptop, prints order slips for workers. Internet by mobile data and Wi-Fi (preferred). Power cuts happen; there is no backup power.

## 4. Problems to solve

Ranked by Jack:
1. **Poor record keeping** → the money on paper doesn't match the cash.
2. **Attendance isn't recorded reliably** → slow, error-prone month-end pay.
3. **Poor product records.**

All the usual failures also happen: wrong change, forgotten debts, stock-outs, expired drugs, wrong prices.

## 5. Design principles

1. **Swahili first**, with an English switch *(default)*.
2. **A sale takes seconds.** A few taps, no typing for common items. Today a cash sale needs no writing at all, so MPC must not feel slower.
3. **Works without Jack.** A new worker can sell after a few minutes; full training takes 30–60 minutes at most.
4. **Search is the strongest part of the sale screen.** It finds products by name, brand, animal and use ("dawa ya kupe").
5. **The shop owns its data.** Export to Excel anytime; automatic backups.
6. **Every action has a name.** Each person has their own login (a quick PIN on shared devices).
7. **Workers can see their own records:** attendance, payslips, cash-ups. MPC protects honest workers.
8. **Runs on shop devices.** No worker needs their own smartphone.
9. **The counter works offline** and syncs when the internet returns.
10. **Rules are settings, not code.** Rates, fines, times, tolerances and services are settings; a change applies from a date forward.
11. **Never guess numbers.** If something is unknown, MPC shows "unknown".
12. **Nothing is deleted.** Sales are cancelled, workers suspended, products archived, always with a reason and a name.

**Core idea: expected vs actual.** Drawers, open bags, deliveries, stock counts and production runs all work the same way. MPC calculates what *should* be there, people record what *is* there, and a difference within the allowed tolerance is normal. Bigger differences are flagged, with names.

## 6. Users, roles and permissions

**Shops and sides.** Every record belongs to a shop (tenant). A shop has one or more sides (MPC: Drugs and Foods). A side is a section of one shop: sides share products, prices and customers, and each keeps its own stock, drawer, staff roles and debts (02 D1, ADR-0001).

**Roles** are bundles of permissions, given to a person *per side*. One person can hold several roles, and extra permissions can be given to individuals.

| Role | Who at MPC | Main abilities |
|---|---|---|
| Owner | Jack's father | Everything on all sides; final approval of cash-ups; sets rules and rates |
| Manager | Jack, his siblings | Runs the shop when the owner is away; approvals the owner grants |
| Seller | Drugs side (Jack) | One-screen sale: write, take payment, hand over |
| Order writer | Foods side | Writes orders; bargains down to the floor price |
| Cashier | Foods side | Takes payments; may also write orders |
| Worker (loader) | Foods side | Clocks in and out; hands over goods against paid slips; cannot bargain |
| Customer | Release 3 | Browses, orders, sees own debt |
| Partner | A contact, not a login *(default)* | Has a balance like a credit customer |

**Example permissions:** bargain down to the floor price · approve below the floor · change prices · give credit · approve credit · cancel a sale · refund · record an expense or advance · record the day's meal money **(v1.2)** · close a drawer · approve the day · manage workers · see buying prices and profit *(default: owner and managers only)*.

**Worker lifecycle:** active → suspended. Suspension stops the login instantly; history and pay records stay. Workers are never deleted.

## 7. Features by area

Release tags: **R1** Drugs side live · **R1b** attendance and pay · **R2** Foods side live · **R3** customer side · **Later**. Build order: R1b first, then R1, R2 and R3 (§10).

### 7.1 Access and staff
- PIN login on shared shop devices, with quick switching between people — R1
- Roles per side, per-person permissions, suspending workers — R1
- Practice mode with fake data for training new workers — R2 *(default)*

### 7.2 Products and prices
- One product list per shop; stock kept per side — R1
- A base unit (kg, litre, piece) plus selling units (e.g. "Bag 50 kg", "1 kg"), each with its own price — R1
- Retail and jumla price per selling unit, plus a floor price — R1
- Prices changed only by permitted people, with full history; a sale keeps the price at the time of sale — R1
- Tags (animal, use, brand), a shelf/store label, and a barcode field (scanning is Later) — R1
- Archiving finished products — R1
- Adding a new product takes under a minute — R1
- Suggest a new selling price when a delivery's buying price rises — R2
- Services as products without stock, priced per kg — R2

### 7.3 Stock
- Stock is a ledger of movements; current stock = the sum of movements — R1
- Receiving deliveries: supplier, quantities, buying price, batch and expiry for drugs, a photo of the supplier's paper, differences noted — R1
- Quick "received, pending" for late deliveries, with details completed the next morning — R1
- A loss button (spilled, damaged, expired) with a reason and a name — R1
- Reorder levels, an automatic shopping list, and a "running low" button — R1
- Expiry alerts; suggest the batch that expires first — R1
- Count 5 products a day; one full count for the opening stock — R1
- Open-bag check: kg sold vs bag size, within a tolerance setting — R2
- Transfers between sides — R2
- Production (grinding or mixing own stock): kg in, kg out, loss measured — R2

### 7.4 Selling
- One-screen sale (Drugs): search, add, bargain to the floor, pay, hand over — R1
- Jumla prices when the customer is marked jumla, or when permitted staff switch a big sale — R1
- Cancel with a reason; returns as refund, exchange or a deal — R1
- Receipt options: none, printed (laptop printer), or shared on WhatsApp — R1
- A field for the EFD receipt number — R1
- Writer → cashier → loader flow (Foods) — R2
- The workers' slip prints only after payment: no slip, no goods — R2
- Phone orders: the caller's number pulls up the customer (debt, last order, formulas) — R2
- One customer, one payment, goods from both sides; MPC tells the other side and keeps each side's money correct — R2
- "Collected by" (name and phone) when someone else collects — R2

### 7.5 Payments and cash-up
- Cash, Lipa Namba and bank; split payments; change recorded — R1
- A transaction code is required for Lipa Namba and bank; a code already used is rejected — R1
- Payment accounts (Lipa Namba numbers, bank accounts) are settings, assigned to sides — R1
- A drawer session per side: opening cash; expenses, worker advances and withdrawals recorded; blind count; confirmation by owner or manager; owner approval — R1
- Automatic payment confirmation from the mobile-money provider or bank — Later

### 7.6 Credit, partners and suppliers
- Customers, partners and suppliers share one balance system (receivables and payables) — R1 for customers, R2 for partners and suppliers
- Each debt records the date, customer, phone, items, amount and who gave it — R1
- Debts kept per side, with a combined view — R1
- Repayments in parts or in full — R1
- Debt aging: who owes what, and since when — R1
- Importing open debts at launch — R1
- SMS or WhatsApp confirmation to the customer for each new debt and payment — Later *(cost decision)*
- Automatic debt reminders — R3 / Later

### 7.7 Services and jobs — R2
- A service catalog (mixing, grinding, more later), priced per kg
- A job list: waiting → in progress → ready → collected
- A job records customer-brought goods separately from MPC stock, plus the machine charge
- Exchange: customer's whole maize into stock, ground maize out, grinding charge paid
- A formula library: MPC's standard formulas and each customer's own; turn a formula into an order for any amount; "same as last time"
- Jobs can be paid at any time, with the same payment and credit rules as sales

### 7.8 Attendance and pay — R1b (built first, §10)
- Clock in and out on a shop device with a PIN, plus a photo from its camera; with no camera, or one that fails, the tap still counts, marked with no photo (Jack, ATT-3) **(v1.5)**
- The rules in §8.1; absence types: office duty, with permission, no-show
- Monthly pay calculated per worker, with advances and meals deducted **(v1.2)**
- The day's meal money, typed each day, by whoever the owner gives the key to **(v1.2)**
- Money given before payday (an advance), typed on the day it is given, by the owner or a manager, never their own **(v1.11)**
- A month's pay approved once it is over, with one tap, by the owner or whoever he gives the key to: a payslip per worker is kept, and nothing of that month can change any more **(v1.12)**
- Each worker signs for their pay on the screen, with a finger, as they sign on paper today, so a payment marked by one person alone proves nothing; paid by M-Pesa or a bank, its transaction number is typed instead **(v1.13)**; the month's sheet is printed with each name, amount and signature, for NSSF and the owner's file **(v1.12)**
- Each worker can see their own payslip
- Rates, the fine and the cut-off times are settings with start dates
- Offline clock-in is protected against changes to the device clock

### 7.9 Reports
- Daily report per side: sales by method, credit given, debts collected, expenses, expected vs counted cash, low stock, items expiring soon — R1
- "Send to boss": WhatsApp opens with the summary already typed — R1
- Weekly best and slowest sellers; monthly profit (unknown buying prices shown as unknown); debt aging; attendance and pay — R2
- Automatic WhatsApp or SMS summaries — Later

### 7.10 Customer side — R3
In this order: a price list with in-stock status (browse by animal and problem) → order now, collect later → my debt and payments → a message when my job is ready → debt reminders → online payment (Later). Pilot with 5–10 regular customers first.

### 7.11 Multi-shop platform
- Every record belongs to a shop; shops never see each other's data — R1
- Everything shop-specific is a setting: sides, services, rules, payment accounts — R1
- A demo shop with fake data for the portfolio — R1
- Sign-up and billing for other shops — Later

### 7.12 Data
- Import: products and selling units, opening stock, customers and open debts — R1
- Export to Excel; automatic backups — R1

## 8. Business rules

### 8.1 Attendance and pay
- **On time:** arrives by 07:35 → full day.
- **Late** **(v1.3)**: arrives after 07:35 and before 08:00 → full day minus the first fine; from 08:00 and before 08:30 → full day minus the second fine. Both fines are settings the owner types; this spec names no amount.
- **Half day** **(v1.3)**: the morning (arrives on time or late, leaves from 13:00 to 13:30) or the afternoon (arrives from 12:00 to 13:00, leaves at closing, 18:40). Half-day pay = daily rate ÷ 2. A late arrival who leaves for the morning's half day loses the fine of their arrival too **(v1.6)**.
- **Toka ends the day** **(v1.6)**: the day runs from the first clock-in to the first clock-out; nobody clocks out for lunch, and a clock-out tapped by mistake makes the day *dharura*.
- **Dharura** **(v1.3)**: any other arrival or leaving time, and a missing clock-out. The day needs review: a manager or the owner decides it.
- **Sundays and public holidays** **(v1.3)**: the shop is closed and nobody is paid. Sunday work is a deal between the owner and the worker, outside the system.
- **Other closed days** **(v1.4)**: the owner may close the shop for days of his own, such as a family funeral, from a first day to a last. Nobody is paid on them, as on a public holiday. If the shop opens again sooner, or stays closed longer, he moves the last day, with a reason. A worker who clocked in on a closed day all the same, as when the shop closes at 10:00 for a funeral, has a day that needs review: the owner or a manager decides whether it is paid **(v1.7)**.
- **A tap in doubt** **(v1.8)**: a day needs review, for the owner or a manager to decide, when one of its taps is in doubt: made by a worker who was suspended or had left, as an offline laptop doesn't know yet; a tap whose time the next tap on the same laptop disagrees with, as one of the two clocks was wrong and nobody knows which, unless the server timed it itself, as a tap sent at once is **(v1.9)**; or a tap before the worker's first day or after their last, as when a manager moves the first day later.
- **Absent:** office duty → paid; with permission → unpaid; no-show → unpaid.
- **Meals** **(v1.2)**: the cook makes the workers' meals at the shop, and each worker pays for their own. Each day, the day's meal money is typed in and split equally among the workers who came that day, half days included; the cook pays no share. So a worker who came 10 days pays 10 days of meals, not a share of the whole month.
- **Pay** = (full days × daily rate) + (half days × daily rate ÷ 2) − each day's fine **(v1.6)** − meal shares − advances. Paid monthly. The daily rate is set per worker. Sundays are not paid. A fine takes no more than its day pays, so a day never goes below 0 **(v1.10)**. Half a day's pay is rounded once, by itself, to the shop's rounding step **(v1.10)**.
- **Advances** **(v1.11)**: money given to a worker before payday is typed on the day it is given, and comes off the pay of that month, in full. One bigger than the pay so far is kept all the same, as the money was given. Nobody types or crosses out their own.
- **Approving the month** **(v1.12)**: once a month is over, the owner reads *Mishahara* and approves it, once, for everyone. Each worker's payslip is kept as it was read, and no day, clock event, pay rate, meal money or advance of that month can be added, decided or crossed out any more; a mistake found later is put right in the next month's pay. A day that still waits for a decision refuses the approval, and is named. A shop laptop that has sent nothing since the month ended is named too, and stops nothing. Months are approved in order.
- **Paying** **(v1.13)**: once a month is approved, each worker's pay is handed out, the whole of it at once (Jack: A). In cash, the worker draws their signature on the screen first, with a finger, or a mouse on a laptop; by M-Pesa or a bank, its transaction number is typed, and a number used already is refused. *Mishahara* then shows who is paid, and how much is still to hand out. Nobody marks their own pay paid. A payment marked by mistake is crossed out, with a reason, and stays, with its signature; the worker is then paid again. A mistake found after the approval is put right in a later month's pay (WAGE-10).
- **A total below 0** **(v1.12)**: one who took more before payday than they earned is paid 0, and the debt comes off the next month they are paid in. The whole of a month counts them as 0, so it is what the month pays.
- **Leaving mid-month** **(v1.2)**: a worker who leaves is paid up to their last day. The system already holds that pay, worked out day by day, so the owner reads it and pays. The day they leave counts as soon as they clock out, less their share of that day's meals, split among those who have come by then **(v1.10)**. They are approved alone, that evening, and the month's approval holds that payslip **(v1.12)**.

Examples (these become automated tests):

| Case | Result |
|---|---|
| Arrives 07:20, leaves at closing | Full day |
| Arrives 07:50, leaves at closing | Full day − the first fine |
| Arrives 08:10, leaves at closing **(v1.3)** | Full day − the second fine |
| Arrives 09:00, leaves at closing **(v1.3)** | Dharura |
| Arrives 12:30, leaves at closing **(v1.3)** | Half day |
| Arrives 13:30, leaves at closing | Dharura **(v1.3)** |
| Arrives 07:20, leaves at 13:10 **(v1.3)** | Half day |
| Arrives 07:50, leaves at 13:10 **(v1.6)** | Half day − the first fine |
| Arrives 07:20, leaves at 12:00 | Dharura **(v1.3)** |
| Arrives 07:20, leaves at 16:00 **(v1.3)** | Dharura |
| Arrives 07:20, never clocks out **(v1.3)** | Dharura |
| Doesn't come, no office reason | No pay |

Payslip example (daily rate 9,000, a first fine of 500 for the example **(v1.3)**): 20 days on time + 3 late = 23 × 9,000 = 207,000; 2 half days × 4,500 = 9,000; 3 fines = −1,500; advance = −20,000 → **194,500**.

### 8.2 Money
- **Expected cash** = opening cash + cash sales + cash debt repayments − cash change given for Lipa Namba overpayments − expenses − advances − withdrawals.
- **Difference** = counted − expected, recorded with the names of the person who counted and the person who confirmed.
- **Blind count:** the counter enters the amount before seeing the expected figure.
- Credit is not a payment method. The unpaid part of a sale becomes debt in the customer's ledger.
- Money is stored as exact decimals, never floating-point numbers.

### 8.3 Prices
- One price per selling unit for the whole shop (both sides).
- Staff may bargain down to the floor price; going lower needs approval from a permitted person.
- Every discount and price change is recorded with a name.
- Sale lines keep the price at the time of sale.

### 8.4 Stock
- Selling a selling unit removes its size in base units: one "Bag 50 kg" removes 50 kg.
- Losses are recorded with a reason and a name.
- Production and exchange are recorded as stock movements in and out.

## 9. Non-functional requirements

- **Language:** Swahili by default; English switch *(default)*.
- **Offline:** counter flows (clock-in, sales, payments) work offline and sync later. Office flows (reports, prices, pay, settings) need internet. Offline records must survive device restarts and attempts to change the device clock.
- **Speed:** a common sale in seconds; a big Foods order written in under a minute; search results as you type.
- **Devices:** one responsive web app for laptops (keyboard) and phones (touch); shared devices with quick PIN switching; printing through the laptop's normal printing.
- **Learnability:** usable after 30–60 minutes of training.
- **Power:** use devices with batteries; a small UPS for the Wi-Fi router is recommended.
- **Security and privacy:** personal logins, permissions and an audit trail; full separation between shops; customer names, phones and debts treated as private; real shop data never in the public repo.
- **Scale:** thousands of products, many shops, several sides per shop.
- **Compliance:** TRA treats a sale as a valid tax document only after it passes through an EFD or VFD. MPC records the EFD receipt number now and may connect to a VFD later. Drug batches and expiry dates are recorded on receiving, including from one-off sellers.

## 10. Releases

These replace the old Phase 1–4. The release names stay as they are, because the build plan, the issues and the version tags use them. The **build order** is set in `04-build-plan.md` (BP7, ADR-0033): **R1b first, then R1, then R2, then R3.** The foundation every release stands on — access and staff, the offline counter, the multi-shop base and the demo shop — is built before all of them (04 stages 0–3).

- **R1b — Attendance and pay for the whole shop** — built and switched on first: clock-in and out on shop devices, the attendance rules, monthly pay runs and payslips (§7.8).
- **R1 — Drugs side live:** access and staff, products and prices, stock, one-screen sale, payments and cash-up, customer credit, daily report, offline counter, imports and export, multi-shop foundation, demo shop.
- **R2 — Foods side live:** writer → cashier → loader flow, paid slips, phone orders, cross-side payment, services and jobs, formulas, exchange, production, open-bag check, transfers, partners and supplier credit, weekly and monthly reports, practice mode.
- **R3 — Customer side**, in the order in §7.10.
- **Later:** online payments, automatic WhatsApp/SMS, VFD receipts, barcode scanning, proforma and invoice PDFs, sign-up and billing for other shops, stock counts per store room.

## 11. Launch plan

- **One website and one repo for everything** — attendance, the Drugs side and the Foods side — at one address. The parts are built and switched on one after another: **attendance first (R1b), then the Drugs side (R1), then the Foods side (R2)**. Each part is switched on in settings; the shop starts using a part once the owner agrees *(default: as soon as it is ready)* (04 BP7, ADR-0033).
- Before attendance goes live: the worker list with daily rates and the attendance rules (04 §15).
- Before each side goes live: products with selling units, prices and buying prices; a full opening stock count; customers and open debts.
- Paper runs alongside: the attendance notebook for the first month; the paper books for the first two weeks of each side (04 §16).
- Jack trains every worker (30–60 minutes each).
- Customer side: pilot with 5–10 regular customers.

## 12. Success measures *(default)*

- The drawer difference is near zero every day, on each side.
- Month-end pay takes minutes, not hours.
- Every debt has a phone number and an age, and the open total is visible daily.

Baselines to record before launch: customers on a busy Foods day (50–100+), open debts (TZS 5–10M), how long month-end pay takes today, how often stock is fully counted.

## 13. Portfolio

- Public repo from day one; real shop data is never committed.
- Live demo = a demo shop with fake data, running on the same multi-shop system.
- Case study with real before/after numbers, with the owner's permission.

## 14. Open questions

To settle while building. Each one has a safe default or is a setting.

- **Attendance:** settled by the owner on 16 Nov 2026 (§8.1, OWN-7) **(v1.3)**: when "late" becomes "half day"; leaving after 13:00 or arriving late in the afternoon; Sundays and public holidays. Still open: any extra penalty for a no-show.
- **Products:** special items (prescription-only drugs, vaccines kept cold, poisons); jumla thresholds; open-bag tolerance.
- **The product:** its name (separate from MPC); target market *(default: agro-vet and farm-supply shops)*; Swahili with an English switch.
- **The owner's decisions:** credit rules (who, approval, limits, non-payment); discount and floor limits; who sees buying prices and profit; who may cancel or refund; prices visible online; customers seeing their own debt; budget (devices, router UPS, printer, SMS/WhatsApp, hosting); a second branch; VAT and vet-drug licence rules; TRA receipt practice; permission to use the shop's name and numbers in the portfolio; an SMS for each debt.
- **Releases:** settled in portion 4 — attendance is R1b and is built first (04 BP7, ADR-0033). Still open: when practice mode arrives *(default: R2; earlier if new Drugs staff need it — 04 §20)*.

## 15. Glossary

| Term | Meaning |
|---|---|
| MPC | Mabatini Pumba Center, the first shop |
| Side | One section of a shop with its own workers, stock view and drawer (MPC: Drugs, Foods) |
| Pembejeo za kilimo na mifugo | Farm and livestock inputs: the Drugs side |
| Pumba | Bran |
| Madeni | Customer debts (credit) |
| Lipa Namba | A merchant mobile-money number |
| Jumla / Rejareja | Wholesale / retail |
| Kusaga | Grinding (e.g. maize) |
| Selling unit | A way of selling a product (Bag 50 kg, 1 kg) with its own price |
| Floor price | The lowest price staff may bargain to without approval |
| Formula | A feed recipe: ingredients and proportions |
| Job | A service order (mixing, grinding) with a status |
| Exchange | Customer's whole maize in, ground maize out, grinding charge paid |
| Production | The shop turning its own stock into another product |
| Partner | A trusted outside person who delivers or provides services and may take goods on credit |
| Cash-up | The end-of-day count of a drawer against the expected amount |
| Blind count | Counting before seeing the expected amount |
| Debt aging | Who owes what, and since when |
| Receivables / Payables | What customers owe the shop / what the shop owes suppliers |
| Reconciliation | Comparing expected with actual, within an allowed difference |
| EFD / VFD | TRA's electronic / virtual fiscal devices for tax receipts |
| Shop (tenant) | One business using the system; its data is fully separate |
| ADR | Architecture Decision Record: a short file recording one big decision and why (`docs/adr/`) |
