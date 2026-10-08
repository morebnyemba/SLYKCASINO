from django.db import models


class PaymentMethod(models.Model):
    """A deposit option as players see it, edited from the admin console.

    `code` ties the method to what the payment gateway can process (Paynow
    takes ecocash/onemoney/innbucks/card), so a method the live gateway can't
    take is never offered for deposits even if it's switched on — it can
    still be shown as a footer badge.
    """

    class Field(models.TextChoices):
        PHONE = 'phone', 'Mobile number'
        CARD = 'card', 'Card'
        CRYPTO = 'crypto', 'Crypto address'
        NONE = 'none', 'Nothing to enter'

    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=60)
    # The line under the name on the deposit screen, e.g. "Mobile money".
    description = models.CharField(max_length=120, blank=True)
    speed = models.CharField(max_length=30, blank=True, default='Instant')
    logo_text = models.CharField(max_length=3, blank=True)
    color = models.CharField(max_length=7, default='#4f46e5', help_text='Logo tile colour, #rrggbb.')
    field = models.CharField(max_length=8, choices=Field.choices, default=Field.PHONE)
    deposit_enabled = models.BooleanField(default=True)
    show_in_footer = models.BooleanField(default=True)
    min_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    max_deposit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wallet_paymentmethod'
        ordering = ['sort_order', 'name']

    def __str__(self) -> str:
        return self.name
