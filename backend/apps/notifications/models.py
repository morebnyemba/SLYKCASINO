from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        BET_WON = 'bet_won', 'Bet won'
        BET_LOST = 'bet_lost', 'Bet lost'
        DEPOSIT_CONFIRMED = 'deposit_confirmed', 'Deposit confirmed'
        WITHDRAWAL_PROCESSED = 'withdrawal_processed', 'Withdrawal processed'
        BONUS_CREDITED = 'bonus_credited', 'Bonus credited'
        PROMO_EXPIRING = 'promo_expiring', 'Promotion expiring soon'
        ACCOUNT_ALERT = 'account_alert', 'Account alert'

    player_id = models.IntegerField(db_index=True)
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=120)
    body = models.TextField(blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['player_id', 'read'], name='notif_player_read_idx')]
