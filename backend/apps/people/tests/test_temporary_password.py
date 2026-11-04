"""apps/people/tests/test_temporary_password.py — a first or forgotten password, set face to face (AUTH-6; 02 §5;
ADR-0038). The service, set_temporary_password (apps/people/services.py); its route is in
test_temporary_password_route.py.

Asha forgot her password. Baba types a temporary one and tells it to her. She logs in with it, and every office route
refuses her until she chooses her own (test_password_change.py). The audit trail keeps who did it and why, never the
password.

Whoever sets a person's password can log in as them, so who may is the giver rule (02 §5) applied to the whole person:

    who sets it                      for whom                               answer
    Baba, the owner                  Asha, a seller                         yes
    Meneja, handed staff.manage      Asha                                   yes
    Meneja, no staff.manage          Asha                                   refused: no key
    Meneja, staff.manage on Dawa     Asha                                   refused: not on the whole shop
    Meneja, handed staff.manage      someone holding a key he lacks         refused: password.more_keys
    anyone at the shop               an owner, suspended or not             refused: password.superuser_only
    anyone at the shop               someone with a job at another shop     refused: password.superuser_only
    anyone at the shop               someone who can open the admin         refused: password.superuser_only
    anyone                           themselves                             refused: password.own

Fake data only: the repo is public (03 §10).
"""

import json
import logging
from collections.abc import Callable
from typing import Any
from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.views.debug import ExceptionReporter

from apps.control.models import AuditAction, AuditEvent
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.services import (
    add_staff,
    grant_permission,
    mark_left,
    set_temporary_password,
    suspend,
)
from apps.shops.models import Shop, Side
from apps.shops.services import add_side

pytestmark = pytest.mark.django_db

LOGIN = "/_allauth/browser/v1/auth/login"
SESSION = "/_allauth/browser/v1/auth/session"

PHONE = "+255712345678"
EMAIL = "asha@example.com"
OLD = "mbegu-za-mahindi-2026"
TEMPORARY = "mbolea-ya-kupandia-2027"

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


def job(shop: Shop, name: str, *, phone: str | None = None, email: str | None = None) -> StaffMember:
    # A person with a job at this shop, and a password of their own.
    user = User.objects.create_user(full_name=f"{name} Mfano", phone=phone, email=email, password=OLD)
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, by=None)


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    staff = job(shop_a, "Baba", phone="+255712345670")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def meneja(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A manager the owner has handed staff.manage, on the whole shop.
    staff = job(shop_a, "Meneja", phone="+255712345671")
    give_role(staff, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(staff, Permission.STAFF_MANAGE, side=None, by=None)
    return staff


@pytest.fixture
def asha(shop_a: Shop, side_a: Side, give_role: GiveRole) -> StaffMember:
    staff = job(shop_a, "Asha", phone=PHONE, email=EMAIL)
    give_role(staff, RoleTemplate.SELLER, side_a)
    return staff


def set_for(staff: StaffMember, *, by: StaffMember, password: str = TEMPORARY, reason: str = "Amesahau") -> None:
    with shop_context(staff.shop_id):
        set_temporary_password(staff, password, by=by, reason=reason)


def refusal(staff: StaffMember, *, by: StaffMember) -> str:
    with pytest.raises(ValidationError) as refused:
        set_for(staff, by=by)
    assert_unchanged(staff)
    return str(refused.value.code)


def assert_unchanged(staff: StaffMember) -> None:
    # A refused try leaves the person exactly as they were, and no line in the audit trail.
    user = User.objects.get(pk=staff.user_id)
    assert user.check_password(OLD)
    assert user.must_change_password is False
    with shop_context(staff.shop_id):
        assert not AuditEvent.objects.filter(action=AuditAction.STAFF_TEMPORARY_PASSWORD).exists()


def log_in(**sent: str) -> tuple[int, list[str]]:
    answer = Client().post(LOGIN, sent, content_type="application/json")
    return answer.status_code, [error["code"] for error in answer.json().get("errors", [])]


def audit_trail_down() -> Any:
    # The line can't be written: something fails right after the password is saved, inside the transaction.
    return mock.patch("apps.people.services.audit", side_effect=RuntimeError("the trail is down"))


def test_owner_sets_temporary_password(baba: StaffMember, asha: StaffMember) -> None:
    set_for(asha, by=baba)

    # It logs her in, her old one no longer does, and the mark is on: the office routes refuse her until she chooses.
    assert log_in(phone=PHONE, password=TEMPORARY)[0] == 200
    assert log_in(phone=PHONE, password=OLD)[0] == 400
    assert User.objects.get(pk=asha.user_id).must_change_password is True


def test_a_person_with_only_a_phone_gets_one_too(
    shop_a: Shop, side_a: Side, baba: StaffMember, give_role: GiveRole
) -> None:
    # Most of the shop's people: no email at all, which is why this exists (ADR-0038).
    juma = job(shop_a, "Juma", phone="+255712345674")
    give_role(juma, RoleTemplate.SELLER, side_a)
    set_for(juma, by=baba)
    assert log_in(phone="+255712345674", password=TEMPORARY)[0] == 200


def test_manager_with_the_key_sets_a_workers(meneja: StaffMember, asha: StaffMember) -> None:
    # Jack's choice (A): Baba may hand the job over, by handing over the key. Asha needn't wait for him to come back.
    set_for(asha, by=meneja)
    assert log_in(phone=PHONE, password=TEMPORARY)[0] == 200


def test_manager_without_the_key_is_refused(shop_a: Shop, give_role: GiveRole, asha: StaffMember) -> None:
    # A manager runs the shop, but who works there is the owner's own (spec §6), until he hands the key over.
    plain_manager = job(shop_a, "Meneja", phone="+255712345671")
    give_role(plain_manager, RoleTemplate.MANAGER, None)
    with pytest.raises(PermissionDenied):
        set_for(asha, by=plain_manager)
    assert_unchanged(asha)


def test_the_key_on_one_side_is_not_enough(shop_a: Shop, side_a: Side, give_role: GiveRole, asha: StaffMember) -> None:
    # A password opens the whole person, not one side, so it asks for the key on the whole shop. Even for Asha, who
    # works on that one side alone: she may be given another side tomorrow, and the login would still be his to use.
    dawa_manager = job(shop_a, "Meneja", phone="+255712345671")
    give_role(dawa_manager, RoleTemplate.MANAGER, side_a)
    with shop_context(shop_a):
        grant_permission(dawa_manager, Permission.STAFF_MANAGE, side=side_a, by=None)
    with pytest.raises(PermissionDenied):
        set_for(asha, by=dawa_manager)
    assert_unchanged(asha)


def test_manager_cannot_reset_owner(baba: StaffMember, meneja: StaffMember) -> None:
    # The very thing the rule is for: with Baba's password, Meneja could approve his own day and his own pay. The
    # owner's own goes through the superuser (ADR-0038).
    assert refusal(baba, by=meneja) == "password.superuser_only"


def test_an_owner_cannot_reset_another_owner(shop_a: Shop, baba: StaffMember, give_role: GiveRole) -> None:
    # "Never for the owner" holds between two owners too. One may have fallen out with the other; the superuser, who has
    # no stake, does it.
    mama = job(shop_a, "Mama", phone="+255712345672")
    give_role(mama, RoleTemplate.OWNER, None)
    assert refusal(mama, by=baba) == "password.superuser_only"


def test_a_suspended_owner_is_still_the_owner(shop_a: Shop, baba: StaffMember, meneja: StaffMember) -> None:
    # A suspended person holds no keys on paper, so a manager would look stronger than Baba, and would hold his login
    # the day he came back.
    with shop_context(shop_a):
        suspend(baba, by=None, reason="Uchunguzi")
    assert refusal(baba, by=meneja) == "password.superuser_only"


def test_someone_holding_more_keys_is_refused(shop_a: Shop, meneja: StaffMember, give_role: GiveRole) -> None:
    # The giver rule, for a whole person: another manager, whom Baba also trusts with the pay. Meneja can't hand himself
    # that key by the back door.
    cashier = job(shop_a, "Rehema", phone="+255712345673")
    give_role(cashier, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(cashier, Permission.PAY_APPROVE, side=None, by=None)
    assert refusal(cashier, by=meneja) == "password.more_keys"


def test_a_suspended_person_counts_for_what_they_were_given(
    shop_a: Shop, meneja: StaffMember, give_role: GiveRole
) -> None:
    # The same manager, suspended: held, he has nothing; given, he has the pay. Brought back, he would hold it all
    # again.
    cashier = job(shop_a, "Rehema", phone="+255712345673")
    give_role(cashier, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(cashier, Permission.PAY_APPROVE, side=None, by=None)
        suspend(cashier, by=None, reason="Uchunguzi")
    assert refusal(cashier, by=meneja) == "password.more_keys"


def test_keys_on_another_side_count_as_more(shop_a: Shop, side_a: Side, give_role: GiveRole) -> None:
    # The same role, on another side: a Vyakula seller's login opens what a Dawa seller's doesn't.
    with shop_context(shop_a):
        vyakula = add_side(shop=shop_a, code="F", name="Vyakula", by=None)
    juma = job(shop_a, "Juma", phone="+255712345674")
    give_role(juma, RoleTemplate.SELLER, vyakula)
    dawa_seller = job(shop_a, "Neema", phone="+255712345675")
    give_role(dawa_seller, RoleTemplate.SELLER, side_a)
    with shop_context(shop_a):
        grant_permission(dawa_seller, Permission.STAFF_MANAGE, side=None, by=None)
    assert refusal(juma, by=dawa_seller) == "password.more_keys"


def test_a_person_at_two_shops_goes_to_the_superuser(shop_b: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # One person, one password (D12): it would open her job at the other shop too, which the owner here has no say over.
    # And the other shop's rows, and her keys there, can't be read from here.
    with shop_context(shop_b):
        add_staff(shop=shop_b, user=asha.user, display_name="Asha", by=None)
    assert refusal(asha, by=baba) == "password.superuser_only"


def test_a_job_she_left_at_another_shop_does_not_count(shop_b: Shop, baba: StaffMember, asha: StaffMember) -> None:
    with shop_context(shop_b):
        before = add_staff(shop=shop_b, user=asha.user, display_name="Asha", by=None)
        mark_left(before, left_on=before.started_on, by=None, reason="Amehama")
    set_for(asha, by=baba)
    assert log_in(phone=PHONE, password=TEMPORARY)[0] == 200


@pytest.mark.parametrize("admin_field", ["is_superuser", "is_staff"])
def test_someone_who_can_open_the_admin_goes_to_the_superuser(
    baba: StaffMember, asha: StaffMember, admin_field: str
) -> None:
    # The admin reads every shop. A password that opens it isn't this shop's owner's to hand out.
    User.objects.filter(pk=asha.user_id).update(**{admin_field: True})
    assert refusal(asha, by=baba) == "password.superuser_only"


def test_nobody_sets_their_own(baba: StaffMember, meneja: StaffMember) -> None:
    # A thief holding a logged-in phone could otherwise set a new password for its owner, with no current one, and keep
    # the login for good. A person changes their own by the change route, which asks for the current one.
    assert refusal(meneja, by=meneja) == "password.own"
    assert refusal(baba, by=baba) == "password.own"


def test_someone_who_left_is_refused(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    with shop_context(shop_a):
        mark_left(asha, left_on=asha.started_on, by=None, reason="Amehama")
    assert refusal(asha, by=baba) == "staff.left"


def test_a_suspended_worker_may_be_given_one(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # As with a PIN: it opens nothing until she is brought back. Baba may have suspended her for lost keys and a lost
    # phone, and want her back with a fresh password.
    with shop_context(shop_a):
        suspend(asha, by=baba, reason="Simu imepotea")
    set_for(asha, by=baba)
    assert User.objects.get(pk=asha.user_id).must_change_password is True


def test_a_person_of_another_shop_is_refused(baba: StaffMember, staff_b: StaffMember) -> None:
    # T1: shop B's staff, through a visit to shop A, or shop A's owner acting on shop B's: never across shops.
    with shop_context(baba.shop_id), pytest.raises(ValidationError) as refused:
        set_temporary_password(staff_b, TEMPORARY, by=baba, reason="Amesahau")
    assert refused.value.code == "staff.other_shop"
    assert User.objects.get(pk=staff_b.user_id).must_change_password is False


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("abc", "password_too_short"),
        ("password", "password_too_common"),
        ("73829164", "password_entirely_numeric"),
        ("ashamfano", "password_too_similar"),
    ],
)
def test_temporary_password_goes_through_the_checker(
    baba: StaffMember, asha: StaffMember, password: str, code: str
) -> None:
    # Like any other: it opens a real login until she replaces it. Filed under the field, so the screen shows it beside
    # the box the owner typed in.
    with pytest.raises(ValidationError) as refused:
        set_for(asha, by=baba, password=password)
    assert code in [error.code for error in refused.value.error_dict["password"]]
    assert_unchanged(asha)


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_reason_is_needed(baba: StaffMember, asha: StaffMember, reason: str) -> None:
    # T3: every action in the audit trail says why.
    with pytest.raises(ValidationError) as refused:
        set_for(asha, by=baba, reason=reason)
    assert refused.value.code == "staff.reason_required"
    assert_unchanged(asha)


def test_audit_line_holds_no_password(baba: StaffMember, asha: StaffMember, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        set_for(asha, by=baba, reason="Amesahau")

    with shop_context(asha.shop_id):
        line = AuditEvent.objects.get(action=AuditAction.STAFF_TEMPORARY_PASSWORD)
        # Who did it, to whom, and why.
        assert line.subject == asha
    assert line.created_by_id == baba.pk
    assert line.reason == "Amesahau"
    assert line.after == {"must_change_password": True}
    # Neither the password nor its hash, in the line or in any log: a hash can be attacked, and the trail is read often.
    stored = User.objects.get(pk=asha.user_id).password
    kept = json.dumps([line.before, line.after, line.reason, str(line)])
    for secret in (TEMPORARY, stored):
        assert secret not in kept
        assert secret not in caplog.text


def test_password_and_line_are_kept_together(baba: StaffMember, asha: StaffMember) -> None:
    # T3: if the line can't be written, the password isn't changed either: nobody's password changes with no trace.
    with audit_trail_down(), pytest.raises(RuntimeError):
        set_for(asha, by=baba)
    assert_unchanged(asha)


def test_password_stays_out_of_error_reports(baba: StaffMember, asha: StaffMember) -> None:
    # Django's error report, which a server with DEBUG off logs and sends, lists each function's local variables when
    # something fails. The password and its hash show as stars.
    with audit_trail_down(), pytest.raises(RuntimeError) as crash:
        set_for(asha, by=baba)
    frames = ExceptionReporter(None, crash.type, crash.value, crash.tb).get_traceback_frames()
    [frame] = [frame for frame in frames if frame["function"] == "set_temporary_password"]
    shown = dict(frame["vars"])
    assert set(str(shown["password"])) == {"*"}
    assert set(str(shown["encoded"])) == {"*"}


def test_temporary_password_ends_old_sessions(baba: StaffMember, asha: StaffMember) -> None:
    # A phone lost while logged in is logged out by this, as well as by her own change later (Django's session check).
    lost_phone = Client()
    assert lost_phone.post(LOGIN, {"phone": PHONE, "password": OLD}, content_type="application/json").status_code == 200
    assert lost_phone.get(SESSION).status_code == 200

    set_for(asha, by=baba)

    assert lost_phone.get(SESSION).status_code == 401


@pytest.mark.parametrize(("name", "login"), [("phone", PHONE), ("email", EMAIL)])
def test_temporary_password_lifts_the_wrong_password_count(
    baba: StaffMember, asha: StaffMember, name: str, login: str
) -> None:
    # She forgot it, so she typed it wrong five times, and the limit stops her. The new one must work at once, not after
    # 5 minutes of standing in front of Baba. A service has no request, so this lifts the count by her login name only.
    for _ in range(5):
        log_in(**{name: login, "password": "not-the-password"})
    assert log_in(**{name: login, "password": OLD}) == (400, ["too_many_login_attempts"])

    set_for(asha, by=baba)

    assert log_in(**{name: login, "password": TEMPORARY})[0] == 200


def test_a_second_temporary_password_replaces_the_first(baba: StaffMember, asha: StaffMember) -> None:
    # She lost the note Baba wrote it on, before she ever logged in. Each one writes its own line.
    set_for(asha, by=baba)
    set_for(asha, by=baba, password="mahindi-ya-njano-2028")

    assert log_in(phone=PHONE, password=TEMPORARY)[0] == 400
    assert log_in(phone=PHONE, password="mahindi-ya-njano-2028")[0] == 200
    with shop_context(asha.shop_id):
        assert AuditEvent.objects.filter(action=AuditAction.STAFF_TEMPORARY_PASSWORD).count() == 2
