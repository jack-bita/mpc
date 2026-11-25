"""apps/staffpay/services — the writes of attendance and pay, and the reads that go through them, in four files:

    book.py        the book of days: what each worker's day was, worked out and kept
    attendance.py  the month and a worker's month on the screen, a decision on a day, a tap added or crossed out
    money.py       what a person types for the pay: daily rates, the day's meal money, money given before payday
    pay.py         the month's pay, worked out from all of them, and read from its payslips once it is approved
    approval.py    approving a month's pay: the payslips kept, and their days marked as paid

Each file says what it owns. They were one file until WAGE-3, which grew past what anyone reads in one sitting. The rest
of the code takes what it needs from here (`from apps.staffpay.services import pay_month`), so a function can move from
one file to another with no change anywhere else; a file of the package takes from its neighbour's own file, as taking
from here would be a circle. What isn't listed is the package's own.
"""

from apps.staffpay.services.approval import approve_month
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
    PayMonth,
    ToApprove,
    WorkerPay,
    WorkerPayMonth,
    pay_month,
    worker_pay,
)

__all__ = [
    "DEMO_ADD_REASONS",
    "DEMO_MONEY_VOID_REASONS",
    "DEMO_REASONS",
    "DEMO_VOID_REASONS",
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
    "PhotoState",
    "TapLine",
    "TapPhoto",
    "TapStamp",
    "ToApprove",
    "VoidedAdvance",
    "VoidedMealMoney",
    "WorkerAttendance",
    "WorkerDay",
    "WorkerMonth",
    "WorkerPay",
    "WorkerPayMonth",
    "add_tap",
    "advance_line",
    "advances_month",
    "approve_month",
    "attendance_month",
    "decide_day",
    "decision_of",
    "meal_line",
    "meal_money_days",
    "pay_month",
    "ready_advance_void_reasons",
    "record_advance",
    "record_meal_money",
    "set_pay_rate",
    "tap_line",
    "void_advance",
    "void_meal_money",
    "void_tap",
    "where_it_falls",
    "work_out_days",
    "worker_attendance",
    "worker_pay",
]
