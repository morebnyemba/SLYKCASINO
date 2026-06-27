from django.db import models

from .player import Player


class KYCSubmission(models.Model):
    """A player-submitted identity document awaiting internal staff review.

    No external verification provider is used — review is always a manual
    staff decision (approve/reject), recorded here.
    """

    class DocumentType(models.TextChoices):
        PASSPORT = 'passport', 'Passport'
        NATIONAL_ID = 'national_id', 'National ID'
        DRIVING_LICENSE = 'driving_license', 'Driving license'
        PROOF_OF_ADDRESS = 'proof_of_address', 'Proof of address'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='kyc_submissions')
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    file = models.FileField(upload_to='kyc/%Y/%m/')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.CharField(max_length=255, blank=True, default='')
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by_username = models.CharField(max_length=150, blank=True, default='')

    class Meta:
        db_table = 'accounts_kyc_submission'
        ordering = ['-submitted_at']

    def __str__(self) -> str:
        return f'{self.player.username} · {self.document_type} · {self.status}'
