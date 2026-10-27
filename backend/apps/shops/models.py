"""apps/shops/models.py — the shops tables: a shop, its sides, where their stock sits and where money lands (02 §4).

Shop is one business, the tenant: every shop table points at one, and the tenancy guard (CORE-2) keeps
each shop's rows apart (ADR-0022). A shop is live (a real business, like MPC), demo (the public demo's
fake shop, ADR-0029) or practice (a copy where new workers learn, ADR-0014).

A Side is a section of one shop (ADR-0001): MPC has Drugs and Foods. Each side keeps its stock in
StockLocations (ADR-0002) and takes money into PaymentAccounts: its own cash drawer, and a Lipa Namba or a
bank account it may share with the other side (PaymentAccountSide links them). apps/shops/services.py
makes a new shop with all of these at once (create_shop). Dated settings join this file in CORE-4.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.languages import Language
from apps.core.models import ShopScoped, TimeStamped, UUIDModel


# Outside Shop so that Shop.Meta can read their values: a nested class can't see the names of the class
# around it. Each list is used by its field and by its database rule below.
class ShopKind(models.TextChoices):
    LIVE = "live", "Live"
    DEMO = "demo", "Demo"
    PRACTICE = "practice", "Practice"


class ShopStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class Shop(UUIDModel, TimeStamped):
    # UUIDModel and TimeStamped (CORE-1) give `id` and `created_at`. Not ShopScoped (CORE-2): the shop
    # is the tenant itself, so it has no `shop` of its own (ADR-0022).

    name = models.CharField(max_length=100)
    # The short form people already say: MPC for Mabatini Pumba Center (Jack, 26 Oct 2026). One shop
    # each; its shape (2 to 10 capital letters) is a rule in Meta, and clean() tidies what was typed.
    code = models.CharField(max_length=10, unique=True)
    # Times are stored in UTC and shown in the shop's own time, and its business dates are worked out
    # in this zone (02 §1). 64 characters hold the longest name in the tz database.
    timezone = models.CharField(max_length=64, default="Africa/Dar_es_Salaam")
    # An ISO 4217 code. Money is an exact 2-place decimal in this currency (ADR-0024). Fixed once the shop
    # exists: amounts don't carry their own currency, so a change would relabel them all (the admin).
    currency = models.CharField(max_length=3, default="TZS")
    # The shop's own language. Each person's screens follow their own choice (User.language, 03 §7.4);
    # 02 §4 names this one, and the cards that read it decide where it applies.
    default_language = models.CharField(max_length=2, choices=Language, default=Language.SWAHILI)
    # Set when the shop is made, and never changed: a live shop turned into a demo one would be open to
    # the demo's fake data and resets (ADR-0029), so the admin shows it read-only once the shop exists.
    # Only the admin guards this today; the database doesn't. A shop made with the wrong kind is put
    # right by the superuser, from the Django shell.
    kind = models.CharField(max_length=10, choices=ShopKind, default=ShopKind.LIVE)
    # Only a practice shop names the shop it copies (ADR-0014); NULL for every other shop. PROTECT:
    # nothing is deleted (rule 7), so a shop with practice copies can't vanish from under them.
    # limit_choices_to: the shop it copies is a live one, never the demo or another copy. The database
    # can't check another row's kind, so this is Django's check: every form (full_clean) refuses another
    # kind, and the admin's drop-down lists live shops only. Code that saves without full_clean skips it.
    practice_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="practice_shops",
        limit_choices_to={"kind": ShopKind.LIVE},
    )
    # Suspended = switched off, with nothing deleted (rule 7). A suspension needs who, when and why,
    # which only the audit trail (CTRL-2) can record, so for now nothing changes it: the admin shows it
    # read-only.
    status = models.CharField(max_length=10, choices=ShopStatus, default=ShopStatus.ACTIVE)

    class Meta:
        # The database is the last guard (03 §5.6): even code that skips the admin's form and saves a Shop
        # directly can't store a row that breaks these. Each rule carries a code, which full_clean passes
        # on to forms and the API: the screens translate codes, the server sends no sentences (ADR-0032).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=ShopKind.values),
                name="shops_shop_kind_known",
                violation_error_code="shop.kind_unknown",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ShopStatus.values),
                name="shops_shop_status_known",
                violation_error_code="shop.status_unknown",
            ),
            # Capital letters only also makes `unique` ignore letter case: "mpc" can't be stored, so it
            # can never sit beside "MPC". Letters only, as Jack chose; allowing digits later is a new
            # migration that loosens this, and loosening never breaks the rows already stored.
            models.CheckConstraint(
                condition=models.Q(code__regex=r"^[A-Z]{2,10}$"),
                name="shops_shop_code_capital_letters",
                violation_error_code="shop.code_invalid",
            ),
            # The shape of an ISO 4217 code (TZS, KES, USD). Which currencies exist isn't checked here.
            models.CheckConstraint(
                condition=models.Q(currency__regex=r"^[A-Z]{3}$"),
                name="shops_shop_currency_three_capitals",
                violation_error_code="shop.currency_invalid",
            ),
            models.CheckConstraint(
                condition=models.Q(default_language__in=Language.values),
                name="shops_shop_language_known",
                violation_error_code="shop.language_unknown",
            ),
            # ADR-0014: a practice shop names the shop it copies...
            models.CheckConstraint(
                condition=~models.Q(kind=ShopKind.PRACTICE) | models.Q(practice_of__isnull=False),
                name="shops_shop_practice_names_its_shop",
                violation_error_code="shop.practice_needs_shop",
            ),
            # ...and only a practice shop names one.
            models.CheckConstraint(
                condition=models.Q(kind=ShopKind.PRACTICE) | models.Q(practice_of__isnull=True),
                name="shops_shop_only_practice_names_a_shop",
                violation_error_code="shop.practice_of_not_practice",
            ),
            # Never itself, which would pass both rules above. That it names a *live* shop needs a look at
            # another row, which a check constraint can't take: `practice_of`'s limit_choices_to does that.
            models.CheckConstraint(
                condition=~models.Q(practice_of=models.F("id")),
                name="shops_shop_not_practice_of_itself",
                violation_error_code="shop.practice_of_itself",
            ),
        ]

    def __str__(self) -> str:
        # How the admin lists shops, and names one in a drop-down: "Duka la Mfano (MFANO)".
        return f"{self.name} ({self.code})"

    def clean(self) -> None:
        # The admin's form runs this (through full_clean) before the database rules and `unique` are
        # checked, so they see the stored shape: " mpc " becomes "MPC".
        super().clean()
        self.code = (self.code or "").strip().upper()
        # The database has no list of timezones, so this check lives here. ZoneInfo looks the name up in
        # the tz database (the system's own, on Linux): an unknown name raises ZoneInfoNotFoundError, and
        # a string that can't be a zone name at all (a path such as "../x") raises ValueError.
        # full_clean runs clean() even after the field's own check has failed, so a missing timezone
        # (None or "") is left to that check: it reports it once, and ZoneInfo(None) would crash.
        if not self.timezone:
            return
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError, ValueError:
            raise ValidationError(
                {"timezone": ValidationError("Unknown timezone.", code="shop.timezone_unknown")}
            ) from None


class SaleFlow(models.TextChoices):
    # 02 §4: how a side sells. One screen: one seller writes the sale, takes the money and hands the
    # goods over. Writer, cashier, loader: three people, one step each, as on MPC's busy Foods side
    # (spec §3).
    ONE_SCREEN = "one_screen", "One screen"
    WRITER_CASHIER_LOADER = "writer_cashier_loader", "Writer, cashier, loader"


class Side(ShopScoped):
    # A section of one shop (ADR-0001, 02 §4): its own stock, drawer, staff roles and debts, sharing the
    # shop's products, prices and customers. ShopScoped (CORE-2) gives `id`, `shop`, `created_at`,
    # `created_by` and the guard on reads.

    # The owner's own word for it: "Dawa".
    name = models.CharField(max_length=40)
    # One capital letter. It starts every human number made on the side's devices, like D2-0457 (D7), so a
    # printed slip names its side. Its shape and its uniqueness within the shop are rules in Meta.
    code = models.CharField(max_length=1)
    sale_flow = models.CharField(max_length=24, choices=SaleFlow, default=SaleFlow.ONE_SCREEN)
    # Off until the owner agrees to start using the side (ADR-0033), so a new side never reaches the
    # counters by surprise. The switch comes with the settings screen (SHOP-3).
    is_live = models.BooleanField(default=False)

    class Meta(ShopScoped.Meta):
        # Builds on ShopScoped.Meta, so `objects`, with the guard, stays the default manager (CORE-2).
        # The database is the last guard (03 §5.6); full_clean checks the same rules first, so a person
        # gets a code, not a database error (ADR-0032).
        constraints = [
            # Capital letters only, so the unique rule below also ignores letter case: "d" can never
            # sit beside "D".
            models.CheckConstraint(
                condition=models.Q(code__regex=r"^[A-Z]$"),
                name="shops_side_code_one_capital_letter",
                violation_error_code="side.code_invalid",
            ),
            models.CheckConstraint(
                condition=models.Q(sale_flow__in=SaleFlow.values),
                name="shops_side_sale_flow_known",
                violation_error_code="side.sale_flow_unknown",
            ),
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="shops_side_name_not_blank",
                violation_error_code="side.name_blank",
            ),
            # Two sides with one letter would print the same numbers. Leads with `shop`, as every index
            # does. The message is there for the code's sake: on a unique rule over fields, Django
            # replaces the code with its own generic one unless the rule has its own message too.
            models.UniqueConstraint(
                fields=["shop", "code"],
                name="shops_side_code_unique",
                violation_error_code="side.code_taken",
                violation_error_message="Another side of this shop has this letter.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    def clean(self) -> None:
        # full_clean runs this after each field's own checks and before the rules above.
        # - The code: "d" is stored as "D". A letter with spaces around it (" d") never gets here: it has
        #   already failed the field's one-character length, with Django's own `max_length` code. Forms
        #   and DRF trim spaces before that; code that calls full_clean itself, like create_shop, doesn't.
        # - The name: trimmed, so a name of only spaces becomes "" and the not-blank rule refuses it
        #   (side.name_blank), instead of an empty-looking side on every screen. The location and the
        #   drawer create_shop names after the side get the trimmed name too.
        super().clean()
        self.code = (self.code or "").upper()
        self.name = (self.name or "").strip()


class StockLocation(ShopScoped):
    # A place where a side's stock sits (ADR-0002, 02 §4). Every stock movement will name one (STK-1), so
    # store rooms (Later) and transfers between sides (R2) need no change to the stock ledger. R1 has one
    # per side, the default, made with the side by create_shop; the screens never show it.

    # T1: the side belongs to the same shop as the location. The database can't compare two rows' shops,
    # so the services check it. PROTECT: nothing is deleted (rule 7). related_name="+": no
    # `side.stocklocation_set`; locations are read through their own guarded `objects`. db_index=False:
    # indexes lead with `shop`, and the unique rule below already indexes (shop, side) for the default
    # locations, the only ones R1 has.
    side = models.ForeignKey(Side, on_delete=models.PROTECT, related_name="+", db_index=False)
    name = models.CharField(max_length=60)
    # The location a side's stock goes to when nobody picks one, which in R1 is always.
    is_default = models.BooleanField(default=False)

    class Meta(ShopScoped.Meta):
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="shops_stocklocation_name_not_blank",
                violation_error_code="location.name_blank",
            ),
            # One default per side: two would leave "where does this side's stock go?" with two answers.
            # A partial unique index: only the default rows are compared, so a side can still have other
            # locations.
            models.UniqueConstraint(
                fields=["shop", "side"],
                condition=models.Q(is_default=True),
                name="shops_stocklocation_one_default_per_side",
                violation_error_code="location.default_taken",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class PaymentAccountKind(models.TextChoices):
    CASH_DRAWER = "cash_drawer", "Cash drawer"
    # A Lipa Namba: customers pay from their phone into the shop's number.
    MOBILE_MONEY = "mobile_money", "Mobile money"
    BANK = "bank", "Bank"


class PaymentAccountStatus(models.TextChoices):
    # As for products and contacts (02 §14): an account the shop stops using is archived, never deleted
    # (rule 7). Archiving needs who, when and why, which only the audit trail (CTRL-2) records, so
    # nothing changes the status yet.
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class PaymentAccount(ShopScoped):
    # Where money lands (02 §4): a side's cash drawer, a Lipa Namba, a bank account. Every payment and
    # money movement will name one (MONEY-1, CASH-1), so what each account holds is a sum over its rows.

    kind = models.CharField(max_length=12, choices=PaymentAccountKind)
    # The shop's own name for it. create_shop names a drawer after its side ("Dawa"), and the screens add
    # the translated kind ("Droo"): the server makes up no words (ADR-0032).
    name = models.CharField(max_length=60)
    # Who runs it: the network for a Lipa Namba ("M-Pesa"), the bank for an account. "" for a drawer.
    provider = models.CharField(max_length=40, blank=True)
    # The Lipa Namba or the bank account number, as a customer reads it. Text, not a number: it can start
    # with 0. "" for a drawer. A real shop's numbers never enter the repo (rule 10).
    number = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=10, choices=PaymentAccountStatus, default=PaymentAccountStatus.ACTIVE)
    # The sides that take money into it: a drawer serves its own side, and MPC's one Lipa Namba serves
    # both (each payment still records its side). Through our own link table, not Django's automatic one:
    # that one would have no `shop` (T1), and its links would vanish with the account or the side
    # (CASCADE, against rule 7). related_name="+": a side's accounts are read through the links.
    sides = models.ManyToManyField(Side, through="PaymentAccountSide", related_name="+")

    class Meta(ShopScoped.Meta):
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=PaymentAccountKind.values),
                name="shops_paymentaccount_kind_known",
                violation_error_code="payment_account.kind_unknown",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=PaymentAccountStatus.values),
                name="shops_paymentaccount_status_known",
                violation_error_code="payment_account.status_unknown",
            ),
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="shops_paymentaccount_name_not_blank",
                violation_error_code="payment_account.name_blank",
            ),
            # A drawer is a box under the counter: no provider, no number. A Lipa Namba or a bank account
            # is nothing without both: a customer can't pay into it, and the owner can't check its
            # statement against the system's total (MONEY-5).
            models.CheckConstraint(
                condition=models.Q(kind=PaymentAccountKind.CASH_DRAWER, provider="", number="")
                | (~models.Q(kind=PaymentAccountKind.CASH_DRAWER) & ~models.Q(provider="") & ~models.Q(number="")),
                name="shops_paymentaccount_details_match_kind",
                violation_error_code="payment_account.details_mismatch",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class PaymentAccountSide(ShopScoped):
    # One link: this account takes money for this side (02 §4). The table behind PaymentAccount.sides,
    # with a `shop` like every shop row (T1). A link is written as a row of this table, with its shop,
    # never through `account.sides.add()`, which knows nothing of the shop.

    # T1: the account and the side belong to the link's shop; the services check it. PROTECT: nothing is
    # deleted (rule 7). db_index=False: the unique rule below indexes (shop, account, side).
    account = models.ForeignKey(PaymentAccount, on_delete=models.PROTECT, related_name="+", db_index=False)
    side = models.ForeignKey(Side, on_delete=models.PROTECT, related_name="+", db_index=False)

    class Meta(ShopScoped.Meta):
        constraints = [
            # Linked once: a second link to the same side would count that side twice in any total built
            # from the links. The message is there for the code's sake, as on Side's letter.
            models.UniqueConstraint(
                fields=["shop", "account", "side"],
                name="shops_paymentaccountside_once",
                violation_error_code="payment_account.side_taken",
                violation_error_message="This account already serves this side.",
            ),
        ]
