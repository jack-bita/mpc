"""apps/staffpay/documents.py — the clock document: a tap of Ingia or Toka a shop laptop pushes, saved as one line
in the attendance book with its photo's row, or why it has none (ATT-1, ATT-3; 02 §12, 03 §6.3, §5.13).

    version 2: {"kind": "in", "last_server_time": "2026-11-19T03:50:00Z", "photo": {"id": ..., "kind": "clock_photo",
               "content_type": "image/jpeg", "size": 151234, "sha256": "9f…"}}      or "no_photo": "no_camera"
    version 1: {"kind": "in", "last_server_time": "2026-11-10T03:50:00Z"}           the app before ATT-3: old_app

The push (apps/sync/push.py) checks the envelope, the maker and the shape, then calls post_clock inside its own
transaction for the document; the list of document types (apps/sync/document_types.py) names it. As every saving
code does (tests/probe/documents.py): it saves inside a recording_changes block, which joins the push's; an INSERT
with the laptop's id, so an id another shop holds clashes and is never overwritten; and a broken rule is a flag,
never a refusal (accept, then flag). A clock-in needs no key: anyone working at the shop may clock in on any of its
laptops (Jack, ATT-1). A camera missing, blocked or broken never stops a tap either: it is kept, with why it has no
photo (Jack, ATT-3: A). A tap that comes after its day's pay was approved is kept too, counted nowhere, as that pay
never changes (A3), and flagged, so nobody's pay is short unsaid (late_record, WAGE-10).
"""

import datetime as dt
import uuid
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from apps.control.models import AttachmentKind, Flag, FlagKind
from apps.control.services import expect_attachment, raise_flag
from apps.core.api.times import ZonedDateTimeField
from apps.core.changes import record_change, recording_changes
from apps.people.models import Device, StaffMember
from apps.staffpay.calculations import Evidence, Sign, check_time
from apps.staffpay.models import AttendanceEvent, ClockKind, NoPhoto, TimeCheck
from apps.staffpay.selectors import is_closed
from apps.staffpay.services import where_it_falls


class Pushed(Protocol):
    # What the saving code reads of a pushed document; the push's Document (apps/sync/document_types.py) has each
    # part. Written here as a shape, not imported: `sync` is the layer above (ADR-0043), and hands its Document in.
    # The type checker proves it fits where the list of types names post_clock. Read-only, as the Document is frozen.
    @property
    def id(self) -> uuid.UUID: ...
    @property
    def device(self) -> Device: ...
    @property
    def device_seq(self) -> int: ...
    @property
    def client_time(self) -> dt.datetime: ...
    @property
    def received_at(self) -> dt.datetime: ...
    @property
    def sent_at(self) -> dt.datetime: ...
    @property
    def time_before(self) -> dt.datetime | None: ...
    @property
    def made_before_by(self) -> uuid.UUID | None: ...
    @property
    def record_before(self) -> uuid.UUID | None: ...
    @property
    def created_by(self) -> StaffMember: ...
    @property
    def carried(self) -> bool: ...


class ClockShape(serializers.Serializer[Any]):
    # A clock document's payload, its shape's version 1: a wrong one is set aside as invalid, with the field that is
    # wrong, and nothing goes in the book. What the worker tapped: in or out.
    kind = serializers.ChoiceField(choices=ClockKind.choices)
    # The last time the server had told the laptop, at a pull before the tap: the evidence for sign 2 of the time
    # check. The laptop keeps it in its `meta` store (03 §6.1) and writes it on the clock-in as it saves it, so it is
    # the one the laptop knew at the tap, not at the push. With its zone, as every time a laptop sends (ATT-1's review).
    last_server_time = ZonedDateTimeField()


class PhotoLabelShape(serializers.Serializer[Any]):
    # A photo's label, as the laptop wrote it (labelPhoto, frontend/src/offline/attachments.ts): the five facts its row
    # is written from, and its file checked against when it comes (CTRL-3). Only their types here: their rules (a JPEG
    # or a WebP, 1 byte to 1 MB, 64 lower-case hex digits) are the row's own, asked by expect_attachment, in one place.
    id = serializers.UUIDField()
    # A clock-in's photo is a clock photo, opened with attendance.manage. Another kind pinned to a line would be a bug
    # in the camera's code, which expect_attachment raises as a server error, not a refusal: so the shape asks first.
    kind = serializers.ChoiceField(choices=[AttachmentKind.CLOCK_PHOTO.value])
    content_type = serializers.CharField()
    size = serializers.IntegerField()
    sha256 = serializers.CharField()


# The reasons a laptop may give for no photo. Not old_app: that one is the server's word for version 1 alone.
REASONS_A_LAPTOP_GIVES = [NoPhoto.NO_CAMERA.value, NoPhoto.BLOCKED.value, NoPhoto.FAILED.value, NoPhoto.DEMO.value]


class ClockShapeV2(ClockShape):
    # A clock document's payload, its shape's version 2 (ATT-3): version 1's, and the tap's photo or why it has none,
    # one or the other. The laptop takes the photo as the worker taps, so it always knows which.
    photo = PhotoLabelShape(required=False)
    no_photo = serializers.ChoiceField(choices=REASONS_A_LAPTOP_GIVES, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Filed under `no_photo` either way, with DRF's own codes: a bug in the laptop's code, which the counter's
        # warning names by its code, as a wrong shape (needs-attention.tsx).
        if "photo" in attrs and "no_photo" in attrs:
            both = ErrorDetail("A tap with a photo has no reason for none.", code="invalid")
            raise serializers.ValidationError({"no_photo": [both]})
        if "photo" not in attrs and "no_photo" not in attrs:
            neither = ErrorDetail("A tap names its photo, or why it has none.", code="required")
            raise serializers.ValidationError({"no_photo": [neither]})
        return attrs


def post_clock_v1(document: Pushed, payload: dict[str, Any]) -> list[Flag]:
    """Save a tap from a laptop still on the app before ATT-3, which names no photo: as a version 2 tap whose reason
    is the old app. Kept until every laptop has updated (03 §6.8): the app's number makes them (SYNC-13)."""
    return post_clock(document, payload | {"no_photo": NoPhoto.OLD_APP})


def _refused_label(refusal: ValidationError) -> ValidationError:
    # The photo's row refused the label the laptop wrote (expect_attachment, CTRL-3). A rule of the photo's own
    # (attachment.too_big, attachment.not_an_image...) refuses the whole tap under its code, so the counter's warning
    # says it in words (needs-attention.tsx), as it says document.* codes, not as a field of "invalid". Anything else
    # (an id this shop already holds) is filed under the payload's `photo`, where the laptop wrote it: so the push
    # answers `photo.id` taken as `id.taken`, as it answers any of the laptop's ids taken (03 §5.4).
    problems = refusal.error_dict if hasattr(refusal, "error_dict") else {NON_FIELD_ERRORS: refusal.error_list}
    for errors in problems.values():
        for error in errors:
            if error.code is not None and error.code.startswith("attachment."):
                return ValidationError(error.message, code=error.code, params=error.params)
    return ValidationError(
        {("photo" if name == NON_FIELD_ERRORS else f"photo.{name}"): errors for name, errors in problems.items()}
    )


def post_clock(document: Pushed, payload: dict[str, Any]) -> list[Flag]:
    """Save one tap of Ingia or Toka in the attendance book, its time checked, and flag it when the time can't be
    trusted; with its photo's row, waiting for the file, or why it has none. The line is its maker's: a worker clocks in
    for themselves, by their PIN (X3)."""
    shop_id = document.device.shop_id
    photo: dict[str, Any] | None = payload.get("photo")
    no_photo = payload.get("no_photo", "")
    if photo is not None and settings.DEMO_SEED:
        # On the demo every visitor shares Meneja's login, which opens clock-in photos, so no visitor's face is kept
        # there (Jack: A). The laptop sends none (attendance.tsx); this is the second lock, should one come all the
        # same: no row, so the server would refuse its file (attachment.not_found), and the line says why.
        photo, no_photo = None, NoPhoto.DEMO
    # The time check, from the evidence the push handed over and the payload's own (apps/staffpay/calculations.py).
    checked = check_time(
        Evidence(
            client_time=document.client_time,
            sent_at=document.sent_at,
            time_before=document.time_before,
            received_at=document.received_at,
            last_server_time=payload["last_server_time"],
            carried=document.carried,
        )
    )
    # Its time later than this tap's, the record before it says a clock moved between the two (sign 1), not whose: so
    # the tap keeps that record's id, and the book sends the day of that record, a tap of Juma's, to review as well
    # (Jack, ATT-11: A). Only for that sign: unverified for another, Juma's Toka timed after the laptop sent it, the
    # tap disagrees with no record, and Neema's day before it stays as it was.
    disagrees_with = document.record_before if Sign.RECORD_BEFORE_IS_LATER in checked.signs else None
    with recording_changes(shop_id):
        # The worker's job, locked for the rest of the push's transaction, before its pay is asked about below: the
        # approval of a month takes every job's row (lock_jobs, WAGE-3). Without it the tap's own link takes only a key
        # share, which never waits for an approval, so a tap that came while Baba approved November could be read by
        # neither: too late for the approval's reads, too early to find the month approved. With it, one waits for the
        # other: the tap is counted by the approval, or finds the month approved and is flagged (WAGE-10). The light
        # lock (backend rules), after the laptop's row, as the push takes that first, and before the change numbers,
        # taken last; the approval takes no laptop's row, so the two never wait for each other in a ring. Every run of
        # the book takes the same rows (lock_jobs): so a tap also waits a moment while an office page works a month out,
        # Mahudhurio ya mwezi, Mishahara or a worker's pay, or the night's job does, as it never did before (the
        # review): a few hundred milliseconds, on a push no person waits on.
        job = StaffMember.objects.select_for_update(no_key=True).get(pk=document.created_by.pk)
        event = AttendanceEvent(
            id=document.id,
            shop_id=shop_id,
            device=document.device,
            device_seq=document.device_seq,
            client_time=document.client_time,
            received_at=document.received_at,
            created_by=document.created_by,
            staff=document.created_by,
            kind=payload["kind"],
            trusted_time=checked.trusted_time,
            time_check=checked.time_check,
            last_server_time=payload["last_server_time"],
            clock_error=checked.clock_error,
            disagrees_with=disagrees_with,
            no_photo=no_photo,
        )
        # An INSERT, never an UPDATE: the id comes from the laptop, and one another shop already holds must clash on
        # the primary key, not overwrite that shop's line (03 §5.4).
        event.save(force_insert=True)
        record_change(event)
        if photo is not None:
            # The photo's row, pinned to the line, in the push's own transaction for this tap: kept with the line or
            # not at all, so a file that comes later always finds its row, and a refused label leaves no line behind
            # whose photo could never come (CTRL-3). After the line, as a row's record must be saved first. Taken by
            # the worker who tapped, and named by the line's own laptop, the one whose key sent the push: for a tap
            # carried in a rescue file (SYNC-12), the laptop that loaded it, not the one that took the photo, as the
            # line names it too. No change line: no laptop keeps a copy of photos' rows.
            try:
                expect_attachment(
                    id=photo["id"],
                    kind=photo["kind"],
                    subject=event,
                    content_type=photo["content_type"],
                    size=photo["size"],
                    sha256=photo["sha256"],
                    by=document.created_by,
                    device=document.device,
                )
            except ValidationError as refusal:
                raise _refused_label(refusal) from refusal
    flags = [] if checked.time_check != TimeCheck.UNVERIFIED else [_unverified(document, event, checked.signs)]
    # The day the tap falls on, as the book places it (where_it_falls): by the time trusted, or the laptop's for one in
    # doubt. Its pay approved already, for the job, with its month or alone as they left (is_closed): the tap is kept
    # and counts for nothing, and the flag says so, naming the worker, on no side, as attendance is the whole shop's
    # (02 §13, WAGE-10). One per tap, beside the time's flag when both hold. Read under the job's lock, taken above.
    shop = document.device.shop
    day, _ = where_it_falls(event.trusted_time, event.client_time, ZoneInfo(shop.timezone))
    if is_closed(shop, day, job.pk):
        flags.append(raise_flag(kind=FlagKind.LATE_RECORD, subject=event, people=[document.created_by], by=None))
    return flags


def _unverified(document: Pushed, event: AttendanceEvent, signs: frozenset[Sign]) -> Flag:
    # A sign the laptop's clock moved, or a record carried in a rescue file: the line is kept, and flagged for a
    # manager, naming the worker (02 §12, SYNC-12). On no side: attendance belongs to the whole shop, as its rules do,
    # so the flag is the shop's. A carried one has no sign 1, so its flag names nobody else.
    people = [document.created_by]
    # Sign 1 says two records disagree, not whose clock moved: back for this tap, or forward for the one before. So the
    # flag names that record's maker too, for a manager to check both (Jack, ATT-1's review). Read only now, through
    # the shop's guard, as a flag is rare; someone the guard can't find is left out.
    if Sign.RECORD_BEFORE_IS_LATER in signs and document.made_before_by is not None:
        people.extend(StaffMember.objects.filter(pk=document.made_before_by))
    return raise_flag(kind=FlagKind.UNVERIFIED_TIME, subject=event, people=people, by=None)
