from django.db import models


class AuditLog(models.Model):
    class EventType(models.TextChoices):
        LOGIN = 'login', 'Login'
        LOGOUT = 'logout', 'Logout'
        REGISTER = 'register', 'Register'
        DEPOSIT = 'deposit', 'Deposit'
        WITHDRAWAL = 'withdrawal', 'Withdrawal'
        BET_PLACED = 'bet_placed', 'Bet placed'
        BET_SETTLED = 'bet_settled', 'Bet settled'
        CASINO_SPIN = 'casino_spin', 'Casino spin'
        PROMO_CLAIM = 'promo_claim', 'Promotion claimed'
        SELF_EXCLUDE = 'self_exclude', 'Self-exclusion'
        LIMIT_SET = 'limit_set', 'Deposit limit set'
        EMAIL_VERIFIED = 'email_verified', 'Email verified'
        PASSWORD_RESET = 'password_reset', 'Password reset'
        DATA_EXPORT = 'data_export', 'Data export'
        ACCOUNT_DELETED = 'account_deleted', 'Account deleted'

    player_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    event_type = models.CharField(max_length=30, choices=EventType.choices, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'accounts_audit_log'
        ordering = ['-created_at']
