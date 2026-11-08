"""test_e2e_shop.py — proves the browser tests' made-up shop is made only on an empty test database (UI-6).

backend/tests/e2e_shop.py makes a shop whose manager's password is written in the public repo. Run anywhere but the
browser tests' own throwaway container, on the demo or the real server, it would quietly add a live shop anyone could
log in to. So it refuses unless the container marks itself as the tests' (E2E_SHOP=yes, compose.e2e.yml) and no shop
exists yet. These tests run the file's text the way scripts/run_e2e.sh hands it to `manage.py shell --command`, and
check that a refusal writes nothing.
"""

from pathlib import Path

import pytest

from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.shops.models import Shop

SHOP_FILE = Path(__file__).with_name("e2e_shop.py")


def run_the_shop_file() -> None:
    # The file's whole text, run with fresh names, as `shell --command` runs it: its last line makes the shop.
    exec(compile(SHOP_FILE.read_text(encoding="utf-8"), str(SHOP_FILE), "exec"), {})


@pytest.mark.django_db
def test_e2e_shop_refused_outside_the_test_container(monkeypatch: pytest.MonkeyPatch) -> None:
    # The demo and the real server never set the mark: the file stops before it writes a row.
    monkeypatch.delenv("E2E_SHOP", raising=False)
    with pytest.raises(SystemExit, match="E2E_SHOP"):
        run_the_shop_file()
    assert not Shop.objects.exists()
    assert not User.objects.exists()


@pytest.mark.django_db
def test_e2e_shop_refused_where_a_shop_exists(monkeypatch: pytest.MonkeyPatch, shop_a: Shop) -> None:
    # The mark alone isn't enough: a database that holds any shop is someone's, never the tests' empty one.
    monkeypatch.setenv("E2E_SHOP", "yes")
    with pytest.raises(SystemExit, match="empty"):
        run_the_shop_file()
    assert list(Shop.objects.all()) == [shop_a]
    assert not User.objects.exists()


@pytest.mark.django_db
def test_e2e_shop_made_on_an_empty_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    # The guard lets the tests' own run through: the shop, its manager and its seller, as the browser test expects.
    monkeypatch.setenv("E2E_SHOP", "yes")
    run_the_shop_file()
    shop = Shop.objects.get(code="JARIBIO")
    with shop_context(shop):
        assert sorted(StaffMember.objects.values_list("display_name", flat=True)) == ["Asha", "Meneja"]
