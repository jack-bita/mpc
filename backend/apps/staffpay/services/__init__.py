"""apps/staffpay/services — the writes of attendance and pay, and the reads that go through them, in seven files:

    book.py        the book of days: what each worker's day was, worked out and kept
    attendance.py  the month and a worker's month on the screen, a decision on a day, a tap added or crossed out
    money.py       what a person types for the pay: daily rates, the day's meal money, money given before payday
    pay.py         the month's pay, worked out from all of them, and read from its payslips once it is approved
    approval.py    approving a month's pay: the payslips kept, and their days marked as paid
    payment.py     handing a payslip out, in cash with the worker's signature or with a transaction number, and
                   crossing out one marked by mistake (WAGE-9)
    correction.py  a mistake found after a month's approval, put right in a later month's pay (WAGE-10)

Each file says what it owns. They were one file until WAGE-3, which grew past what anyone reads in one sitting. The rest
of the code takes what it needs from here (`from apps.staffpay.services import pay_month`), so a function can move from
one file to another with no change anywhere else; a file of the package takes from its neighbour's own file, as taking
from here would be a circle. What isn't listed is the package's own.
"""

from apps.staffpay.services.approval import APPROVES, approve_leaver, approve_month
from apps.staffpay.services.attendance import (
    DEMO_ADD_REASONS,
    DEMO_REASONS,
    DEMO_VOID_REASONS,
    AttendanceMonth,
    DayDecision,
    DayOption,
    PhotoState,
    TapLine,
    TapPhoto,
    TapStamp,
    WorkerAttendance,
    WorkerDay,
    WorkerMonth,
    add_tap,
    attendance_month,
    decide_day,
    decision_of,
    tap_line,
    void_tap,
    worker_attendance,
)
from apps.staffpay.services.book import SUNDAY, where_it_falls, work_out_days
from apps.staffpay.services.correction import DEMO_CORRECTION_REASONS, ready_correction_reasons, record_correction
from apps.staffpay.services.money import (
    DEMO_MONEY_VOID_REASONS,
    AdvanceLine,
    AdvancesMonth,
    AdvanceWorker,
    MealDay,
    MealMoneyDays,
    MealMoneyLine,
    VoidedAdvance,
    VoidedMealMoney,
    advance_line,
    advances_month,
    meal_line,
    meal_money_days,
    ready_advance_void_reasons,
    record_advance,
    record_meal_money,
    set_pay_rate,
    void_advance,
    void_meal_money,
)
from apps.staffpay.services.pay import (
    Approval,
    OpenDay,
    PaymentLine,
    PayMonth,
    ToApprove,
    VoidedPayment,
    WorkerPay,
    WorkerPayMonth,
    pay_month,
    payment_line,
    worker_pay,
)
from apps.staffpay.services.payment import (
    DEMO_PAYMENT_VOID_REASONS,
    PAYS,
    keeps_signatures,
    pay_payslip,
    ready_payment_void_reasons,
    void_payslip_payment,
)

__all__ = [
    "APPROVES",
    "DEMO_ADD_REASONS",
    "DEMO_CORRECTION_REASONS",
    "DEMO_MONEY_VOID_REASONS",
    "DEMO_PAYMENT_VOID_REASONS",
    "DEMO_REASONS",
    "DEMO_VOID_REASONS",
    "PAYS",
    "SUNDAY",
    "AdvanceLine",
    "AdvanceWorker",
    "AdvancesMonth",
    "Approval",
    "AttendanceMonth",
    "DayDecision",
    "DayOption",
    "MealDay",
    "MealMoneyDays",
    "MealMoneyLine",
    "OpenDay",
    "PayMonth",
    "PaymentLine",
    "PhotoState",
    "TapLine",
    "TapPhoto",
    "TapStamp",
    "ToApprove",
    "VoidedAdvance",
    "VoidedMealMoney",
    "VoidedPayment",
    "WorkerAttendance",
    "WorkerDay",
    "WorkerMonth",
    "WorkerPay",
    "WorkerPayMonth",
    "add_tap",
    "advance_line",
    "advances_month",
    "approve_leaver",
    "approve_month",
    "attendance_month",
    "decide_day",
    "decision_of",
    "keeps_signatures",
    "meal_line",
    "meal_money_days",
    "pay_month",
    "pay_payslip",
    "payment_line",
    "ready_advance_void_reasons",
    "ready_correction_reasons",
    "ready_payment_void_reasons",
    "record_advance",
    "record_correction",
    "record_meal_money",
    "set_pay_rate",
    "tap_line",
    "void_advance",
    "void_meal_money",
    "void_payslip_payment",
    "void_tap",
    "where_it_falls",
    "work_out_days",
    "worker_attendance",
    "worker_pay",
]
