"""apps/people/models.py — the people tables. For now one: User, a human across every shop (02 §5).

A User is the person, not the job: the same person can work at MPC and in the demo shop, and their job
at each shop (StaffMember, PPL-2) holds the nickname, the PIN and the roles. So User keeps only what
belongs to the person. It is global, one of the few tables without a `shop` (ADR-0022).
This table is the project's first migration on purpose: Django fixes its user table at the first
`migrate` and can't swap it afterwards (ADR-0012, 04 BP5).
"""

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import TimeStamped, UUIDModel
from apps.core.phones import normalise_phone


# Outside User so that User.Meta can read its values: a nested class can't see the names of the class
# around it. One list, used by the field and by the database rule below.
class Language(models.TextChoices):
    SWAHILI = "sw", "Kiswahili"
    ENGLISH = "en", "English"


class UserManager(BaseUserManager["User"]):
    # Also written into the migrations, so a future data migration can call create_user.
    use_in_migrations = True

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
        # The same rules as the admin's form, before anything is written: clean() above, every field,
        # `unique` and the database rules. A broken rule is a ValidationError naming the field.
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
    # Stored in E.164 (`+255712345678`, apps/core/phones.py), which is at most 16 characters.
    phone = models.CharField(max_length=16, unique=True, null=True, blank=True)
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
        # (full_clean), so a person gets a clear message instead of a database error.
        constraints = [
            # Emails are stored in lower case, so `unique` on email is unique whatever the letter case.
            models.CheckConstraint(condition=models.Q(email=Lower("email")), name="people_user_email_lower_case"),
            # A missing email is NULL, never "": two "" would clash on `unique`.
            models.CheckConstraint(condition=~models.Q(email=""), name="people_user_email_not_blank"),
            # Only the normalised form: +, a country code that never starts with 0, 7 to 15 digits in all.
            models.CheckConstraint(
                condition=models.Q(phone__regex=r"^\+[1-9][0-9]{6,14}$"), name="people_user_phone_e164"
            ),
            models.CheckConstraint(condition=models.Q(language__in=Language.values), name="people_user_language_known"),
            # The superuser logs in to the admin by email, so one without an email could never log in.
            models.CheckConstraint(
                condition=models.Q(is_superuser=False) | models.Q(email__isnull=False),
                name="people_user_superuser_has_email",
            ),
        ]

    def __str__(self) -> str:
        # The admin shows people by name. Django's default is the login name, and most workers have no email.
        return self.full_name

    def clean(self) -> None:
        # One door for every new or changed person: the admin's form and create_user both run this
        # (through full_clean) before saving, so both store email and phone the same way.
        super().clean()
        # A blank form field sends "", which becomes NULL: many people without an email or a phone
        # must not clash on `unique` (see the fields above).
        self.email = (self.email or "").strip().lower() or None
        phone = (self.phone or "").strip()
        if not phone:
            self.phone = None
            return
        try:
            self.phone = normalise_phone(phone)
        except ValidationError as error:
            # Named after the field, so the admin shows the message next to the phone box.
            raise ValidationError({"phone": error}) from None
