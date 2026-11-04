"""apps/people/tests/test_login_limits.py — whoever guesses passwords is slowed down (AUTH-3; 03 §5.10; ADR-0038).

allauth runs two limits on wrong passwords, its defaults, which these tests pin: 5 in 5 minutes per person, and 10 a
minute per caller. Past either, even the right password waits (`too_many_login_attempts`).

    the caller, as these limits see them      what they are told apart by
    an IPv4 address                           itself: a shop's many phones share one
    an IPv6 address                           its /64 network, where a phone takes new addresses at will
    an address the caller wrote in a header   nothing: only what the proxy in front saw counts

They count in a table of their own (`default`, CACHES, config/settings/base.py), so a flood of one kind never clears
another kind's counts. Each test starts with empty caches (backend/conftest.py). Fake data only, and every address here
is one set aside for documentation (RFC 5737; RFC 3849 for IPv6); the repo is public (03 §10).
"""

import hashlib
from typing import Any

import pytest
from django.db import connection
from django.test import Client
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.people.models import User

pytestmark = pytest.mark.django_db

LOGIN = "/_allauth/browser/v1/auth/login"
PAIRING = "/api/devices/v1/pairing/"

PHONE = "+255712345678"
EMAIL = "meneja@example.com"
PASSWORD = "mbegu-za-mahindi-2026"
# allauth's two limits on wrong passwords.
PER_PERSON = 5
PER_CALLER = 10
TOO_MANY = (400, ["too_many_login_attempts"])


@pytest.fixture
def person() -> User:
    return User.objects.create_user(full_name="Meneja Mfano", phone=PHONE, email=EMAIL, password=PASSWORD)


def someone_else(number: int) -> str:
    # A phone that is nobody's, new for each guess: only the caller's own count can stop these.
    return f"+2557120000{number:02d}"


def try_login(address: str = "203.0.113.10", *, forwarded: str = "", **sent: str) -> tuple[int, list[str]]:
    # One login, from a browser at this address, as the proxy in front saw it. `forwarded`: the X-Forwarded-For header
    # as it reaches Django, the caller's own words first and the proxy's own entry last. CSRF isn't what these test.
    # Left out when there is none: DRF reads an empty header as a blank address, which every such caller would share.
    header: dict[str, Any] = {"HTTP_X_FORWARDED_FOR": forwarded} if forwarded else {}
    answer = Client(REMOTE_ADDR=address).post(LOGIN, sent, content_type="application/json", **header)
    return answer.status_code, [error["code"] for error in answer.json().get("errors", [])]


def test_login_rate_limited(person: User) -> None:
    # Five wrong passwords for one person, each from a network of its own: the person's own count stops the sixth,
    # from anywhere, even with the right password.
    for network in range(1, PER_PERSON + 1):
        assert try_login(f"198.51.100.{network}", email=EMAIL, password="not-the-password")[0] == 400
    assert try_login("198.51.100.99", email=EMAIL, password=PASSWORD) == TOO_MANY


def test_a_caller_guessing_many_people_is_slowed_down(person: User) -> None:
    # Ten wrong passwords from one network, each for a different phone, as someone trying common passwords on everyone:
    # the caller's own count stops the next one. Another network isn't slowed down.
    for number in range(PER_CALLER):
        assert try_login(phone=someone_else(number), password="not-the-password")[0] == 400
    assert try_login(phone=PHONE, password=PASSWORD) == TOO_MANY
    assert try_login("198.51.100.20", phone=PHONE, password=PASSWORD) == (200, [])


def test_right_passwords_never_count(person: User) -> None:
    # A shop's phones share one address: logging in all day must not use up the limit on wrong ones.
    for _ in range(PER_CALLER + 2):
        assert try_login(phone=PHONE, password=PASSWORD) == (200, [])


def test_login_limit_counts_by_network(person: User) -> None:
    # Under IPv6 a phone can take a new address in its own network, its /64, for every guess: so the network counts as
    # one, as an IPv4 shop's one address does. Another network isn't slowed down.
    for number in range(PER_CALLER):
        address = f"2001:db8:5:7::{number + 1:x}"
        assert try_login(address, phone=someone_else(number), password="not-the-password")[0] == 400

    assert try_login("2001:db8:5:7:abcd::99", phone=PHONE, password=PASSWORD) == TOO_MANY
    assert try_login("2001:db8:5:8::1", phone=PHONE, password=PASSWORD) == (200, [])


def test_login_limit_reads_the_address_behind_the_proxy(person: User) -> None:
    # Caddy adds the address it saw to the end of X-Forwarded-For (NUM_PROXIES, 1), and the entries before it are the
    # caller's own words: a new false one for every guess changes nothing. Behind Caddy, REMOTE_ADDR is Caddy itself.
    for number in range(PER_CALLER):
        forwarded = f"192.0.2.{number + 1}, 203.0.113.10"
        sent = {"phone": someone_else(number), "password": "not-the-password"}
        assert try_login("10.0.0.1", forwarded=forwarded, **sent)[0] == 400

    assert try_login("10.0.0.1", forwarded="192.0.2.99, 203.0.113.10", phone=PHONE, password=PASSWORD) == TOO_MANY
    # Another caller, behind the same Caddy, isn't slowed down.
    assert try_login("10.0.0.1", forwarded="198.51.100.20", phone=PHONE, password=PASSWORD) == (200, [])


def test_login_limit_reads_cloudflares_header_on_the_demo(person: User, settings: Settings) -> None:
    # On the demo, Cloudflare writes the caller's address in a header of its own, over any the caller sent
    # (render.yaml).
    settings.CLIENT_IP_HEADER = "CF-Connecting-IP"
    for number in range(PER_CALLER):
        client = Client(REMOTE_ADDR=f"10.0.0.{number + 1}", HTTP_CF_CONNECTING_IP="203.0.113.10")
        client.post(LOGIN, {"phone": someone_else(number), "password": "x-wrong"}, content_type="application/json")

    slowed = Client(REMOTE_ADDR="10.0.0.50", HTTP_CF_CONNECTING_IP="203.0.113.10")
    other = Client(REMOTE_ADDR="10.0.0.50", HTTP_CF_CONNECTING_IP="198.51.100.20")
    sent = {"phone": PHONE, "password": PASSWORD}
    assert slowed.post(LOGIN, sent, content_type="application/json").status_code == 400
    assert other.post(LOGIN, sent, content_type="application/json").status_code == 200


def test_login_counts_keep_no_address_and_no_login_name() -> None:
    # The counts sit in a table, and in its backups, and an address or a phone can name a person. They keep fingerprints
    # made with the server's secret key: not even a plain hash, which could be worked back by trying every phone number.
    try_login(phone=PHONE, password="not-the-password")
    try_login(email=EMAIL, password="not-the-password")

    with connection.cursor() as cursor:
        cursor.execute("SELECT cache_key FROM throttle_login")
        keys = " ".join(key for (key,) in cursor.fetchall())
    assert "allauth" in keys  # the login limits' own table: the counts are there
    for written_out in ("203.0.113", PHONE, EMAIL):
        assert written_out not in keys
    for login_name in (PHONE, EMAIL):
        assert hashlib.sha256(login_name.encode()).hexdigest() not in keys


def test_pairing_flood_keeps_login_counts(person: User, settings: Settings) -> None:
    # A full cache table loses a third of its rows, picked by their keys' ABC order, not their age, and allauth's keys
    # sort before the pairing limits': in a shared table, a flood of pairing starts from many networks would clear a
    # guesser's count, and give them five more tries. In a table of their own, it clears only starts. Every table is
    # shrunk to three rows here, so a small flood fills it.
    settings.CACHES = {name: {**config, "OPTIONS": {"MAX_ENTRIES": 3}} for name, config in settings.CACHES.items()}
    for _ in range(PER_PERSON):
        try_login(phone=PHONE, password="not-the-password")
    for network in range(1, 9):
        APIClient(REMOTE_ADDR=f"198.51.100.{network}").post(PAIRING)

    assert try_login(phone=PHONE, password=PASSWORD) == TOO_MANY
