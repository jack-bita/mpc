"""apps/staffpay/tests/test_pay_rate_routes.py — the pay rates routes, /api/v1/staffpay/pay-rates/ (WAGE-1, 03 §5.10).

    GET  pay-rates/?staff=…   the shop's today, a worker's rates, newest first, and the one in force today
    POST pay-rates/           a new rate, through set_pay_rate, with the id the client made (ADR-0007)

Who may is pinned in backend/tests/test_route_permissions.py, beside every other route's, and set_pay_rate's own rules
in test_set_pay_rate.py. Here the client from backend/conftest.py holds every key: shop A's owner, Staff A. The amounts
are made up: the repo is public (rule 10).
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from apps.staffpay.models import PayRate
from apps.staffpay.services import set_pay_rate

pytestmark = pytest.mark.django_db

PAY_RATES = "/api/v1/staffpay/pay-rates/"


def worker(shop: Shop, name: str, *, started_on: dt.date) -> StaffMember:
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, started_on=started_on, by=None)


def rate(staff: StaffMember, amount: str, effective_from: dt.date, *, by: StaffMember | None = None) -> PayRate:
    with shop_context(staff.shop_id):
        return set_pay_rate(staff, daily_rate=Decimal(amount), effective_from=effective_from, by=by)


def new_rate(staff: StaffMember, effective_from: dt.date, **changes: object) -> dict[str, object]:
    # A new rate as the page sends it, with the id it made itself (ADR-0007).
    sent: dict[str, object] = {
        "id": str(uuid.uuid7()),
        "staff": str(staff.pk),
        "daily_rate": "10000",
        "shares_meals": True,
        "effective_from": effective_from.isoformat(),
        "note": "",
    }
    sent.update(changes)
    return sent


@pytest.fixture
def today(shop_a: Shop) -> dt.date:
    return shop_today(shop_a)


@pytest.fixture
def juma(shop_a: Shop, today: dt.date) -> StaffMember:
    # A worker who started nine days ago.
    return worker(shop_a, "Juma", started_on=today - dt.timedelta(days=9))


def test_a_workers_rates_newest_first_with_todays(
    staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember, today: dt.date
) -> None:
    # Juma's page: his rate from his first day, which is the one in force today, and a raise still to come, listed
    # first, as the history shows them. Money as strings (rule 3), each with who set it, by the nickname the page shows.
    first = rate(juma, "10000", juma.started_on, by=staff_a)
    coming = rate(juma, "12000", today + dt.timedelta(days=12))

    reply = staff_client_a.get(PAY_RATES, {"staff": str(juma.pk)})

    assert reply.status_code == 200
    answer = reply.json()
    assert answer["today"] == today.isoformat()
    assert answer["in_force"] == str(first.pk)
    assert [row["id"] for row in answer["rates"]] == [str(coming.pk), str(first.pk)]
    assert answer["rates"][1] == {
        "id": str(first.pk),
        "staff": str(juma.pk),
        "daily_rate": "10000.00",
        "shares_meals": True,
        "effective_from": juma.started_on.isoformat(),
        "note": "",
        "set_by": "Staff A",
        "created_at": answer["rates"][1]["created_at"],
    }
    # The seed's, or the superuser's, is set by nobody.
    assert answer["rates"][0]["set_by"] is None


def test_a_rate_still_to_come_is_not_in_force(staff_client_a: APIClient, juma: StaffMember, today: dt.date) -> None:
    # A first rate from tomorrow: today he has none, so the page says so, and shows the coming one in the history.
    coming = rate(juma, "10000", today + dt.timedelta(days=1))
    answer = staff_client_a.get(PAY_RATES, {"staff": str(juma.pk)}).json()
    assert answer["in_force"] is None
    assert [row["id"] for row in answer["rates"]] == [str(coming.pk)]


def test_a_worker_with_no_rate(staff_client_a: APIClient, juma: StaffMember) -> None:
    answer = staff_client_a.get(PAY_RATES, {"staff": str(juma.pk)}).json()
    assert (answer["in_force"], answer["rates"]) == (None, [])


def test_another_shops_worker_shows_no_rate(staff_client_a: APIClient, shop_b: Shop, today: dt.date) -> None:
    # Shop B's worker, asked about by their real id: their rates are not shop A's to see, and the answer is the one an
    # id no shop has gets, so it tells nothing (03 §5.4).
    stranger = worker(shop_b, "Juma", started_on=today)
    rate(stranger, "15000", today)
    nobodys = staff_client_a.get(PAY_RATES, {"staff": str(uuid.uuid7())}).json()
    theirs = staff_client_a.get(PAY_RATES, {"staff": str(stranger.pk)}).json()
    assert theirs == nobodys
    assert theirs["rates"] == []


@pytest.mark.parametrize("asked", [{}, {"staff": "Juma"}])
def test_the_list_names_its_worker(staff_client_a: APIClient, asked: dict[str, str]) -> None:
    # No worker, or one that is no id: refused under `staff`, never read as every worker's.
    reply = staff_client_a.get(PAY_RATES, asked)
    assert reply.status_code == 400
    assert list(reply.json()["fields"]) == ["staff"]


def test_baba_sets_a_rate(staff_client_a: APIClient, juma: StaffMember) -> None:
    # Typed as Baba types it, "10000": stored as 10,000.00, and answered as the page shows it, with who set it.
    sent = new_rate(juma, juma.started_on, note="Mshahara wa kuanzia", shares_meals=False)

    reply = staff_client_a.post(PAY_RATES, sent, format="json")

    assert reply.status_code == 201
    body = reply.json()
    assert (body["id"], body["daily_rate"], body["shares_meals"], body["note"], body["set_by"]) == (
        sent["id"],
        "10000.00",
        False,
        "Mshahara wa kuanzia",
        "Staff A",
    )
    with shop_context(juma.shop_id):
        assert PayRate.objects.get(pk=str(sent["id"])).daily_rate == Decimal("10000.00")


def test_a_rate_sent_twice_is_made_once(staff_client_a: APIClient, juma: StaffMember) -> None:
    # The phone's answer was lost and it sends the same rate again, with the same id: one rate, and the same answer.
    sent = new_rate(juma, juma.started_on)
    assert staff_client_a.post(PAY_RATES, sent, format="json").status_code == 201
    again = staff_client_a.post(PAY_RATES, sent, format="json")
    assert again.status_code == 201
    assert again.json()["id"] == sent["id"]
    with shop_context(juma.shop_id):
        assert PayRate.objects.filter(staff=juma).count() == 1


def test_mistakes_come_back_beside_their_boxes(staff_client_a: APIClient, juma: StaffMember) -> None:
    # An amount of 0 and a day before his first: both at once, each beside its box, in the service's codes, which the
    # page translates.
    sent = new_rate(juma, juma.started_on - dt.timedelta(days=1), daily_rate="0")
    reply = staff_client_a.post(PAY_RATES, sent, format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {
        "daily_rate": ["pay_rate.amount_invalid"],
        "effective_from": ["pay_rate.before_first_day"],
    }


def test_the_question_of_the_meals_is_never_left_out(staff_client_a: APIClient, juma: StaffMember) -> None:
    # A form that forgot to ask would make the cook pay for the meals: the route asks the page to say, every time.
    sent = new_rate(juma, juma.started_on)
    del sent["shares_meals"]
    reply = staff_client_a.post(PAY_RATES, sent, format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"shares_meals": ["required"]}


def test_another_shops_worker_gets_no_rate(staff_client_a: APIClient, shop_b: Shop, today: dt.date) -> None:
    # Shop B's worker, named by their real id: "not found", as an id no shop has, and nothing written.
    stranger = worker(shop_b, "Juma", started_on=today)
    reply = staff_client_a.post(PAY_RATES, new_rate(stranger, today), format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"staff": ["does_not_exist"]}
    with shop_context(shop_b):
        assert not PayRate.objects.exists()


def test_who_may_is_the_services(staff_client_a: APIClient, staff_a: StaffMember) -> None:
    # The route asks settings.manage; the PIN's rule is set_pay_rate's, answered through the one error handler: the
    # owner, who holds every key, still may not set his own rate.
    reply = staff_client_a.post(PAY_RATES, new_rate(staff_a, staff_a.started_on), format="json")
    assert reply.status_code == 400
    assert reply.json()["code"] == "staff.own"
