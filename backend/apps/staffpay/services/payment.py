"""apps/staffpay/services/payment.py — handing out a month's pay, once it is approved (WAGE-9; 02 §12, A5): a payslip
marked paid, with its proof, and a payment marked by mistake crossed out.

    2 Dec, 08:10, Baba gives Asha her November, 152,000, in cash; she draws her signature on his phone; he taps
    Nimemlipa:
        PayslipPayment  Asha, Novemba  152,000  cash, by Baba
        Attachment      signature, pinned to it, kept for ever
    08:20, Baraka is paid by M-Pesa:
        PayslipPayment  Baraka, Novemba  148,000  mobile_money QK7H2M9XPL, by Baba

    09:00, he sees he tapped Lipa beside Juma, not Baraka, and crosses it out: "Nilibonyeza mfanyakazi mwingine"; the
    payment and its signature stay, struck through, and Juma's payslip waits for Lipa again.

The whole amount, at once (Jack: A), and only once a payslip says what it is: approving and paying are two moments
(WAGE-3). Who may: whoever holds `pay.run` with the two keys of pay, on the whole shop, never on their own pay. No line
in the change log: no laptop keeps a payslip (03 §6.1).
"""

import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.control.models import Attachment, AttachmentKind
from apps.control.services import adding_attachment
from apps.core.permissions import Permission
from apps.core.tenancy import ShopMismatch
from apps.people.models import StaffMember
from apps.people.permissions import require
from apps.staffpay.calculations import cash_to_pay
from apps.staffpay.models import NoSignature, PaymentMethod, Payslip, PayslipPayment

# The keys whoever hands out pay must hold, on the whole shop: `pay.run`, every manager's, as handing out is a job of
# its own, apart from approving (`pay.approve`, the owner's); and the two keys of pay, as nobody hands out what they may
# not read (WAGE-1's review: A). The signature is what proves the money reached the worker, not the key.
PAYS = (Permission.PAY_RUN, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE)

# A transaction number as the owner finds it on his statement: letters and digits, and the dashes and slashes a bank's
# reference may hold. Written in capitals, with no spaces, so "qk7h 2m9xpl" and "QK7H2M9XPL" are one number, and the
# rule that a number counts once can't be passed by typing it another way.
_NUMBER = re.compile(r"^[A-Z0-9/-]+$")


def pay_payslip(
    payslip: Payslip,
    *,
    payment_id: uuid.UUID,
    method: PaymentMethod,
    reference: str = "",
    signature_id: uuid.UUID | None = None,
    signature: bytes | None = None,
    by: StaffMember,
) -> PayslipPayment:
    """Mark `payslip` handed out, all of it, with its proof (WAGE-9, Jack: A). `payment_id`: the client's (ADR-0007),
    so a request sent twice is answered with the payment it made. `method`: cash, mobile money or a bank. In cash, the
    worker's signature, the drawing's id (`signature_id`, the client's) and its JPEG bytes (`signature`), on the demo
    none; otherwise the transaction number (`reference`). `by`: who hands it out, with pay.run and the two keys of pay
    on the whole shop, never the worker. Refuses: one's own (payment.own); a payslip that pays nothing
    (payment.nothing_to_pay); one paid already (payment.already_paid); cash with no signature
    (payment.signature_missing), or on the demo with one (demo.no_signature); and beside the number's box, none
    (payment.reference_missing), one that is no number (payment.reference_invalid), or one counted already
    (payment.reference_used). Returns the payment as saved."""
    # A job of another shop handing out this shop's pay is a bug in the calling code (T1), never a person's mistake: the
    # route finds both in the one shop open. A server error, before anything is read.
    if by.shop_id != payslip.shop_id:
        raise ShopMismatch("pay_payslip was given a person of another shop.")
    # What a route hands in: a signature only with cash, and both its halves, as each route sends one way of paying. A
    # bug in the calling code, never the person's: the sheet never sends both.
    if method == PaymentMethod.CASH and reference:
        raise ValueError("Cash is paid with a signature, never a transaction number.")
    if method != PaymentMethod.CASH and (signature is not None or signature_id is not None):
        raise ValueError("Only cash is paid with a signature.")
    if (signature is None) != (signature_id is None):
        raise ValueError("A signature comes with its id.")
    reference = "".join(reference.split()).upper()
    # Not a recording_changes block: a payment writes no line in the change log, as no laptop gets one (03 §6.1).
    with transaction.atomic():
        by, slip = _locked(payslip.pk, by)
        # Sent twice, its first answer lost: the payment it made, as it is now, whatever came since.
        made = PayslipPayment.objects.filter(pk=payment_id, payslip=slip).first()
        if made is not None:
            return made
        # An id this shop holds already, on another payslip's payment or another photo: told as one held anywhere is,
        # id.taken, so the answer never says which shop holds it (03 §5.4). Another shop's is found only by the insert,
        # which the route says the same way (_refusing_a_taken_id). Never sent by the app, which makes each id new.
        if PayslipPayment.objects.filter(pk=payment_id).exists() or (
            signature_id is not None and Attachment.objects.filter(pk=signature_id).exists()
        ):
            raise ValidationError({"id": [ValidationError("This id is already in use.", code="id.taken")]})
        # Never one's own (02 A5): Meneja marking his own November paid proves nothing, signed or not. By the person,
        # not the job, as an advance's: someone hired again has two jobs, and neither's pay is theirs to hand out.
        if StaffMember.objects.get(pk=slip.staff_id).user_id == by.user_id:
            raise ValidationError("Nobody marks their own pay paid.", code="payment.own")
        # A payslip below 0 pays nothing (WAGE-3, Jack: A): nothing to hand over, and nothing to sign for.
        amount = cash_to_pay(slip.total)
        if amount <= 0:
            raise ValidationError("This payslip pays nothing.", code="payment.nothing_to_pay")
        # Read under the payslip's lock: two people tapping Nimemlipa at once take turns, and the second finds it paid.
        if PayslipPayment.objects.filter(payslip=slip, voided_at__isnull=True).exists():
            raise ValidationError("This payslip is paid already.", code="payment.already_paid")
        no_signature = _check_proof(slip, method, reference, signature)
        row = PayslipPayment(
            id=payment_id,
            shop_id=slip.shop_id,
            payslip=slip,
            staff_id=slip.staff_id,
            amount=amount,
            method=method,
            reference=reference,
            no_signature=no_signature,
            created_by=by,
        )
        # The row's own checks of its fields, as a guard on what was asked above: a choice or a length. Not its unique
        # rules or its checks, which the insert's own refusal says (_insert): asked here, a number another commit took a
        # moment ago would come back under no box, and an id as a word no screen has.
        row.full_clean(validate_unique=False, validate_constraints=False)
        _insert(row)
        if signature is not None and signature_id is not None:
            # The drawing last, its file after its row (adding_attachment), so a payment refused leaves no file. A
            # drawing that is no JPEG, or past 1 MB, is refused here, and the payment with it: cash is never unsigned.
            with adding_attachment(
                id=signature_id, kind=AttachmentKind.SIGNATURE, subject=row, content=signature, by=by
            ):
                pass
    return row


def _locked(payslip_id: uuid.UUID, by: StaffMember) -> tuple[StaffMember, Payslip]:
    # Who pays, asked before anything is locked, so someone without a key sets nothing to work and holds nobody up; and
    # asked again of their own row, locked: Baba takes Meneja's key away while Meneja taps Nimemlipa. Taking a key holds
    # Meneja's job's row, which this waits for, so asked only before it, a key he no longer holds would mark the payment
    # for good (AUTH-8's order, as the approval keeps it). Then the payslip, locked, so two payments of it take turns.
    # FOR NO KEY UPDATE, the light lock (backend rules): the payment's own link to its payslip takes a lock that never
    # waits for it. Always the person first, then the payslip, so two people paying never wait for each other in a ring.
    _ask_who_pays(by)
    by = StaffMember.objects.select_for_update(no_key=True).get(pk=by.pk)
    _ask_who_pays(by)
    return by, Payslip.objects.select_for_update(no_key=True).get(pk=payslip_id)


def _ask_who_pays(by: StaffMember) -> None:
    for key in PAYS:
        require(by, key, None)


def _check_proof(slip: Payslip, method: PaymentMethod, reference: str, signature: bytes | None) -> NoSignature | str:
    # The proof each way of paying needs (Jack, 26 Nov 2026), and what the row says of a signature: "demo" on the
    # demo's cash, empty everywhere else.
    if method == PaymentMethod.CASH:
        if settings.DEMO_SEED:
            # On the demo every visitor logs in as Meneja (OPS-3), so a signature kept would show to every visitor
            # after, as a visitor's photo would (Jack, ATT-3 and PPL-9: none is kept). The visitor draws, and nothing is
            # sent.
            if signature is not None:
                raise ValidationError("On the demo, no signature is kept.", code="demo.no_signature")
            return NoSignature.DEMO
        if signature is None:
            # A payment marked by one person alone proves nothing: the worker signs, as on paper today (Jack: A).
            raise ValidationError("Cash is paid with the worker's signature.", code="payment.signature_missing")
        return ""
    # M-Pesa and a bank: the number the owner finds on his statement, beside its box.
    if not reference:
        refusal = ValidationError("A transaction number is needed.", code="payment.reference_missing")
    elif not _NUMBER.match(reference):
        refusal = ValidationError("A transaction number is letters and digits.", code="payment.reference_invalid")
    elif PayslipPayment.objects.filter(
        shop_id=slip.shop_id, method=method, reference=reference, voided_at__isnull=True
    ).exists():
        # One real payment never stands for two (01 §7.5): the same code typed on Juma's payslip and Baraka's.
        refusal = ValidationError("This transaction number is used already.", code="payment.reference_used")
    else:
        return ""
    raise ValidationError({"reference": [refusal]})


def _insert(row: PayslipPayment) -> None:
    # An INSERT, never an UPDATE: an id another row holds clashes, loudly, and never overwrites it (03 §5.4). The number
    # was asked as free above, but two people paying two payslips with the same number at once each hold only their
    # own payslip's lock, so both may find it free: the table's rule then refuses the second, and it is said as the
    # same refusal, beside its box, not as a server error. A savepoint of its own, so the refusal leaves the rest of
    # the transaction whole.
    try:
        with transaction.atomic():
            row.save(force_insert=True)
    except IntegrityError as clash:
        if "staffpay_payslippayment_number_counted_once" not in str(clash):
            raise
        refusal = ValidationError("This transaction number is used already.", code="payment.reference_used")
        raise ValidationError({"reference": [refusal]}) from None


# The ready reason a payment is crossed out with on the demo, where every visitor is the same Meneja, so typed words
# would show to the next one (as an advance's, WAGE-8); the page says it in words. Elsewhere the reason is typed.
DEMO_PAYMENT_VOID_REASONS = ("marked_by_mistake",)


def keeps_signatures() -> bool:
    """Whether a payment in cash is sent with its signature: everywhere but the demo, which keeps none (WAGE-9). The
    Lipa sheet asks it first, so on the demo the visitor draws and nothing is sent."""
    return not settings.DEMO_SEED


def ready_payment_void_reasons() -> list[str]:
    """The ready reason a payment may be crossed out with, for the sheet to offer: the demo's, or none elsewhere, where
    it is typed."""
    return list(DEMO_PAYMENT_VOID_REASONS) if settings.DEMO_SEED else []


def void_payslip_payment(payment: PayslipPayment, *, reason: str, by: StaffMember) -> PayslipPayment:
    """Cross out a payment marked by mistake (WAGE-9, 02 §12, T2): Baba tapped Lipa beside Juma when he paid Asha. The
    row stays, voided once with who, when and why, and counts for nothing, its signature kept with it; the payslip waits
    for Lipa again. Never brought back. `by`: who crosses it out, with pay.run and the two keys of pay on the whole
    shop, whoever marked it, and never the worker it paid. A payment crossed out already, by this request sent twice or
    by someone a moment before, is answered as it was crossed out, never stamped again. Refuses: one's own
    (payment.own); and, beside the reason's box, no reason (payment.reason_missing), or on the demo a reason not the
    ready one (demo.ready_reasons). Returns the row as saved."""
    # Who voids is a staff member of the row's own shop (T1): the void rule in the database checks only that the stamp
    # is filled whole, so this is the check it can't make with one column.
    if by.shop_id != payment.shop_id:
        raise ShopMismatch("void_payslip_payment was given a person of another shop.")
    reason = reason.strip()
    with transaction.atomic():
        # The same locks as paying, in the same order: the person, asked again under theirs, then the payslip, so a
        # crossing out and a new payment of the same payslip take turns, and the new one finds the old one gone.
        by, _ = _locked(payment.payslip_id, by)
        # Never one's own (02 A5): crossing out his own payment would let Juma be paid twice. By the person, as paying.
        if StaffMember.objects.get(pk=payment.staff_id).user_id == by.user_id:
            raise ValidationError("Nobody crosses out their own payment.", code="payment.own")
        if not reason:
            raise ValidationError(
                {"reason": [ValidationError("A payment crossed out says why.", code="payment.reason_missing")]}
            )
        if settings.DEMO_SEED and reason not in DEMO_PAYMENT_VOID_REASONS:
            raise ValidationError(
                {"reason": [ValidationError("On the demo, pick the ready reason.", code="demo.ready_reasons")]}
            )
        # The stamp, filled once, by one guarded UPDATE, as an advance's (void_advance): only while the row counts, so
        # two crossings out never both write it. Never save(), which AppendOnly refuses; the void trigger lets this
        # UPDATE change the stamp and nothing else (ADR-0021).
        PayslipPayment.objects.filter(pk=payment.pk, voided_at__isnull=True).update(
            voided_at=timezone.now(), voided_by=by, void_reason=reason
        )
        # Read back as it is now: crossed out by this request, by the same one sent before, its answer lost, or by
        # someone a moment before, whose stamp the page is then shown.
        return PayslipPayment.objects.get(pk=payment.pk)
