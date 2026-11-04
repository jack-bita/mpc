"""apps/people/admin.py — the Django admin page for people: the creator's back room.

Only the superuser opens it, to see and fix people before any office screen exists; the owner adds staff
from the app's own staff screen (PPL-4), not here. It owns the add and edit forms for a User and the
page's three rules: the id is shown but never typed in, nobody is deleted, and a password typed here is temporary
(ADR-0038). A reset here is kept in Django's own admin log, with who and when, and not in the shop's audit trail: a
person belongs to no one shop, and this page reads none. And a PIN's badge never opens the site (AUTH-4).
"""

from typing import Any, cast

from allauth.account.models import EmailAddress
from django.contrib import admin
from django.contrib.admin.forms import AdminPasswordChangeForm as OwnPasswordForm
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, AdminUserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from django.forms import CharField
from django.http import HttpRequest, HttpResponse
from django.views.decorators.debug import sensitive_variables

from apps.people.api.pin_session import PIN_SESSION
from apps.people.login_counts import lift_wrong_password_count
from apps.people.models import User

# allauth puts its own table of addresses on this site, and its login and reset trust that table. A row typed there
# would be a login name for a person, set past the phone cleaner and the audit trail (PPL-2). Our User holds the email,
# and the table stays empty (ACCOUNT_PASSWORD_RESET_TOKEN_GENERATOR, config/settings/base.py). allauth comes first in
# INSTALLED_APPS, so it has registered by now; if that order ever changes, this line stops the start-up, loudly.
admin.site.unregister(EmailAddress)

_admin_lets_in = admin.site.has_permission
_admin_login = admin.site.login


def _not_by_pin(request: HttpRequest) -> bool:
    # A PIN's badge never opens this site, whoever's it is. The site reads every shop's rows (ADR-0037), and a badge is
    # 4 digits typed at a shared counter; and what each visit asks of a badge (job_of_pin_session,
    # apps/people/selectors.py) is asked by the office routes' login, never here, so a copied badge, a suspended person
    # or a blocked device would still get in. Someone who may open the site logs in here with their password.
    return PIN_SESSION not in request.session and _admin_lets_in(request)


def _login_starts_clean(request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
    # Django's login keeps a session's data when it is the same person, so a password typed here over a badge would keep
    # the badge's mark, and this site would send them back to this page for good. So the badge goes first. A wrong
    # password then costs that badge too, which logging out costs anyway; the CSRF check has already passed by here.
    if request.method == "POST" and PIN_SESSION in request.session:
        request.session.flush()
    return _admin_login(request, extra_context)


# Set on Django's one site, as its password form is below, rather than replacing the whole site. mypy refuses a method
# replaced this way; it is what lets this file stay the only place that changes the site.
admin.site.has_permission = _not_by_pin  # type: ignore[method-assign]
admin.site.login = _login_starts_clean  # type: ignore[method-assign]


def _take_off_spaces(cleaned_data: dict[str, Any], *fields: str) -> None:
    # Django's admin forms keep the spaces around a password, and allauth's login takes them off what is typed, so a
    # password stored with them could never log in. Taken off first, so Django's checks judge what will be stored:
    # twelve spaces leave nothing, which SetUnusablePasswordMixin, the parent of the forms that call this, refuses as
    # required.
    for field in fields:
        if cleaned_data.get(field):
            cleaned_data[field] = cleaned_data[field].strip()


class PasswordTypedHereIsTemporary:
    # The superuser knows any password typed for someone else here: a new owner's first one, or the owner's forgotten
    # one, which nobody at the shop may reset (ADR-0038). So the person must choose their own at the next login, as with
    # a temporary one the owner sets (set_temporary_password, apps/people/services.py). The add form, and the password
    # page reached from a person's row, both save through this method, on Django's own, in the classes below. Every
    # variable in these methods, and in what they call down to any narrower rule of Django's own, shows as stars in
    # Django's error reports, as the library at the bottom of the hash names the password `secret`.
    cleaned_data: dict[str, Any]

    @sensitive_variables()
    def clean(self) -> dict[str, Any]:
        _take_off_spaces(self.cleaned_data, "password1", "password2")
        # mypy reads this class alone, with no parent to call: the forms below give it one.
        cleaned: dict[str, Any] = super().clean()  # type: ignore[misc]
        return cleaned

    @sensitive_variables()
    def set_password_and_save(self, user: User, commit: bool = True, **kwargs: Any) -> User:
        # Django's switch: "Disabled" means no password at all, so nothing is left to replace, and the mark would say
        # otherwise. On the row before Django's one save, so the password and the mark are written together.
        user.must_change_password = self.cleaned_data["set_usable_password"]
        # As in clean above, for mypy.
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


class ChooseOwnPasswordForm(OwnPasswordForm):
    # Django's own page where someone who can open the admin changes their own password (/admin/password_change/). The
    # one password form here that is not typed for someone else, so it follows the rules of choosing one's own, as
    # allauth's change route does (AccountAdapter, apps/people/accounts.py): never the temporary one, and the mark comes
    # off. Its variables are hidden from error reports, as above.
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Spaces off by the field itself, before its own "required" check, not afterwards as _take_off_spaces does for
        # the other forms: this form's parent has no second check for an empty password, so spaces alone would store the
        # hash of nothing, and lock the person out with the page saying it worked.
        for field in ("new_password1", "new_password2"):
            cast(CharField, self.fields[field]).strip = True

    @sensitive_variables()
    def clean_old_password(self) -> str:
        # Written out, with no call to Django's own, which hides only the name `old_password`: the nearest rule wins, so
        # the frames below it would show this same password as `raw_password`, and at the bottom of the hash as
        # `secret`. For someone with the mark on, this is the temporary one.
        old_password: str = self.cleaned_data["old_password"]
        if not self.user.check_password(old_password):
            raise ValidationError(self.error_messages["password_incorrect"], code="password_incorrect")
        return old_password

    @sensitive_variables()
    def clean(self) -> dict[str, Any] | None:
        cleaned = super().clean()
        new_password = self.cleaned_data.get("new_password1")
        if new_password and self.user.must_change_password and self.user.check_password(new_password):
            refused = ValidationError(
                "Choose a password other than the temporary one.", code="password.same_as_temporary"
            )
            self.add_error("new_password1", refused)
        return cleaned

    @sensitive_variables()
    def save(self, commit: bool = True) -> User:
        # The mark comes off in one save with the new password: never one without the other. These two columns alone,
        # not Django's save of the whole row: this copy was read when the visit began, so saving all of it could undo
        # what happened since, such as someone taking the admin away from this person.
        saved: User = self.user
        saved.set_password(self.cleaned_data["new_password1"])
        saved.must_change_password = False
        if commit:
            saved.save(update_fields=["password", "must_change_password"])
        lift_wrong_password_count(saved)
        return saved


admin.site.password_change_form = ChooseOwnPasswordForm


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
