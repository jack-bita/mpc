"""apps/people/tests/test_own_settings.py — a person changes their own language and font (UI-9, ADR-0039; 03 §7.4).

`PATCH /api/auth/me/settings/` changes the logged-in person's own two choices, and nobody else's:

    the session                                   the answer
    a PIN's badge, or a password                  200: their language and font, as now saved
    an unknown language or font                   400, under the field, nothing saved
    a suspended person, a temporary password      403, each with its code, nothing saved
    nobody, or the superuser (nobody's staff)     403 not_authenticated
    no CSRF token                                 403, nothing saved

It takes no key: everyone may change their own choices. It isn't an office route for that reason, as an office route
asks every change for a key of its own (PPL-5), so the tenancy sweep doesn't call it (NOT_SHOP_ROUTES,
backend/tests/sweep_lists.py). Its answer holds only the person's two choices, which this file proves instead. Fake
data only: the repo is public (03 §10).
"""

from collections.abc import Callable

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import change_own_settings, confirm_pairing, set_pin, start_pairing, suspend
from apps.shops.models import Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The routes and the cookie's name, written out: they are a promise to the app (test_me.py says why).
SETTINGS = "/api/auth/me/settings/"
ME = "/api/auth/me/"
PIN_LOGIN = "/api/auth/pin-login/"
KEY_COOKIE = "device_key"

PIN = "4829"


def on_a_phone(staff: StaffMember, *, csrf: bool = False) -> APIClient:
    # A real Django session for this person, as a password's login leaves, so the route's own login checks it on every
    # visit (StaffSessionAuthentication): not force_authenticate, which would skip the very checks tested here.
    # `csrf`: check the token, as a real browser's visit is checked.
    client = APIClient(enforce_csrf_checks=csrf)
    client.force_login(User.objects.get(pk=staff.user_id))
    return client


def row(staff: StaffMember) -> User:
    # The person as the database keeps them now.
    return User.objects.get(pk=staff.user_id)


@pytest.fixture
def juma(staff_a2: StaffMember) -> StaffMember:
    # A second person at the same shop: what Asha does must never change his row.
    return staff_a2


def test_person_changes_own_language_and_font(staff_a: StaffMember, juma: StaffMember) -> None:
    # Asha reads English, in the font that is easier to read.
    answer = on_a_phone(staff_a).patch(SETTINGS, {"language": "en", "font": "second"}, format="json")

    assert (answer.status_code, answer.data) == (200, {"language": "en", "font": "second"})
    assert (row(staff_a).language, row(staff_a).font) == ("en", "second")
    # Juma, at the same shop, keeps his.
    assert (row(juma).language, row(juma).font) == ("sw", "default")


def test_me_answers_the_persons_choices(staff_a: StaffMember) -> None:
    # The app asks `me` after every login: that is how her choices reach any device she logs in at (UI-9).
    phone = on_a_phone(staff_a)
    phone.patch(SETTINGS, {"font": "second"}, format="json")

    person = phone.get(ME).data["user"]
    assert (person["language"], person["font"]) == ("sw", "second")


def test_settings_change_one_at_a_time(staff_a: StaffMember) -> None:
    # The screen sends only the choice just tapped: the other stays as it was.
    phone = on_a_phone(staff_a)
    phone.patch(SETTINGS, {"language": "en"}, format="json")
    answer = phone.patch(SETTINGS, {"font": "second"}, format="json")

    assert answer.data == {"language": "en", "font": "second"}


def test_settings_with_nothing_sent_change_nothing(staff_a: StaffMember) -> None:
    # Nothing to save, and no refusal either: the answer says what is saved now.
    answer = on_a_phone(staff_a).patch(SETTINGS, {}, format="json")

    assert (answer.status_code, answer.data) == (200, {"language": "sw", "font": "default"})


def test_settings_change_only_your_own(staff_a: StaffMember, juma: StaffMember) -> None:
    # The route names no person: it changes whoever is logged in. Asha sending Juma's id, or a field that isn't one of
    # the two choices, changes nothing of his, and nothing else of hers.
    sent = {"id": str(juma.user_id), "user": str(juma.user_id), "full_name": "Juma Mpya", "font": "second"}
    answer = on_a_phone(staff_a).patch(SETTINGS, sent, format="json")

    assert answer.status_code == 200
    assert row(juma).font == "default"
    assert row(juma).full_name == "Staff Demo Two"
    assert (row(staff_a).font, row(staff_a).full_name) == ("second", "Staff Demo")


def test_settings_answer_holds_nothing_of_a_shop(staff_a: StaffMember) -> None:
    # Why the sweep may leave this route out (NOT_SHOP_ROUTES): its answer is the person's two choices, and nothing
    # else, of any shop's or of the person's.
    answer = on_a_phone(staff_a).patch(SETTINGS, {"language": "en"}, format="json")
    assert set(answer.data) == {"language", "font"}


@pytest.mark.parametrize("sent", [{"font": "atkinson"}, {"language": "fr"}, {"font": None}])
def test_settings_refuse_an_unknown_choice(staff_a: StaffMember, sent: dict[str, object]) -> None:
    # Only a role's value is stored, never a font's name (ADR-0039), and only a language the app has words for.
    answer = on_a_phone(staff_a).patch(SETTINGS, sent, format="json")

    assert (answer.status_code, answer.data["code"]) == (400, "invalid")
    assert list(answer.data["fields"]) == list(sent)
    assert (row(staff_a).language, row(staff_a).font) == ("sw", "default")


def test_the_service_refuses_an_unknown_font_too(staff_a: StaffMember) -> None:
    # The route's form checks first, but the service keeps the rule itself, for whatever calls it next (ADR-0015).
    with pytest.raises(ValidationError) as refused:
        change_own_settings(row(staff_a), font="atkinson")

    assert [error.code for error in refused.value.error_dict["font"]] == ["invalid_choice"]
    assert row(staff_a).font == "default"


def test_suspended_person_cannot_change_settings(staff_a: StaffMember) -> None:
    # A suspension takes effect at the person's very next visit, whatever session they hold (ADR-0038): the login every
    # office route shares refuses her here too.
    phone = on_a_phone(staff_a)
    with shop_context(staff_a.shop_id):
        suspend(staff_a, by=None, reason="Amekosa kazi siku tatu")

    answer = phone.patch(SETTINGS, {"font": "second"}, format="json")

    assert (answer.status_code, answer.data["code"]) == (403, "staff.suspended")
    assert row(staff_a).font == "default"


def test_settings_refuse_a_temporary_password(staff_a: StaffMember) -> None:
    # Someone else knows her password (ADR-0038): until she chooses her own, the office stays closed but for `me`, and
    # Chagua nenosiri lako stands in place of every screen, this one's too.
    User.objects.filter(pk=staff_a.user_id).update(must_change_password=True)

    answer = on_a_phone(staff_a).patch(SETTINGS, {"font": "second"}, format="json")

    assert (answer.status_code, answer.data["code"]) == (403, "password.must_change")
    assert row(staff_a).font == "default"


def test_settings_need_a_login(superuser_client: Client) -> None:
    # Nobody at all; and the superuser, who is nobody's staff, so has no screen to change choices on.
    answer = APIClient().patch(SETTINGS, {"font": "second"}, format="json")
    assert (answer.status_code, answer.data["code"]) == (403, "not_authenticated")

    admin = superuser_client.patch(SETTINGS, {"font": "second"}, content_type="application/json")
    assert admin.status_code == 403
    assert User.objects.get(email="admin@example.com").font == "default"


def test_settings_check_csrf(staff_a: StaffMember) -> None:
    # Without the token, another website Asha visits could change her language behind her back.
    answer = on_a_phone(staff_a, csrf=True).patch(SETTINGS, {"language": "en"}, format="json")

    assert (answer.status_code, answer.data["code"]) == (403, "permission_denied")
    assert row(staff_a).language == "sw"


@pytest.fixture
def laptop_key(staff_a2: StaffMember, side_a: Side, give_role: GiveRole) -> str:
    # A device paired the way the app pairs one: it asks and keeps its key, and a manager confirms its code.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    asked = start_pairing()
    with shop_context(staff_a2.shop_id):
        device: Device = confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=side_a, by=staff_a2)
    assert device.pk
    return asked.key


def test_a_pin_session_changes_its_own_settings(staff_a: StaffMember, laptop_key: str) -> None:
    # Asha at the counter laptop, logged in by her PIN: the way most of the shop logs in.
    with shop_context(staff_a.shop_id):
        set_pin(staff_a, PIN, by=None)
    laptop = APIClient()
    laptop.cookies[KEY_COOKIE] = laptop_key
    assert laptop.post(PIN_LOGIN, {"staff": str(staff_a.pk), "pin": PIN}, format="json").status_code == 204

    answer = laptop.patch(SETTINGS, {"font": "second"}, format="json")

    assert (answer.status_code, answer.data) == (200, {"language": "sw", "font": "second"})


def test_a_choice_follows_the_person_to_another_device(staff_a: StaffMember, laptop_key: str) -> None:
    # The card's first case, on the server: Asha picks the second font on her phone, then logs in by PIN at the
    # counter laptop, another browser with a session of its own. The laptop learns her choice from `me` there, as it is
    # saved on her, not on the phone (UI-9).
    on_a_phone(staff_a).patch(SETTINGS, {"language": "en", "font": "second"}, format="json")
    with shop_context(staff_a.shop_id):
        set_pin(staff_a, PIN, by=None)
    laptop = APIClient()
    laptop.cookies[KEY_COOKIE] = laptop_key
    assert laptop.post(PIN_LOGIN, {"staff": str(staff_a.pk), "pin": PIN}, format="json").status_code == 204

    person = laptop.get(ME).data["user"]

    assert (person["language"], person["font"]) == ("en", "second")


def test_settings_describe_nothing_to_options(staff_a: StaffMember) -> None:
    # OPTIONS would describe the route's form to anyone who asks; the office routes refuse it on purpose, as the API's
    # own description is the schema (apps/core/api/base.py). This route refuses it too.
    assert on_a_phone(staff_a).options(SETTINGS).status_code == 405
