"""apps/people/admin.py — the Django admin page for people: the creator's back room.

Only the superuser opens it, to see and fix people before any office screen exists; the owner adds staff
from the app's own staff screen (PPL-4), not here. It owns the add and edit forms for a User and the
page's three rules: the id is shown but never typed in, nobody is deleted, and a password typed here is temporary
(ADR-0038). A reset here is kept in Django's own admin log, with who and when, and not in the shop's audit trail: a
person belongs to no one shop, and this page reads none.
"""

from typing import Any

from allauth.account.models import EmailAddress
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, AdminUserCreationForm, UserChangeForm
from django.http import HttpRequest

from apps.people.accounts import lift_wrong_password_count
from apps.people.models import User

# allauth puts its own table of addresses on this site, and its login and reset trust that table. A row typed there
# would be a login name for a person, set past the phone cleaner and the audit trail (PPL-2). Our User holds the email,
# and the table stays empty (ACCOUNT_PASSWORD_RESET_TOKEN_GENERATOR, config/settings/base.py). allauth comes first in
# INSTALLED_APPS, so it has registered by now; if that order ever changes, this line stops the start-up, loudly.
admin.site.unregister(EmailAddress)


class PasswordTypedHereIsTemporary:
    # The superuser knows any password typed here: a new owner's first one, or the owner's forgotten one, which nobody
    # at the shop may reset (ADR-0038). So the person must choose their own at the next login, as with a temporary one
    # the owner sets (set_temporary_password, apps/people/services.py). Both of the admin's password forms save through
    # this method, on Django's own, in the classes below.
    cleaned_data: dict[str, Any]

    def clean(self) -> dict[str, Any]:
        # Django's admin forms keep the spaces around a password, and allauth's login takes them off what is typed, so a
        # password stored with them could never log in. Taken off first, so Django's checks judge what will be stored:
        # twelve spaces leave nothing, which it refuses as required. mypy reads this class alone, as below.
        for field in ("password1", "password2"):
            if self.cleaned_data.get(field):
                self.cleaned_data[field] = self.cleaned_data[field].strip()
        cleaned: dict[str, Any] = super().clean()  # type: ignore[misc]
        return cleaned

    def set_password_and_save(self, user: User, commit: bool = True, **kwargs: Any) -> User:
        # Django's switch: "Disabled" means no password at all, so nothing is left to replace, and the mark would say
        # otherwise. On the row before Django's one save, so the password and the mark are written together.
        user.must_change_password = self.cleaned_data["set_usable_password"]
        # mypy reads this class alone, with no parent to call: the forms below give it one.
        saved: User = super().set_password_and_save(user, commit=commit, **kwargs)  # type: ignore[misc]
        # They came because they kept typing it wrong: the new one must work at once, not after 5 minutes.
        lift_wrong_password_count(saved)
        return saved


class UserAddForm(PasswordTypedHereIsTemporary, AdminUserCreationForm[User]):
    # Django's add form, with our fields instead of `username`. Its "password-based authentication"
    # switch lets the superuser add a worker with no password at all (02 §5).
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("full_name", "phone", "email", "language")


class TemporaryPasswordForm(PasswordTypedHereIsTemporary, AdminPasswordChangeForm[User]):
    # Django's own form for a person's password, on its own page, reached from the person's page.
    pass


class UserEditForm(UserChangeForm[User]):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin[User]):
    add_form = UserAddForm
    form = UserEditForm
    change_password_form = TemporaryPasswordForm
    # Django's own UserAdmin names `username`, `first_name` and `last_name`, which our User doesn't have.
    list_display = ("full_name", "phone", "email", "is_active", "is_superuser")
    list_filter = ("is_active", "is_superuser", "language")
    search_fields = ("full_name", "phone", "email")
    ordering = ("full_name",)
    # `id` is shown but can't be typed in. It stays editable in the model, so DRF keeps the id a device
    # sends (ADR-0007, CORE-1); changed here, it would save a copy of the person instead. The mark is shown, so the
    # superuser sees whether a person has chosen their own password yet, but only choosing one takes it off (ADR-0038).
    readonly_fields = ("id", "created_at", "last_login", "must_change_password")
    fieldsets = (
        (None, {"fields": ("id", "full_name", "phone", "email", "language", "password")}),
        (
            "Access",
            {"fields": ("is_active", "must_change_password", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("created_at", "last_login")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("full_name", "phone", "email", "language", "usable_password", "password1", "password2"),
            },
        ),
    )

    def has_delete_permission(self, request: HttpRequest, obj: User | None = None) -> bool:
        # Nothing is deleted: a person who must not log in is switched off (`is_active`), and their name
        # stays on everything they did.
        return False
