"""apps/core/permissions.py — the permission codes, and the six role templates built from them (02 §5, 03 §5.8).

A permission is one action a person may do, named by a code: `sale.bargain`, lower a price down to the floor. The
codes are a fixed list in code, not a table: a screen can give a person a code from the list, never make up a new
one, and every app checks against the same list. A card whose action needs a permission takes its code from here;
a new action is a new line here. A code, once stored in a role or a grant, never changes and never names another
action: a person would then hold something nobody chose to give them (as with type codes, apps/core/links.py).

A role template is a named bundle of codes. The templates live here, beside the codes (03 §5.8). Each new shop gets
its own copy of them, as Role rows its owner can change later (set_up_shop, apps/people/services.py). So a change
here reaches the shops made after it, never a shop that already has its roles.

Only data lives here. Who holds which code, and where, is `people`'s (apps/people/permissions.py): `core` is layer 0
and may not import `people` (ADR-0035).
"""

from django.db import models

# The shape of a code, "area.action" in small letters and underscores (02 §5), and its longest length, the size of
# the column that stores one. A test keeps every code storable (apps/core/tests/test_permission_codes.py).
PERMISSION_CODE_SHAPE = r"^[a-z]+\.[a-z][a-z_]*$"
PERMISSION_CODE_MAX_LENGTH = 40


class Permission(models.TextChoices):
    # Every action a person may be given, as 02 §5 lists them, grouped by the part of the shop they belong to.

    # Selling (02 §9).
    SALE_WRITE = "sale.write", "Write a sale or an order"
    SALE_TAKE_PAYMENT = "sale.take_payment", "Take a payment"
    SALE_HAND_OVER = "sale.hand_over", "Hand the goods over"
    SALE_BARGAIN = "sale.bargain", "Lower a price, down to the floor"
    SALE_BELOW_FLOOR_APPROVE = "sale.below_floor_approve", "Approve a price below the floor"
    SALE_JUMLA_SWITCH = "sale.jumla_switch", "Switch a sale to the jumla price"
    SALE_CANCEL = "sale.cancel", "Cancel a sale"
    SALE_REFUND = "sale.refund", "Refund a sale"
    # Credit and debts (02 §8).
    CREDIT_GIVE = "credit.give", "Sell on credit"
    CREDIT_APPROVE = "credit.approve", "Approve credit over a limit"
    DEBT_VIEW = "debt.view", "See the debts"
    DEBT_ADJUST = "debt.adjust", "Adjust or write off a debt"
    # Products and prices (02 §6), contacts (02 §8).
    PRICE_CHANGE = "price.change", "Change a price"
    COST_VIEW = "cost.view", "See buying prices and profit"
    PRODUCT_MANAGE = "product.manage", "Add and change products"
    CONTACT_MANAGE = "contact.manage", "Add and change customers, suppliers and partners"
    # Stock (02 §7).
    STOCK_RECEIVE = "stock.receive", "Complete a delivery, with its buying prices"
    STOCK_WEIGH = "stock.weigh", "Weigh goods as they arrive"
    STOCK_LOSS = "stock.loss", "Record a loss"
    STOCK_COUNT = "stock.count", "Count the stock"
    STOCK_COUNT_APPROVE = "stock.count_approve", "Approve a stock count"
    STOCK_TRANSFER = "stock.transfer", "Move stock from one place to another"
    # Money and drawers (02 §10).
    MONEY_EXPENSE = "money.expense", "Pay an expense"
    MONEY_ADVANCE = "money.advance", "Give a worker an advance"
    MONEY_WITHDRAW = "money.withdraw", "Take money out of a drawer"
    DRAWER_COUNT = "drawer.count", "Count a drawer"
    DRAWER_CONFIRM = "drawer.confirm", "Confirm a counted drawer"
    DRAWER_APPROVE = "drawer.approve", "Approve the day"
    # Staff, attendance and pay (02 §5, §12).
    STAFF_MANAGE = "staff.manage", "Add workers and give them roles"
    ATTENDANCE_MANAGE = "attendance.manage", "Fix attendance"
    PAY_RUN = "pay.run", "Prepare the month's pay"
    PAY_APPROVE = "pay.approve", "Approve the month's pay"
    # The shop itself (02 §4, §5, §13).
    SETTINGS_MANAGE = "settings.manage", "Change the shop's rules and rates"
    DEVICE_MANAGE = "device.manage", "Register and block devices"
    FLAG_REVIEW = "flag.review", "Resolve or dismiss a side's flags"
    REPORT_VIEW = "report.view", "See the reports"
    # Release 2: machine jobs and production (02 §11).
    JOB_MANAGE = "job.manage", "Run machine jobs"
    PRODUCTION_RUN = "production.run", "Record a production run"


class RoleTemplate(models.TextChoices):
    # The six roles every new shop starts with (spec §6). The code names the template a shop's role was copied
    # from; the screens show its name in the person's language (ADR-0032).
    OWNER = "owner", "Owner"
    MANAGER = "manager", "Manager"
    SELLER = "seller", "Seller"
    ORDER_WRITER = "order_writer", "Order writer"
    CASHIER = "cashier", "Cashier"
    WORKER = "worker", "Worker"


# The owner's own four: the day's final approval, the pay, the shop's rules, and who works there (spec §6).
_OWNERS_OWN = frozenset(
    {Permission.DRAWER_APPROVE, Permission.PAY_APPROVE, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE}
)

# What each template holds, as Jack chose them for MPC (29 Oct 2026, from spec §6). Each shop's owner can change
# their own copy later. A new code reaches the Owner by itself, and the Manager unless it joins the owner's own
# four; any other role, only by a line here. Weighing goods as they arrive is everyone's job (Jack): it is on
# every role, and buying prices stay with whoever completes the delivery.
ROLE_TEMPLATES: dict[RoleTemplate, frozenset[Permission]] = {
    # Everything, on every side: the shop is theirs.
    RoleTemplate.OWNER: frozenset(Permission),
    # Runs the shop when the owner is away. Any of the owner's four can still go to one manager as a grant.
    RoleTemplate.MANAGER: frozenset(Permission) - _OWNERS_OWN,
    # One screen on the Drugs side: writes, takes the money and hands over; bargains down to the floor; sells on
    # credit and takes back a sale; adds customers and suppliers; counts the stock and their own drawer.
    RoleTemplate.SELLER: frozenset(
        {
            Permission.SALE_WRITE,
            Permission.SALE_TAKE_PAYMENT,
            Permission.SALE_HAND_OVER,
            Permission.SALE_BARGAIN,
            Permission.SALE_REFUND,
            Permission.CREDIT_GIVE,
            Permission.DEBT_VIEW,
            Permission.CONTACT_MANAGE,
            Permission.STOCK_COUNT,
            Permission.STOCK_WEIGH,
            Permission.DRAWER_COUNT,
        }
    ),
    # Writes orders on the Foods side and bargains down to the floor; adds customers, suppliers, products and
    # prices (each price keeps the name of whoever set it); sees debts.
    RoleTemplate.ORDER_WRITER: frozenset(
        {
            Permission.SALE_WRITE,
            Permission.SALE_BARGAIN,
            Permission.DEBT_VIEW,
            Permission.CONTACT_MANAGE,
            Permission.PRODUCT_MANAGE,
            Permission.PRICE_CHANGE,
            Permission.STOCK_WEIGH,
        }
    ),
    # Takes the money on the Foods side, and may write orders too; counts their own drawer; sees debts.
    RoleTemplate.CASHIER: frozenset(
        {
            Permission.SALE_TAKE_PAYMENT,
            Permission.SALE_WRITE,
            Permission.DEBT_VIEW,
            Permission.STOCK_WEIGH,
            Permission.DRAWER_COUNT,
        }
    ),
    # A loader: hands goods over against paid slips, and weighs what arrives. Clocking in needs no permission.
    RoleTemplate.WORKER: frozenset({Permission.SALE_HAND_OVER, Permission.STOCK_WEIGH}),
}
