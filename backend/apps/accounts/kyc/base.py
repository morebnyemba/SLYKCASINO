from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class KYCStatus(str, Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    REQUIRES_RESUBMISSION = 'requires_resubmission'


@dataclass
class KYCSession:
    session_id: str
    redirect_url: str   # URL to redirect player to for document upload
    status: KYCStatus


@dataclass
class KYCResult:
    session_id: str
    player_id: int
    status: KYCStatus
    rejection_reason: str
    raw: dict


class BaseKYCProvider(ABC):
    """Abstract KYC provider. Implement and register with @kyc_registry.register('name')."""

    @abstractmethod
    def create_session(
        self, player_id: int, first_name: str, last_name: str, email: str,
    ) -> KYCSession:
        """Start a KYC verification session. Returns redirect URL for player."""

    @abstractmethod
    def get_result(self, session_id: str) -> KYCResult:
        """Poll for session result (also used from webhook handler)."""

    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> KYCResult:
        """Parse inbound webhook from the KYC provider."""
