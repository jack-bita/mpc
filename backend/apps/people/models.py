"""apps/people/models.py — the people tables: User, a human across every shop; StaffMember, their job at one
shop; and what each job may do there: the shop's own roles (Role), the roles a person holds on each side
(RoleAssignment), and the extra permissions one person holds (PermissionGrant) (02 §5). And the shop's devices:
Device, a laptop or phone a manager has paired with the shop, and PairingRequest, a device still waiting for a
manager's yes, which belongs to no shop yet (AUTH-1).

A User is the person, not the job: the same person can work at MPC and in its practice shop, and their
job at each shop (StaffMember) holds the nickname, the status and the PIN, and its roles hang from it.
So User keeps only what belongs to the person. It is global, one of the few tables without a `shop`
(ADR-0022). User is the project's first migration on purpose: Django fixes its user table at the first
`migrate` and can't swap it afterwards (ADR-0012, 04 BP5).
"""

import uuid
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.functions import Lower

from apps.core.fields import PhoneField
from apps.core.languages import Language
from apps.core.models import Editable, ShopScoped, TimeStamped, UUIDModel
from apps.core.permissions import PERMISSION_CODE_MAX_LENGTH, HeldPermissions, Permission, RoleTemplate
from apps.people.device_keys import KEY_HASH_LENGTH, KEY_HASH_SHAPE, PAIRING_CODE_ALPHABET, PAIRING_CODE_LENGTH
from apps.shops.models import Side


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

    def held_permissions(self) -> HeldPermissions:
        # As a Person (apps/core/permissions.py): the office routes ask the person a login names for their own
        # permissions, since `core` may not import `people` to read them (ADR-0035, PPL-5). The reading itself lives
        # with the other permission reads. That file imports this one for its tables, so it is imported here, when
        # first asked, not at the top: at the top, each file would wait for the other to load first, and neither
        # could.
        from apps.people.permissions import held_permissions

        return held_permissions(self)

    def clean(self) -> None:
        # full_clean runs this before the rules above: " Asha " and "Asha" are one nickname on screen.
        super().clean()
        self.display_name = (self.display_name or "").strip()


class Role(Editable):
    # A named bundle of permissions, the shop's own (02 §5): MPC's Manager, which MPC's owner can change without
    # touching any other shop's. Each new shop gets one row per template (apps/core/permissions.py), copied in by
    # copy_role_templates (apps/people/services.py). Editable (CORE-6) gives `updated_at`, `updated_by` and the
    # `version` that keeps two people's edits apart, for the day the owner changes a role; the trigger in this
    # table's migration records each change, before and after (ADR-0036).

    # The template it was copied from ("manager"), or blank for a role an owner makes from nothing, later.
    template = models.CharField(max_length=20, blank=True)
    # The owner's own name for it. Blank on a copied role: the screens show the template's name in the person's
    # language, so the server makes up no words (ADR-0032).
    name = models.CharField(max_length=40, blank=True)
    # The codes the role gives (02 §5), as one PostgreSQL array: a change to the role is then one row's edit, and
    # the history keeps the whole list, before and after.
    permissions = ArrayField(models.CharField(max_length=PERMISSION_CODE_MAX_LENGTH), default=list, blank=True)

    class Meta(Editable.Meta):
        # Builds on Editable.Meta, so `objects`, with the guard, stays the default manager (CORE-2). The database
        # is the last guard (03 §5.6); full_clean checks the same rules first, so a person gets a code (ADR-0032).
        constraints = [
            # Only codes from the list: a typo would give nobody anything. The list is written into the rule, as
            # AuditAction's is, so a new code is a new line in Permission and a migration that rebuilds this rule.
            models.CheckConstraint(
                condition=models.Q(permissions__contained_by=Permission.values),
                name="people_role_permissions_known",
                violation_error_code="permission.unknown",
            ),
            models.CheckConstraint(
                condition=models.Q(template__in=["", *RoleTemplate.values]),
                name="people_role_template_known",
                violation_error_code="role.template_unknown",
            ),
            # Every role has a name to show: its template's, or the owner's own.
            models.CheckConstraint(
                condition=~models.Q(template="", name=""),
                name="people_role_named",
                violation_error_code="role.name_blank",
            ),
            # One role per template per shop: two Managers would split the shop's managers across two bundles.
            # Roles an owner makes (no template) don't count. The message is there for the code's sake, as on
            # Side's letter (apps/shops/models.py).
            models.UniqueConstraint(
                fields=["shop", "template"],
                condition=~models.Q(template=""),
                name="people_role_one_per_template",
                violation_error_code="role.template_taken",
                violation_error_message="This shop already has a role from this template.",
            ),
        ]

    def __str__(self) -> str:
        return self.name or self.template

    def clean(self) -> None:
        # full_clean runs this before the rules in Meta: " Msaidizi " and "Msaidizi" are one name on screen, as for a
        # side, and a name of only spaces becomes "", which people_role_named refuses on a role from no template.
        super().clean()
        self.name = (self.name or "").strip()


class RoleAssignment(ShopScoped):
    # One role given to one person, on one side or on all of them (02 §5): Asha is Cashier on Vyakula. Who gave it,
    # and when, are the row's `created_by` and `created_at`. Made only by assign_role (apps/people/services.py),
    # which checks that the person, the role and the side all belong to the row's shop (T1). Taking a role away
    # comes with the staff screens (PPL-4), as an edit the history records (ADR-0036): nothing is deleted.

    # PROTECT: nothing is deleted (rule 7). related_name="+": a person's roles are read through the guarded
    # `objects` (apps/people/permissions.py). db_index=False: the unique rule below indexes (shop, staff, ...),
    # and nothing is deleted, so PROTECT never has to search the role's or the side's column.
    staff = models.ForeignKey(StaffMember, on_delete=models.PROTECT, related_name="+", db_index=False)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="+", db_index=False)
    # Empty: every side of the shop, a side added later included.
    side = models.ForeignKey(Side, on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False)

    class Meta(ShopScoped.Meta):
        constraints = [
            # Given once per side: a second row would change nothing, and taking the role away would have to find
            # both. nulls_distinct=False: "all sides" (no side) counts as one value too, which PostgreSQL otherwise
            # never does with two empty values. The message is there for the code's sake, as on Role.
            models.UniqueConstraint(
                fields=["shop", "staff", "role", "side"],
                nulls_distinct=False,
                name="people_roleassignment_once",
                violation_error_code="role.already_given",
                violation_error_message="This person already has this role on this side.",
            ),
        ]


class PermissionGrant(ShopScoped):
    # One extra permission for one person, on one side or on all of them (02 §5): Juma may count the stock on
    # Vyakula. Made only by grant_permission (apps/people/services.py), with the same checks as a role is given;
    # taken back with the staff screens (PPL-4), as a role is. Links as on RoleAssignment above.
    staff = models.ForeignKey(StaffMember, on_delete=models.PROTECT, related_name="+", db_index=False)
    # A code from the list (apps/core/permissions.py).
    permission = models.CharField(max_length=PERMISSION_CODE_MAX_LENGTH)
    # Empty: every side of the shop, a side added later included.
    side = models.ForeignKey(Side, on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False)

    class Meta(ShopScoped.Meta):
        constraints = [
            # Only codes from the list, as on a role.
            models.CheckConstraint(
                condition=models.Q(permission__in=Permission.values),
                name="people_permissiongrant_permission_known",
                violation_error_code="permission.unknown",
            ),
            # Given once per side, "all sides" included, as a role is.
            models.UniqueConstraint(
                fields=["shop", "staff", "permission", "side"],
                nulls_distinct=False,
                name="people_permissiongrant_once",
                violation_error_code="permission.already_given",
                violation_error_message="This person already has this permission on this side.",
            ),
        ]


class DeviceStatus(models.TextChoices):
    # 02 §5 (v1.11): active ⇄ blocked. Never pending: a device waits in a PairingRequest until a manager says yes, and
    # is born active. Outside Device so that its Meta can read the values.
    ACTIVE = "active", "Active"
    BLOCKED = "blocked", "Blocked"


class Device(Editable):
    # A laptop or phone a manager has paired with the shop (02 §5, ADR-0018): "Laptop ya Dawa". Made only by
    # confirm_pairing (apps/people/services.py), in the confirming manager's shop. Editable (CORE-6) gives
    # `updated_at`, `updated_by` and the `version` that keeps two people's edits apart, for the day a manager renames
    # it (UI-3); the trigger in this table's migration records each change, before and after, but never the key's
    # hash (ADR-0036). Who confirmed it, and when, are the row's `created_by` and `created_at` (02 v1.11). The columns
    # each sync reports (`last_synced_at`, `unsent_count`...) come with SYNC-5, and `last_seen_at` with AUTH-2.

    # What the manager called it, on the device list: "Laptop ya Dawa".
    name = models.CharField(max_length=40)
    # Its number in the shop's receipt numbers (D7): the shop's "device" counter gives it (apps/core/sequences.py),
    # so it is never given twice, even after a block and a new pairing. editable=False: no form or API changes it.
    code = models.PositiveIntegerField(editable=False)
    # The side it mostly serves; who may pair or block it is asked on this side (device.manage). PROTECT: nothing is
    # deleted (rule 7). db_index=False: indexes lead with `shop`, and nothing is deleted, so PROTECT never searches it.
    home_side = models.ForeignKey(Side, on_delete=models.PROTECT, related_name="+", db_index=False)
    status = models.CharField(max_length=10, choices=DeviceStatus, default=DeviceStatus.ACTIVE)
    # The SHA-256 hash of its key, never the key (03 §5.9). editable=False: no form shows it, and it never leaves the
    # server. Blocking leaves it in place, so unblocking brings the same key back (Jack, AUTH-1).
    key_hash = models.CharField(max_length=KEY_HASH_LENGTH, editable=False)

    class Meta(Editable.Meta):
        # Builds on Editable.Meta, so `objects`, with the guard, stays the default manager (CORE-2). The database is
        # the last guard (03 §5.6); full_clean checks the same rules first, so a person gets a code (ADR-0032).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=DeviceStatus.values),
                name="people_device_status_known",
                violation_error_code="device.status_unknown",
            ),
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="people_device_name_not_blank",
                violation_error_code="device.name_blank",
            ),
            # Codes start at 1 (the counter's first number); 0 would mean one was never given.
            models.CheckConstraint(
                condition=models.Q(code__gte=1),
                name="people_device_code_given",
                violation_error_code="device.code_missing",
            ),
            # Only a hash's shape: a key stored by mistake, instead of its hash, is refused here.
            models.CheckConstraint(
                condition=models.Q(key_hash__regex=KEY_HASH_SHAPE),
                name="people_device_key_hashed",
                violation_error_code="device.key_not_hashed",
            ),
            # D7: one device per code in a shop, so two devices never print the same receipt numbers. The counter
            # already gives each code once; this is the database's own promise, whatever code writes the row.
            models.UniqueConstraint(
                fields=["shop", "code"],
                name="people_device_code_once",
                violation_error_code="device.code_taken",
                violation_error_message="This shop already has a device with this code.",
            ),
            # The device list names devices, so one name per shop, in any letter case, blocked ones included: a
            # replacement for a stolen "Laptop ya Dawa" gets a name of its own, and the history stays clear.
            models.UniqueConstraint(
                "shop",
                Lower("name"),
                name="people_device_name_once",
                violation_error_code="device.name_taken",
                violation_error_message="This shop already has a device with this name.",
            ),
            # One device per key, across every shop. Not led by `shop`, unlike every other index: a request that
            # brings a key names no shop yet, so AUTH-2 finds its device by the key's hash alone, in this index.
            models.UniqueConstraint(
                fields=["key_hash"],
                name="people_device_key_once",
                violation_error_code="device.key_taken",
                violation_error_message="Another device has this key.",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        # full_clean runs this before the rules above: " Laptop ya Dawa " and "Laptop ya Dawa" are one name on screen.
        super().clean()
        self.name = (self.name or "").strip()


class PairingRequest(UUIDModel, TimeStamped):
    # A new device waiting for a manager's yes (02 §5, v1.11): it asked to join (start_pairing), shows `code` on its
    # screen, and holds its key, which works once a manager confirms the code (confirm_pairing). UUIDModel and
    # TimeStamped (CORE-1) give `id` and `created_at`, when it asked.
    # No `shop`, unlike every shop's table (T1's exception, NO_SHOP in backend/tests/sweep_lists.py): until a manager
    # says yes, the device belongs to no shop, and anyone may ask. So no guard either: its default manager reads every
    # request, which is safe because a request holds nothing of any shop's until it names its device. A shop's own
    # tables only ever hold devices one of its managers confirmed.

    # Every code ever given stays taken (unique, below), so a code can only ever mean one request: start_pairing draws
    # again on a clash. With about 850 billion codes, that is rare.
    code = models.CharField(max_length=PAIRING_CODE_LENGTH)
    # created_at + 10 minutes (PAIRING_CODE_LIFETIME): a manager's confirm after this is refused.
    expires_at = models.DateTimeField()
    # The SHA-256 hash of the key the device was given when it asked, never the key. confirm_pairing copies it onto
    # the Device, which switches the key on (Jack, AUTH-1).
    key_hash = models.CharField(max_length=KEY_HASH_LENGTH, editable=False)
    # The device it became, once confirmed; empty while it waits. One request per device (OneToOne). PROTECT: nothing
    # is deleted (rule 7). related_name="+": a device's request is read from here, not from the device.
    device = models.OneToOneField(Device, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    # When a manager confirmed it. Who did is the device's `created_by`.
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # Not built on ShopScoped.Meta: this table has no shop, so it has no guard to keep.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(code__regex=rf"^[{PAIRING_CODE_ALPHABET}]{{{PAIRING_CODE_LENGTH}}}$"),
                name="people_pairingrequest_code_shape",
                violation_error_code="pairing.code_invalid",
            ),
            models.CheckConstraint(
                condition=models.Q(key_hash__regex=KEY_HASH_SHAPE),
                name="people_pairingrequest_key_hashed",
                violation_error_code="pairing.key_not_hashed",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="people_pairingrequest_expires_after_asked",
                violation_error_code="pairing.expires_before_asked",
            ),
            # Confirmed means both at once: the device it became, and when.
            models.CheckConstraint(
                condition=models.Q(device__isnull=True, confirmed_at__isnull=True)
                | models.Q(device__isnull=False, confirmed_at__isnull=False),
                name="people_pairingrequest_confirmed_whole",
                violation_error_code="pairing.confirmed_half",
            ),
            models.UniqueConstraint(
                fields=["code"],
                name="people_pairingrequest_code_once",
                violation_error_code="pairing.code_taken",
                violation_error_message="This pairing code was already given.",
            ),
            # A key belongs to one request, as it belongs to one device.
            models.UniqueConstraint(
                fields=["key_hash"],
                name="people_pairingrequest_key_once",
                violation_error_code="pairing.key_taken",
                violation_error_message="Another pairing request has this key.",
            ),
        ]

    def __str__(self) -> str:
        return self.code
