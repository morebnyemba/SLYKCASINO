from .base import BaseKYCProvider, KYCResult, KYCSession, KYCStatus
from .registry import register


@register('stub')
class StubKYCProvider(BaseKYCProvider):
    """Auto-approves all checks. Used in dev and tests."""

    def create_session(self, player_id, first_name, last_name, email):
        return KYCSession(
            session_id=f'stub_{player_id}',
            redirect_url='',
            status=KYCStatus.APPROVED,
        )

    def get_result(self, session_id):
        return KYCResult(
            session_id=session_id,
            player_id=0,
            status=KYCStatus.APPROVED,
            rejection_reason='',
            raw={},
        )

    def verify_webhook(self, payload, signature):
        raise NotImplementedError('StubKYCProvider does not handle webhooks')
