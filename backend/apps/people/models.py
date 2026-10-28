"""apps/people/models.py — the people tables: User, a human across every shop, and StaffMember, their job
at one shop (02 §5).

A User is the person, not the job: the same person can work at MPC and in its practice shop, and their
job at each shop (StaffMember) holds the nickname, the status and the PIN; the roles join it in PPL-3.
So User keeps only what belongs to the person. It is global, one of the few tables without a `shop`
(ADR-0022). User is the project's first migration on purpose: Django fixes its user table at the first
`migrate` and can't swap it afterwards (ADR-0012, 04 BP5).
"""

import uuid
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower

from apps.core.fields import PhoneField
from apps.core.languages import Language
from apps.core.models import ShopScoped, TimeStamped, UUIDModel


class UserManager(BaseUserManager["User"]):
    # Not written into the migrations (no `use_in_migrations`): inside a migration, User is a bare copy
    # without set_password or full_clean, so this manager couldn't run there, and 0001 would import it forever.

    def create_user(
        self,
        full_name: str,
        email: str | None = None,
        phone: str | None = None,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        """Add one person. Only the name is required: a worker is added with a name and maybe a phone."""
        user = self.model(full_name=full_name, email=email, phone=phone, **extra_fields)
        if password:
            user.set_password(password)  # stored as a hash, never as typed
        else:
            # The password column is never empty: Django stores "!" and random characters, which no
            # typed password can match. A PIN-only worker can't be logged in to with a password.
            user.set_unusable_password()
        # The same rules as the admin's form, before anything is written: every field, clean() below,
        # `unique` and the database rules. A broken rule is a ValidationError, under the field's name when
        # it belongs to one field (a database rule that spans fields comes under `__all__`).
        user.full_clean()
        user.save(using=self._db)
        return user

    def create_superuser(
        self, full_name: str, email: str | None = None, password: str | None = None, **extra_fields: Any
    ) -> User:
        """Add someone who can open the Django admin. `createsuperuser` calls this (ADR-0012)."""
        if not email:
            # The admin's login name is the email (USERNAME_FIELD), so refuse now, not at the first login.
            raise ValueError("A superuser needs an email: it is the admin's login name.")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(full_name, email=email, password=password, **extra_fields)

    def get_by_natural_key(self, username: str | None) -> User:
        # The admin login and createsuperuser find a person by login name. Emails are stored in lower
        # case, so look up the lower-case form: "Admin@Example.com" finds admin@example.com.
        return self.get(email=(username or "").strip().lower())


class User(UUIDModel, TimeStamped, AbstractBaseUser, PermissionsMixin):
    # UUIDModel and TimeStamped (CORE-1) give `id` and `created_at`. AbstractBaseUser gives `password`
    # and `last_login`. PermissionsMixin gives `is_superuser` and Django's groups and permissions, which
    # only the Django admin uses: shop permissions are our own codes on a person's job (02 §5, PPL-3).

    full_name = models.CharField(max_length=150)
    # Optional, so a worker without a phone can still be added. A missing phone is NULL, never "":
    # PostgreSQL never counts two NULLs as the same value, so `unique` only compares real numbers.
    # PhoneField stores E.164 (`+255712345678`) and cleans what was typed first (apps/core/fields.py).
    phone = PhoneField(unique=True, null=True, blank=True)
    # Optional for the same reason: most people at the shop have none. Stored in lower case.
    email = models.EmailField(unique=True, null=True, blank=True)
    # The screens follow the logged-in person's language (03 §7.4). Swahili first.
    language = models.CharField(max_length=2, choices=Language, default=Language.SWAHILI)
    # Nothing is deleted: a person who must never log in again is switched off instead.
    is_active = models.BooleanField(default=True)
    # May open the Django admin. In practice only the superuser.
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    # No username. Django's login name is the email: the admin login and `createsuperuser` use it.
    USERNAME_FIELD = "email"
    # What `createsuperuser` asks for besides the email and the password.
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        # The database is the last guard (03 §5.6): even code that skips create_user and saves a User
        # directly can't store a row that breaks these. create_user checks the same rules first
        # (full_clean), so a person gets a clear message instead of a database error. Each rule carries a
        # code, which full_clean passes on to forms and the API: the screens translate codes, the server
        # sends no sentences (ADR-0032).
        constraints = [
            # Emails are stored in lower case, so `unique` on email is unique whatever the letter case.
            models.CheckConstraint(
                condition=models.Q(email=Lower("email")),
                name="people_user_email_lower_case",
                violation_error_code="user.email_not_lower_case",
            ),
            # A missing email is NULL, never "": two "" would clash on `unique`.
            models.CheckConstraint(
                condition=~models.Q(email=""),
                name="people_user_email_not_blank",
                violation_error_code="user.email_blank",
            ),
            # Only the normalised form: +, a country code that never starts with 0, 7 to 15 digits in all.
            # Same code as the phone cleaner's (apps/core/phones.py): to a person it is the same mistake.
            models.CheckConstraint(
                condition=models.Q(phone__regex=r"^\+[1-9][0-9]{6,14}$"),
                name="people_user_phone_e164",
                violation_error_code="phone.invalid",
            ),
            models.CheckConstraint(
                condition=models.Q(language__in=Language.values),
                name="people_user_language_known",
                violation_error_code="user.language_unknown",
            ),
            # The superuser logs in to the admin by email, so one without an email could never log in.
            models.CheckConstraint(
                condition=models.Q(is_superuser=False) | models.Q(email__isnull=False),
                name="people_user_superuser_has_email",
                violation_error_code="user.superuser_needs_email",
            ),
        ]

    def __str__(self) -> str:
        # The admin shows people by name. Django's default is the login name, and most workers have no email.
        return self.full_name

    def clean(self) -> None:
        # One door for every new or changed person: the admin's form and create_user both run this
        # (through full_clean) before saving, so both store email and phone the same way. The phone is
        # already cleaned by its own field, which full_clean runs first.
        super().clean()
        # A blank form field sends "", which becomes NULL: many people without an email or a phone
        # must not clash on `unique` (see the fields above).
        self.email = (self.email or "").strip().lower() or None
        self.phone = self.phone or None


class StaffStatus(models.TextChoices):
    # 02 §5: active ⇄ suspended → left. Outside StaffMember so that its Meta can read the values.
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    LEFT = "left", "Left"


class StaffMember(ShopScoped):
    # A person's job at one shop (02 §5, D12). ShopScoped (CORE-2) gives `id`, `shop`, `created_at`,
    # `created_by` and the guard on reads.

    # PROTECT: nothing is deleted (rule 7). related_name="+": no `user.staffmember_set`; a person's
    # jobs are read through StaffMember.objects, which shows only the current shop's. Django's own index
    # on `user` stays, unlike `created_by`'s: finding a person's jobs (at login, AUTH-3 and AUTH-4)
    # starts from the person, not from a shop.
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    # What the shop calls them, on the login screen and receipts: "Asha".
    display_name = models.CharField(max_length=40)
    # The owner's own words ("Muuzaji"). What they may do comes from roles (PPL-3), not from this.
    job_title = models.CharField(max_length=60, blank=True)
    # Shop dates (02 §1), not UTC times.
    started_on = models.DateField()
    left_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=StaffStatus, default=StaffStatus.ACTIVE)
    # The PIN's Argon2 hash, never the PIN; "" = no PIN yet. editable=False: no form shows it,
    # only set_pin writes it, and it never leaves the server (03 §5.9).
    pin_hash = models.CharField(max_length=128, blank=True, default="", editable=False)
    # Devices compare this with their own copy and drop an old offline PIN check (03 §5.9).
    pin_changed_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta(ShopScoped.Meta):
        # Builds on ShopScoped.Meta, so `objects`, with the guard, stays the default manager (CORE-2).
        # The database is the last guard (03 §5.6); the services check the same rules first (full_clean),
        # so a person gets a code, not a database error (ADR-0032).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=StaffStatus.values),
                name="people_staffmember_status_known",
                violation_error_code="staff.status_unknown",
            ),
            # A leaving date exactly when the person has left: never on a current job, never missing on a past one.
            models.CheckConstraint(
                condition=models.Q(status=StaffStatus.LEFT, left_on__isnull=False)
                | (~models.Q(status=StaffStatus.LEFT) & models.Q(left_on__isnull=True)),
                name="people_staffmember_left_on_when_left",
                violation_error_code="staff.left_on_mismatch",
            ),
            models.CheckConstraint(
                condition=models.Q(left_on__isnull=True) | models.Q(left_on__gte=models.F("started_on")),
                name="people_staffmember_left_after_start",
                violation_error_code="staff.left_before_start",
            ),
            models.CheckConstraint(
                condition=~models.Q(display_name=""),
                name="people_staffmember_display_name_not_blank",
                violation_error_code="staff.display_name_blank",
            ),
            # set_pin writes the hash and its time together: a PIN with no time would never reach the
            # devices' "PIN changed" check.
            models.CheckConstraint(
                condition=(models.Q(pin_hash="") & models.Q(pin_changed_at__isnull=True))
                | (~models.Q(pin_hash="") & models.Q(pin_changed_at__isnull=False)),
                name="people_staffmember_pin_hash_with_time",
                violation_error_code="staff.pin_without_time",
            ),
            # One current job per person per shop. Rows of people who left don't count, so a worker who
            # comes back gets a new row and the old one keeps its history. Leads with `shop`, as every
            # index does.
            models.UniqueConstraint(
                fields=["shop", "user"],
                condition=~models.Q(status=StaffStatus.LEFT),
                name="people_staffmember_one_current_job",
                violation_error_code="staff.already_member",
            ),
            # The login screen and receipts name staff by nickname: unique among current staff of a
            # shop, in any letter case.
            models.UniqueConstraint(
                "shop",
                Lower("display_name"),
                condition=~models.Q(status=StaffStatus.LEFT),
                name="people_staffmember_nickname_unique",
                violation_error_code="staff.display_name_taken",
            ),
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def staff_id(self) -> uuid.UUID:
        # As an Actor (apps/core/tenancy.py), the one a login names: a staff member acts as itself, so it is
        # the one recorded as who made or changed a row.
        return self.pk

    def clean(self) -> None:
        # full_clean runs this before the rules above: " Asha " and "Asha" are one nickname on screen.
        super().clean()
        self.display_name = (self.display_name or "").strip()
