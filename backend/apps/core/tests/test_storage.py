"""apps/core/tests/test_storage.py — tests for where the shop's files are kept, apps/core/storage.py (CTRL-3).

Two places, one set of promises: the folder (the real server, Jack's laptop) and the database (the demo, whose disk
doesn't last). Each test says which it checks; the promises both keep run on both. The promises: a file keeps to its
shop, a name sent again writes over the file, and no file has a web address.

The shops come from backend/conftest.py and are typed as plain models: `core` may not name `Shop` (ADR-0035).
"""

import os
import stat
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.db.models import Model

from apps.core.models import StoredFile
from apps.core.storage import DatabaseStorage, FolderStorage, NoAddress
from apps.core.tenancy import NoShopSelected, shop_context, system_context

# The shops are rows in the test database, and the demo's files too.
pytestmark = pytest.mark.django_db

# A few made-up bytes stand for a photo: the storage never looks inside a file (the upload route does, CTRL-3).
PHOTO = b"\xff\xd8\xff not a real photo"


def name_in(shop: Model) -> str:
    # A file's name as every caller makes it: its shop's id, then the file's own id.
    return f"{shop.pk}/{uuid.uuid7()}"


@pytest.fixture(params=["folder", "database"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Storage:
    # Each test that takes `storage` runs twice: once on the folder, once on the database, as the real server and the
    # demo must keep the same promises. The folder is the test's own, empty.
    if request.param == "folder":
        return FolderStorage(location=str(tmp_path))
    return DatabaseStorage()


def test_demo_storage_keeps_a_file(shop_a: Model) -> None:
    # The demo saves a photo, then reads it back whole, as the office route will (CTRL-3).
    storage = DatabaseStorage()
    name = name_in(shop_a)

    with shop_context(shop_a):
        saved = storage.save(name, ContentFile(PHOTO))

        assert saved == name
        assert storage.exists(name)
        assert storage.size(name) == len(PHOTO)
        with storage.open(name) as file:
            assert file.read() == PHOTO


def test_a_file_survives_in_the_database(shop_a: Model) -> None:
    # The point of the demo's storage: the file is a row, so it is still there after a restart, which wipes Render's
    # disk. A new storage object stands for the new server process.
    name = name_in(shop_a)
    with shop_context(shop_a):
        DatabaseStorage().save(name, ContentFile(PHOTO))

        assert StoredFile.objects.filter(name=name).count() == 1
        with DatabaseStorage().open(name) as file:
            assert file.read() == PHOTO


def test_the_same_name_writes_over_the_file(storage: Storage, shop_a: Model) -> None:
    # A laptop that sends a photo again, after its first try's answer was lost, must not leave two copies, nor get a
    # changed name back (ADR-0007): the name is the file's own id.
    name = name_in(shop_a)
    with shop_context(shop_a):
        first = storage.save(name, ContentFile(b"first try"))
        second = storage.save(name, ContentFile(PHOTO))

        assert first == second == name
        with storage.open(name) as file:
            assert file.read() == PHOTO


def test_a_file_keeps_to_its_shop(storage: Storage, shop_a: Model, shop_b: Model) -> None:
    # T1: inside shop A's visit, shop B's file can't be written, read, measured or removed, whichever way it is named.
    # Both storages keep it, though the folder has no guard of its own: the check is on the name.
    theirs = name_in(shop_b)
    with shop_context(shop_b):
        storage.save(theirs, ContentFile(PHOTO))

    with shop_context(shop_a):
        for reach in (
            lambda: storage.save(name_in(shop_b), ContentFile(PHOTO)),
            lambda: storage.open(theirs),
            lambda: storage.exists(theirs),
            lambda: storage.size(theirs),
            lambda: storage.delete(theirs),
        ):
            with pytest.raises(SuspiciousFileOperation):
                reach()

    # And the refused delete took nothing away.
    with shop_context(shop_b):
        assert storage.exists(theirs)


@pytest.mark.parametrize(
    "make_name",
    [
        lambda shop: "photo.jpg",  # no shop at all
        lambda shop: f"{shop.pk}/",  # the shop's folder, not a file in it
        lambda shop: f"not-a-shop/{uuid.uuid7()}",
    ],
    ids=["no-shop", "no-file", "not-a-shop"],
)
def test_a_name_starts_with_its_shop(storage: Storage, shop_a: Model, make_name: Callable[[Model], str]) -> None:
    # Every name is `<shop id>/<file id>`. Another shape is refused before anything is written, so a file can never sit
    # where no shop's check would find it.
    with shop_context(shop_a), pytest.raises(SuspiciousFileOperation):
        storage.save(make_name(shop_a), ContentFile(PHOTO))


def test_no_file_outside_a_shop(storage: Storage, shop_a: Model) -> None:
    # As a row is never read outside a visit or a system job (ADR-0022), neither is a file.
    with pytest.raises(NoShopSelected):
        storage.save(name_in(shop_a), ContentFile(PHOTO))


def test_a_system_job_reaches_any_shops_file(storage: Storage, shop_a: Model) -> None:
    # ATT-7's nightly job removes old clock-in photos shop by shop, as the system: it may name any shop's file.
    name = name_in(shop_a)
    with system_context():
        storage.save(name, ContentFile(PHOTO))
        storage.delete(name)

        assert not storage.exists(name)


def test_files_have_no_address(storage: Storage, shop_a: Model) -> None:
    # A photo is served only through Django, after a permission check (03 §5.13): no storage hands out a link anyone
    # could pass around.
    name = name_in(shop_a)
    with shop_context(shop_a):
        storage.save(name, ContentFile(PHOTO))

        with pytest.raises(NoAddress):
            storage.url(name)


def test_folder_files_only_the_server_may_read(tmp_path: Path, shop_a: Model) -> None:
    # On the real server, a photo of a worker is personal data (03 §10): only the user the server runs as may read the
    # file or list its folder, not another program or person on the machine.
    storage = FolderStorage(location=str(tmp_path))
    name = name_in(shop_a)
    with shop_context(shop_a.pk):
        storage.save(name, ContentFile(PHOTO))
        path = Path(storage.path(name))

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
