"""House revenue share: three partner wallets that each take a share (10% by
default) of every day's GGR, and an operating pool (the rest, 70%) that
covers costs — affiliate commissions automatically, plus expenses staff record
(Claude, hosting, SMS…).

Kept entirely apart from player wallets: these are the house's own books. The
actual money stays in the operator's accounts; this ledger says who is owed
what. Every balance is the sum of append-only entries.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

WALLET_SLOTS = (1, 2, 3)


class RevenueSettings(models.Model):
    """One row. `share_percent` is each wallet's share of a day's GGR;
    `started_on` is the first day that counts (days before it are never shared)."""
    share_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))
    started_on = models.DateField(null=True, blank=True)
    # Uploads the weekly Paynow and payouts reports and signs each week off.
    # Unset: whoever holds Partner 1's wallet.
    founder = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='+')
    # Weekly audits are due (and missed ones count towards the lock) from this week on.
    audits_from = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'revenue_settings'

    @classmethod
    def load(cls) -> 'RevenueSettings':
        today = timezone.localdate()
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'started_on': today,
                                                            'audits_from': today - timedelta(days=today.weekday())})
        return obj


class ShareWallet(models.Model):
    """A partner's 10% wallet, held by one staff login (who sees it and asks for
    its withdrawal). A slot with no holder still accrues, claimable once assigned."""
    slot = models.PositiveSmallIntegerField(unique=True)
    holder = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name='share_wallet')
    label = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'revenue_share_wallet'
        ordering = ['slot']

    @classmethod
    def ensure(cls) -> list['ShareWallet']:
        for slot in WALLET_SLOTS:
            cls.objects.get_or_create(slot=slot, defaults={'label': f'Partner {slot}'})
        return list(cls.objects.filter(slot__in=WALLET_SLOTS).select_related('holder'))


class RevenueDay(models.Model):
    """One closed day. A losing day's loss is carried forward and netted against
    the next winning days before anything is shared (`carried_in` <= 0,
    `carry_out` <= 0); `base` is what was shared out: each wallet `share_each`,
    the pool the rest. Closed once, never edited."""
    day = models.DateField(unique=True)
    # Real-money GGR: cash stakes minus cash wins, less bonus money that turned
    # into withdrawable Winnings that day (see services.day_ggr).
    ggr = models.DecimalField(max_digits=14, decimal_places=2)
    bonus_conversions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    carried_in = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    base = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    carry_out = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    share_percent = models.DecimalField(max_digits=5, decimal_places=2)
    share_each = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pool = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Affiliate commissions that became final this day, charged to the pool.
    affiliate_costs = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    closed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'revenue_day'
        ordering = ['-day']


class ShareWithdrawal(models.Model):
    """A holder asks for their wallet: the whole balance, which resets to zero at
    once. Staff send the money and mark it paid; a rejected one goes back."""

    class Status(models.TextChoices):
        REQUESTED = 'requested', 'Requested'
        PAID = 'paid', 'Paid'
        REJECTED = 'rejected', 'Rejected'

    class Method(models.TextChoices):
        ECOCASH = 'ecocash', 'EcoCash'
        ONEMONEY = 'onemoney', 'OneMoney'
        INNBUCKS = 'innbucks', 'InnBucks'
        BANK = 'bank', 'Bank transfer'
        CASH = 'cash', 'Cash'

    wallet = models.ForeignKey(ShareWallet, on_delete=models.PROTECT, related_name='withdrawals')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    method = models.CharField(max_length=10, choices=Method.choices)
    account = models.CharField(max_length=120, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=500, blank=True)
    requested_by = models.CharField(max_length=150)
    decided_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'revenue_share_withdrawal'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['wallet'], condition=Q(status='requested'),
                                    name='revenue_one_open_withdrawal_per_wallet'),
        ]


class ShareEntry(models.Model):
    """Append-only movements on a share wallet. Balance = the sum of amounts."""

    class Kind(models.TextChoices):
        ACCRUAL = 'accrual', 'Daily share'
        WITHDRAWAL = 'withdrawal', 'Withdrawal'
        RETURN = 'return', 'Withdrawal rejected'
        POOL = 'pool', 'Paid out of the pool (agreed by all partners)'

    wallet = models.ForeignKey(ShareWallet, on_delete=models.PROTECT, related_name='entries')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    day = models.ForeignKey(RevenueDay, null=True, blank=True, on_delete=models.PROTECT, related_name='entries')
    withdrawal = models.ForeignKey(ShareWithdrawal, null=True, blank=True, on_delete=models.PROTECT, related_name='entries')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'revenue_share_entry'
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['wallet', 'day'], condition=Q(kind='accrual'), name='revenue_one_accrual_per_day'),
            models.UniqueConstraint(fields=['withdrawal', 'kind'], condition=Q(withdrawal__isnull=False),
                                    name='revenue_one_entry_per_withdrawal_kind'),
        ]


class PoolExpense(models.Model):
    """A cost paid out of the operating pool (affiliate commissions are counted
    automatically and aren't entered here)."""

    class Category(models.TextChoices):
        AI = 'ai', 'Claude / AI'
        HOSTING = 'hosting', 'Hosting & servers'
        SMS = 'sms', 'SMS & messaging'
        PAYMENTS = 'payments', 'Payment fees'
        DATA = 'data', 'Odds & data feeds'
        MARKETING = 'marketing', 'Marketing'
        STAFF = 'staff', 'Staff'
        OTHER = 'other', 'Other'
        PROMOTION = 'promotion', 'Promotion (agreed by all partners)'
        DISBURSE = 'disburse', 'Paid to partners equally (agreed by all)'

    day = models.DateField()
    category = models.CharField(max_length=10, choices=Category.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=300, blank=True)
    recorded_by = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'revenue_pool_expense'
        ordering = ['-day', '-id']


class PoolAudit(models.Model):
    """One week (Monday to Sunday) of the pool, due by the end of the next
    Tuesday. The founder submits Paynow's report of money received, the
    EcoCash/bank statement of money paid to players, and the pool balance they
    actually hold after the costs they claim; each report is matched line by
    line against the platform. Every partner then co-signs or disputes. Once
    all have approved, the week's figures are frozen and its costs locked. Two
    missed weeks in a row lock the money controls until the audits catch up."""

    class Status(models.TextChoices):
        OPEN = 'open', 'Waiting for the founder'
        SUBMITTED = 'submitted', 'Waiting for partners to co-sign'
        DISPUTED = 'disputed', 'Disputed by a partner'
        APPROVED = 'approved', 'Approved by every partner'

    class Source(models.TextChoices):
        ECOCASH = 'ecocash', 'EcoCash statement'
        BANK = 'bank', 'Bank statement'
        ONEMONEY = 'onemoney', 'OneMoney statement'
        INNBUCKS = 'innbucks', 'InnBucks statement'

    week_start = models.DateField(unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    paynow_file = models.FileField(upload_to='pool-audits/%Y/', blank=True)
    paynow_result = models.JSONField(default=dict, blank=True)
    payouts_file = models.FileField(upload_to='pool-audits/%Y/', blank=True)
    payouts_result = models.JSONField(default=dict, blank=True)
    payouts_source = models.CharField(max_length=10, choices=Source.choices, blank=True)
    # What the founder says the pool actually holds at the week's end, after the
    # costs they claim — against what the platform's ledger says it should be.
    declared_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    expected_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # The platform's own figures, frozen at approval (live until then).
    snapshot = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=1000, blank=True)
    uploaded_by = models.CharField(max_length=150, blank=True)
    submitted_by = models.CharField(max_length=150, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'revenue_pool_audit'
        ordering = ['-week_start']


class Decision(models.TextChoices):
    APPROVE = 'approve', 'Approved'
    REJECT = 'reject', 'Disputed / rejected'


class AuditSignature(models.Model):
    """A partner's co-signature on a submitted week (the founder's submission
    counts as theirs). Cleared when the founder resubmits."""

    audit = models.ForeignKey(PoolAudit, on_delete=models.CASCADE, related_name='signatures')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    decision = models.CharField(max_length=8, choices=Decision.choices)
    note = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'revenue_audit_signature'
        constraints = [models.UniqueConstraint(fields=['audit', 'user'], name='revenue_one_signature_per_partner')]


class PoolProposal(models.Model):
    """Using the pool: a promotion, or paying it out to the three partner wallets
    equally. Happens only when every partner has approved."""

    class Kind(models.TextChoices):
        PROMOTION = 'promotion', 'Fund a promotion'
        DISBURSE = 'disburse', 'Pay out to every partner equally'

    class Status(models.TextChoices):
        OPEN = 'open', 'Waiting for every partner'
        DONE = 'done', 'Approved and carried out'
        REJECTED = 'rejected', 'Rejected'
        CANCELLED = 'cancelled', 'Withdrawn'

    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=500)
    proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    expense = models.OneToOneField(PoolExpense, null=True, blank=True, on_delete=models.PROTECT, related_name='proposal')
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'revenue_pool_proposal'
        ordering = ['-created_at']


class ProposalVote(models.Model):
    proposal = models.ForeignKey(PoolProposal, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    decision = models.CharField(max_length=8, choices=Decision.choices)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'revenue_proposal_vote'
        constraints = [models.UniqueConstraint(fields=['proposal', 'user'], name='revenue_one_vote_per_partner')]
