from django.db import models


class Promotion(models.Model):
    """A promotion offer. `wagering_multiplier` is how many times the bonus must
    be wagered before it can be withdrawn."""

    class Kind(models.TextChoices):
        DEPOSIT = 'deposit', 'Deposit Bonus'
        FREEBET = 'freebet', 'Free Bet'
        CASHBACK = 'cashback', 'Cashback'

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.DEPOSIT)
    active = models.BooleanField(default=True)
    bonus_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    wagering_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    code = models.CharField(max_length=100, blank=True)
    terms_html = models.TextField(blank=True)

    class Meta:
        db_table = 'promotions_promotion'
        ordering = ['-active', 'name']

    def __str__(self) -> str:
        return self.name
