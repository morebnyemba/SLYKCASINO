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
        EVENT_SETTLED = 'event_settled', 'Event settled (result)'
        EVENT_SETTLED_SCORE = 'event_settled_score', 'Event settled (score)'
        MARKET_SETTLED = 'market_settled', 'Market settled'
        CASINO_SPIN = 'casino_spin', 'Casino spin'
        PROMO_CLAIM = 'promo_claim', 'Promotion claimed'
        SELF_EXCLUDE = 'self_exclude', 'Self-exclusion'
        LIMIT_SET = 'limit_set', 'Deposit limit set'
        EMAIL_VERIFIED = 'email_verified', 'Email verified'
        PASSWORD_RESET = 'password_reset', 'Password reset'
        DATA_EXPORT = 'data_export', 'Data export'
        ACCOUNT_DELETED = 'account_deleted', 'Account deleted'
        KYC_SUBMITTED = 'kyc_submitted', 'KYC document submitted'
        KYC_APPROVED = 'kyc_approved', 'KYC approved'
        KYC_REJECTED = 'kyc_rejected', 'KYC rejected'
        PLAYER_SUSPENDED = 'player_suspended', 'Player suspended'
        PLAYER_UNSUSPENDED = 'player_unsuspended', 'Player unsuspended'
        BALANCE_ADJUSTED = 'balance_adjusted', 'Balance adjusted'
        THEME_UPDATED = 'theme_updated', 'Site theme updated'
        IDENTITY_UPDATED = 'identity_updated', 'Site identity updated'
        AFFILIATE_APPLIED = 'affiliate_applied', 'Affiliate applied'
        AFFILIATE_STATUS = 'affiliate_status', 'Affiliate status changed'
        AFFILIATE_TERMS = 'affiliate_terms', 'Affiliate terms changed'
        AFFILIATE_PROGRAMME = 'affiliate_programme', 'Affiliate programme settings changed'
        AFFILIATE_PAYOUT_PAID = 'affiliate_payout_paid', 'Affiliate payout sent'
        AFFILIATE_PAYOUT_REJECTED = 'affiliate_payout_rejected', 'Affiliate payout rejected'
        PLAYER_DELETED = 'player_deleted', 'Player permanently deleted'
        AFFILIATE_COMMISSION_PAID = 'affiliate_commission_paid', 'Affiliate commission paid'
        FEED_SETTINGS_CHANGED = 'feed_settings_changed', 'Odds feed settings changed'
        EVENT_EDITED = 'event_edited', 'Match edited by staff'
        PAYMENT_SETTINGS_CHANGED = 'payment_settings', 'Payment gateway settings changed'
        CASHOUT_SETTINGS_CHANGED = 'cashout_settings', 'Cash-out settings changed'
        JET_SETTINGS_CHANGED = 'jet_settings', 'Aviator settings changed'

    player_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    event_type = models.CharField(max_length=30, choices=EventType.choices, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'accounts_audit_log'
        ordering = ['-created_at']
