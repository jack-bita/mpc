"""apps/shops/models.py — the shops tables. For now one: Shop, one business, the tenant (02 §4).

Every shop table will point at a Shop, and the tenancy guard (CORE-2) keeps each shop's rows apart
(ADR-0022). A shop is live (a real business, like MPC), demo (the public demo's fake shop, ADR-0029)
or practice (a copy where new workers learn, ADR-0014). Sides, stock locations and payment accounts
join this file in SHOP-2, dated settings in CORE-4.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.languages import Language
from apps.core.models import TimeStamped, UUIDModel


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
    # An ISO 4217 code. Money is an exact 2-place decimal in this currency (ADR-0024).
    currency = models.CharField(max_length=3, default="TZS")
    # The shop's own language. Each person's screens follow their own choice (User.language, 03 §7.4);
    # 02 §4 names this one, and the cards that read it decide where it applies.
    default_language = models.CharField(max_length=2, choices=Language, default=Language.SWAHILI)
    # Set when the shop is made, and never changed: a live shop turned into a demo one would be open to
    # the demo's fake data and resets (ADR-0029), so the admin shows it read-only once the shop exists.
    kind = models.CharField(max_length=10, choices=ShopKind, default=ShopKind.LIVE)
    # Only a practice shop names the shop it copies (ADR-0014); NULL for every other shop. PROTECT:
    # nothing is deleted (rule 7), so a shop with practice copies can't vanish from under them.
    practice_of = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="practice_shops"
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
            # another row, which a check constraint can't take: the service that makes practice shops (R2)
            # checks that.
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
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError, ValueError:
            raise ValidationError(
                {"timezone": ValidationError("Unknown timezone.", code="shop.timezone_unknown")}
            ) from None
