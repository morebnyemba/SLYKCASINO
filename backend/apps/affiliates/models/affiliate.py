from django.db import models


class Affiliate(models.Model):
    """A player who refers others for a share of the revenue they bring.
    `player_id` references accounts.Player (no cross-app FK). Rates are per
    affiliate so an operator can negotiate deals; defaults come from settings."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending approval'
        ACTIVE = 'active', 'Active'
        SUSPENDED = 'suspended', 'Suspended'
        REJECTED = 'rejected', 'Rejected'

    player_id = models.BigIntegerField(unique=True)
    code = models.CharField(max_length=24, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # Share of referred players' net gaming revenue, paid per calendar month.
    revshare_percent = models.DecimalField(max_digits=5, decimal_places=2)
    # One-off payment per referral once their deposits reach cpa_min_deposit (0 = off).
    cpa_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cpa_min_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Deposit commission: this % of a referral's FIRST deposit, paid once (with
    # cpa_amount) when they qualify, capped per referral at cpa_cap (0 = no cap).
    cpa_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cpa_cap = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    website = models.CharField(max_length=200, blank=True)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'affiliates_affiliate'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.code} ({self.status})'


class AffiliateClick(models.Model):
    """A visit through an affiliate link (counted once per browser session)."""

    affiliate = models.ForeignKey(Affiliate, on_delete=models.CASCADE, related_name='clicks')
    campaign = models.CharField(max_length=50, blank=True)
    landing = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'affiliates_click'
        indexes = [models.Index(fields=['affiliate', 'created_at'])]


class Referral(models.Model):
    """A player who signed up through an affiliate. A player belongs to at most
    one affiliate, fixed at registration."""

    affiliate = models.ForeignKey(Affiliate, on_delete=models.CASCADE, related_name='referrals')
    player_id = models.BigIntegerField(unique=True)
    campaign = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'affiliates_referral'
        ordering = ['-created_at']


class Commission(models.Model):
    """Money owed to an affiliate: a month's revenue share, or a CPA for one
    referral. PENDING -> APPROVED (by an operator, or automatically) -> PAID once
    the keyed wallet credit lands; or REJECTED."""

    class Kind(models.TextChoices):
        REVSHARE = 'revshare', 'Revenue share'
        CPA = 'cpa', 'CPA'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending review'
        APPROVED = 'approved', 'Approved (paying)'
        PAID = 'paid', 'Paid'
        REJECTED = 'rejected', 'Rejected'

    affiliate = models.ForeignKey(Affiliate, on_delete=models.PROTECT, related_name='commissions')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    # First day of the month a revenue share covers (null for CPA).
    period = models.DateField(null=True, blank=True)
    referral = models.ForeignKey(Referral, null=True, blank=True, on_delete=models.PROTECT, related_name='commissions')
    # What the commission was computed from: net gaming revenue (revshare) or
    # total deposits (CPA), plus the rate applied.
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    active_players = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'affiliates_commission'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['affiliate', 'period'], condition=models.Q(kind='revshare'),
                name='one_revshare_per_affiliate_month',
            ),
            models.UniqueConstraint(
                fields=['referral'], condition=models.Q(kind='cpa'), name='one_cpa_per_referral',
            ),
        ]
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self) -> str:
        return f'{self.kind} {self.amount} for {self.affiliate_id} ({self.status})'


class AffiliateProgramme(models.Model):
    """Programme-wide settings (one row, edited in the admin): the welcome
    bonus referred players get on their first deposit, the terms new
    affiliates start on, when a deposit commission qualifies, and whether a
    losing month is carried into the next revenue share."""

    # Referred players: bonus of this % of their first deposit, capped, as
    # bonus money that must be wagered `welcome_bonus_wagering` times before
    # it can be withdrawn. 0% = off.
    welcome_bonus_percent = models.DecimalField(max_digits=5, decimal_places=2, default=30)
    welcome_bonus_cap = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    welcome_bonus_wagering = models.DecimalField(max_digits=5, decimal_places=2, default=5)
    welcome_bonus_min_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    # Terms a new affiliate starts with (each affiliate can be changed after).
    default_revshare_percent = models.DecimalField(max_digits=5, decimal_places=2, default=25)
    default_cpa_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    default_cpa_min_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=20)
    default_cpa_percent = models.DecimalField(max_digits=5, decimal_places=2, default=30)
    default_cpa_cap = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    # A deposit commission is only earned once the referral has staked at
    # least this many times their first deposit (stops deposit-and-withdraw farming).
    cpa_min_turnover_multiple = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    # Carry a losing month (negative net revenue) into the next months'
    # revenue share until it has been earned back.
    negative_carryover = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'affiliates_programme'

    @classmethod
    def load(cls) -> 'AffiliateProgramme':
        from django.conf import settings
        obj, created = cls.objects.get_or_create(pk=1, defaults={
            'default_revshare_percent': getattr(settings, 'AFFILIATE_DEFAULT_REVSHARE', 25),
            'default_cpa_amount': getattr(settings, 'AFFILIATE_DEFAULT_CPA', 0),
            'default_cpa_min_deposit': getattr(settings, 'AFFILIATE_DEFAULT_CPA_MIN_DEPOSIT', 20),
        })
        if created:
            obj.refresh_from_db()  # in-memory defaults are ints/floats; read back proper Decimals
        return obj


class RevshareMonth(models.Model):
    """One closed month of an affiliate's revenue share: the month's net
    revenue, the losing balance carried in from before, and what is carried
    out (negative or zero). Makes month-closing idempotent, including for
    losing months that pay nothing."""

    affiliate = models.ForeignKey(Affiliate, on_delete=models.CASCADE, related_name='revshare_months')
    period = models.DateField()
    ngr = models.DecimalField(max_digits=14, decimal_places=2)
    carried_in = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    carry_out = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    commission = models.OneToOneField(Commission, null=True, blank=True, on_delete=models.SET_NULL, related_name='month')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'affiliates_revshare_month'
        ordering = ['-period']
        constraints = [models.UniqueConstraint(fields=['affiliate', 'period'], name='one_revshare_month_per_affiliate')]
