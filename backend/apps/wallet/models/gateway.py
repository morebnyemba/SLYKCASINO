from django.db import models


class PaymentGateway(models.Model):
    """The live payment gateway and its credentials, set from the admin
    console (one row). Blank fields fall back to the server environment
    (PSP_PROVIDER, PAYNOW_*), so a deployment configured by env keeps working
    until an operator saves something here."""

    class Provider(models.TextChoices):
        SERVER = '', 'Use the server setting'
        STUB = 'stub', 'Test processor (no money moves)'
        PAYNOW = 'paynow', 'Paynow'

    provider = models.CharField(max_length=10, choices=Provider.choices, blank=True, default='')
    paynow_integration_id = models.CharField(max_length=20, blank=True)
    paynow_integration_key = models.CharField(max_length=100, blank=True)
    paynow_auth_email = models.EmailField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by_username = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'wallet_paymentgateway'

    def __str__(self) -> str:
        return self.provider or 'server setting'

    @classmethod
    def load(cls) -> 'PaymentGateway':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def current(cls) -> 'PaymentGateway | None':
        """The saved row, or None (no query error before migrations run)."""
        try:
            return cls.objects.filter(pk=1).first()
        except Exception:  # noqa: BLE001 — table missing during migrate
            return None
