"""apps/shops/tests/test_admin.py — the Django admin page for shops (apps/shops/admin.py).

The superuser adds MPC and the demo shop here before any office screen exists. These tests drive the
page like a browser would, through Django's test client, logged in as a fake superuser (the
`superuser` and `superuser_client` fixtures, in backend/conftest.py).
"""

import pytest
from django.test import Client

from apps.shops.models import Shop

pytestmark = pytest.mark.django_db

SHOPS = "/admin/shops/shop/"
# Fake shops only: the repo is public (03 §10).
NAME = "Duka la Mfano"
CODE = "MFANO"


def form_data(**changes: str) -> dict[str, str]:
    # Everything the shop's form sends when the superuser presses Save, with the defaults filled in.
    # `practice_of` empty: the shop is nobody's practice copy.
    data = {
        "name": NAME,
        "code": CODE,
        "timezone": "Africa/Dar_es_Salaam",
        "currency": "TZS",
        "default_language": "sw",
        "kind": "live",
        "practice_of": "",
    }
    return {**data, **changes}


def test_admin_adds_a_shop(superuser_client: Client) -> None:
    # Typed in small letters: the form cleans it the same way as everywhere else (Shop.clean).
    response = superuser_client.post(f"{SHOPS}add/", form_data(code="mfano"))

    assert response.status_code == 302  # saved, and sent on to the next page
    shop = Shop.objects.get()
    assert shop.code == "MFANO"
    assert shop.status == "active"  # every new shop starts active; the page doesn't ask


def test_admin_shows_id_read_only(superuser_client: Client) -> None:
    shop = Shop.objects.create(name=NAME, code=CODE)

    response = superuser_client.get(f"{SHOPS}{shop.pk}/change/")

    # Shown, so the superuser can match a shop with a log line or a device's records...
    assert "id" in response.context["adminform"].readonly_fields
    # ...but there is no box to type a new one into. The id stays editable in the model on purpose, so
    # DRF keeps the id a device sends (ADR-0007, CORE-1); a changed id here would save a copy of the shop.
    assert "id" not in response.context["adminform"].form.fields


def test_admin_kind_and_status_fixed_on_edit(superuser_client: Client) -> None:
    shop = Shop.objects.create(name=NAME, code=CODE)

    # A form sent with a new kind and status, as a changed page or a hand-made request could send it.
    response = superuser_client.post(f"{SHOPS}{shop.pk}/change/", form_data(kind="demo", status="suspended"))

    assert response.status_code == 302  # the rest of the form is saved...
    shop.refresh_from_db()
    # ...but a live shop never becomes a demo one, open to the demo's fake data (ADR-0029), and a
    # suspension waits for the audit trail, which records who, when and why (rule 7, CTRL-2).
    assert shop.kind == "live"
    assert shop.status == "active"


def test_admin_currency_fixed_on_edit(superuser_client: Client) -> None:
    shop = Shop.objects.create(name=NAME, code=CODE)

    response = superuser_client.post(f"{SHOPS}{shop.pk}/change/", form_data(currency="KES"))

    assert response.status_code == 302
    shop.refresh_from_db()
    # A sale stores only the number, and the shop gives it its currency: TZS turned into KES would make
    # every old 1,000 shillings read as 1,000 Kenyan shillings (Jack, 27 Oct 2026).
    assert shop.currency == "TZS"


def test_admin_cannot_delete_a_shop(superuser_client: Client) -> None:
    shop = Shop.objects.create(name=NAME, code=CODE)

    # "post": "yes" is the admin's "Yes, I'm sure" button on the delete page.
    response = superuser_client.post(f"{SHOPS}{shop.pk}/delete/", {"post": "yes"})

    # Nothing is deleted (rule 7): a shop that stops is suspended, and its history stays.
    assert response.status_code == 403
    assert Shop.objects.filter(pk=shop.pk).exists()

    # Nor many at once: the list page's "Delete selected" action is gone too. Read from the list page
    # itself, so this test needs no User (people sits above shops, ADR-0035). With no actions left at
    # all, the page shows no action box (`action_form` is None).
    action_form = superuser_client.get(SHOPS).context["action_form"]
    actions = dict(action_form.fields["action"].choices) if action_form else {}
    assert "delete_selected" not in actions
