"""apps/people/admin.py — the Django admin page for people: the creator's back room.

Only the superuser opens it, to see and fix people before any office screen exists; the owner adds staff
from the app's own staff screen (PPL-4), not here. It owns the add and edit forms for a User and the
page's two rules: the id is shown but never typed in, and nobody is deleted.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.http import HttpRequest

from apps.people.models import User


class UserAddForm(AdminUserCreationForm[User]):
    # Django's add form, with our fields instead of `username`. Its "password-based authentication"
    # switch lets the superuser add a worker with no password at all (02 §5).
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("full_name", "phone", "email", "language")


class UserEditForm(UserChangeForm[User]):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin[User]):
    add_form = UserAddForm
    form = UserEditForm
    # Django's own UserAdmin names `username`, `first_name` and `last_name`, which our User doesn't have.
    list_display = ("full_name", "phone", "email", "is_active", "is_superuser")
    list_filter = ("is_active", "is_superuser", "language")
    search_fields = ("full_name", "phone", "email")
    ordering = ("full_name",)
    # `id` is shown but can't be typed in. It stays editable in the model, so DRF keeps the id a device
    # sends (ADR-0007, CORE-1); changed here, it would save a copy of the person instead.
    readonly_fields = ("id", "created_at", "last_login")
    fieldsets = (
        (None, {"fields": ("id", "full_name", "phone", "email", "language", "password")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
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
