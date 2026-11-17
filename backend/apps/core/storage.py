"""apps/core/storage.py — where the shop's files are kept: photos now, other files later (03 §5.13, CTRL-3).

Django's storage API is one way to save, open and remove a file, whatever keeps it. Code asks the default storage
(`default_storage`, or a FileField, which uses it) and never names a folder, so the place can change with no code
change: settings choose it (config/settings/base.py, prod.py). Two places, two classes here:

    FolderStorage    a folder on the server's disk: the real server (FILES_ROOT, which OPS-5 mounts and OPS-8 backs
                     up), and Jack's laptop (backend/files/, gitignored)
    DatabaseStorage  a table of the database (StoredFile, apps/core/models.py): the demo, as Render's free plan loses
                     its disk at every restart and every deploy, so a photo kept there would vanish within the hour

What both keep, the same way:
- A file's name starts with its shop's id: `<shop id>/<file id>`. A name for another shop than the one open is
  refused, so one shop's code can never write or read another shop's file by a wrong name (T1).
- A name is never changed to make room: the same name again writes over the file. A file's name is its own id, so
  the same name is the same file sent again, a laptop's retry (ADR-0007), never a second file.
- A file has no web address. `url()` refuses: a photo is served only through Django, after a permission check
  (CTRL-3's office route), never from a link anyone could pass around (03 §5.13).
"""

import uuid
from typing import Any

from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage, Storage
from django.db.models.functions import Length
from django.utils.deconstruct import deconstructible

from apps.core.models import StoredFile
from apps.core.tenancy import ALL_SHOPS, current_shop


class NoAddress(Exception):
    """A file was asked for its web address. It has none: it is served only through a route that checks who asks."""


def shop_of(name: str) -> uuid.UUID:
    """The shop a file's name belongs to, from its first part, checked against the shop that is open (T1).

    Raises SuspiciousFileOperation, Django's own refusal of a bad file name, for a name that doesn't start with a shop's
    id, or that starts with another shop's than the one open. A system job (system_context) may name any shop's file:
    ATT-7's nightly job removes old clock-in photos shop by shop.
    """
    first, _, rest = name.partition("/")
    try:
        shop = uuid.UUID(first)
    except ValueError:
        shop = None
    # A name with nothing after its shop would be the shop's folder itself, not a file in it.
    if shop is None or not rest:
        raise SuspiciousFileOperation(f"{name!r} is not <shop id>/<file id>.")
    # current_shop() raises NoShopSelected when no shop is open: a file is never saved or read outside a visit or a
    # system job, as a row never is (ADR-0022).
    open_shop = current_shop()
    if open_shop is not ALL_SHOPS and open_shop != shop:
        raise SuspiciousFileOperation(f"{name!r} belongs to another shop than the one open.")
    return shop


@deconstructible
class FolderStorage(FileSystemStorage):
    """Files in a folder on the server's disk, each at `<folder>/<shop id>/<file id>`."""

    def __init__(self, location: str | None = None, **options: Any) -> None:
        # allow_overwrite: the same name writes over the file, never beside it as `<id>_a8Kd2`. 0o600 and 0o700: only
        # the user the server runs as may read the files or list the folders. A photo of a worker is personal data
        # (03 §10), and nothing else on the server needs to read it.
        super().__init__(
            location=location,
            allow_overwrite=True,
            file_permissions_mode=0o600,
            directory_permissions_mode=0o700,
            **options,
        )

    def path(self, name: str) -> str:
        # Every way into the folder passes here (save, open, exists, size, delete), so the shop check sits here once.
        shop_of(name)
        return super().path(name)

    def url(self, name: str | None) -> str:
        raise NoAddress("A file has no address: it is served only through Django, after a permission check.")


@deconstructible
class DatabaseStorage(Storage):
    """Files in a table of the database (StoredFile), for the demo, whose disk doesn't survive a restart.

    Read and written through StoredFile's guarded manager, so the shop that is open is checked twice: by shop_of() on
    the name, and by the guard on every read (ADR-0022). The demo's nightly wipe (`flush`, apps/demo/services.py)
    empties this table with the others, so no file outlives the rows that name it.
    """

    def _save(self, name: str, content: File[Any]) -> str:
        shop = shop_of(name)
        # Read whole: the demo's files are photos of about 150 KB, and the upload route refuses any over 1 MB.
        data = content.read()
        # update_or_create: the same name again writes over the file, as the folder does (allow_overwrite).
        StoredFile.objects.update_or_create(shop_id=shop, name=name, defaults={"content": data})
        return name

    def _open(self, name: str, mode: str = "rb") -> File[Any]:
        # Only reading: a file is written whole through save(), never changed in place.
        if mode != "rb":
            raise ValueError(f"DatabaseStorage opens files for reading only, not {mode!r}.")
        content = StoredFile.objects.filter(shop_id=shop_of(name), name=name).values_list("content", flat=True).first()
        if content is None:
            raise FileNotFoundError(name)
        # bytes(): PostgreSQL's bytea comes back as a memoryview.
        return ContentFile(bytes(content), name=name)

    def exists(self, name: str) -> bool:
        return StoredFile.objects.filter(shop_id=shop_of(name), name=name).exists()

    def delete(self, name: str) -> None:
        # Taking the bytes away is the point of removing a file: the retention rule (03 §5.13) asks that a clock-in
        # photo is gone, not hidden. The row that named it (control.Attachment) stays, with who removed it and why.
        StoredFile.objects.filter(shop_id=shop_of(name), name=name).delete()

    def size(self, name: str) -> int:
        # Counted by PostgreSQL (length of the bytes), so the file itself never travels to Python just to be measured.
        size = (
            StoredFile.objects.filter(shop_id=shop_of(name), name=name)
            .annotate(size=Length("content"))
            .values_list("size", flat=True)
            .first()
        )
        if size is None:
            raise FileNotFoundError(name)
        return int(size)

    def is_name_available(self, name: str, max_length: int | None = None) -> bool:
        # The same name is the same file sent again (above), so a name already used is still free to write over, as
        # the folder's allow_overwrite does. Only a name too long for its column is not: Django then shortens it, and
        # refuses one it can't (Storage.get_available_name, which also refuses a name that climbs out with "..").
        return not (max_length and len(name) > max_length)

    def url(self, name: str | None) -> str:
        raise NoAddress("A file has no address: it is served only through Django, after a permission check.")

    def listdir(self, path: str) -> tuple[list[str], list[str]]:
        # Nothing lists a shop's files: each is found through the row that names it.
        raise NotImplementedError("DatabaseStorage doesn't list files: find a file through the row that names it.")
