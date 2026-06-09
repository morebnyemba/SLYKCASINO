# To enable: pip install onfido-python, set KYC_PROVIDER=onfido, ONFIDO_API_TOKEN=...
# Uncomment @register('onfido') below.
import os

from .base import BaseKYCProvider, KYCResult, KYCSession, KYCStatus
from .registry import register


# @register('onfido')
class OnfidoKYCProvider(BaseKYCProvider):
    """Onfido KYC integration skeleton.
    Docs: https://documentation.onfido.com/

    To activate:
    1. pip install onfido-python
    2. Set KYC_PROVIDER=onfido in .env
    3. Set ONFIDO_API_TOKEN in .env
    4. Uncomment @register('onfido') above
    """

    def __init__(self):
        import onfido
        self.client = onfido.Api(os.environ['ONFIDO_API_TOKEN'])

    def create_session(self, player_id, first_name, last_name, email):
        applicant = self.client.Applicant.create(
            {'first_name': first_name, 'last_name': last_name, 'email': email},
        )
        sdk_token = self.client.SdkToken.generate(
            {'applicant_id': applicant['id'], 'referrer': '*'},
        )
        return KYCSession(
            session_id=applicant['id'],
            redirect_url=sdk_token['token'],
            status=KYCStatus.PENDING,
        )

    def get_result(self, session_id):
        checks = self.client.Check.all(session_id)
        latest = checks['checks'][0] if checks['checks'] else None
        if latest and latest['status'] == 'complete' and latest['result'] == 'clear':
            kyc_status = KYCStatus.APPROVED
        else:
            kyc_status = KYCStatus.PENDING
        return KYCResult(
            session_id=session_id,
            player_id=0,
            status=kyc_status,
            rejection_reason='',
            raw=latest or {},
        )

    def verify_webhook(self, payload, signature):
        raise NotImplementedError('Implement Onfido webhook verification')
