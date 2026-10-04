"""KYC uploads carry the player's legal name, which staff see in the review queue."""
from __future__ import annotations

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.accounts.models import KYCSubmission, Player

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class KYCNameTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.player = account_services.create_player(username='kyc_punter', email='kyc@example.com')
        self.user = User.objects.create(username='kyc_punter')
        self.player.user = self.user
        self.player.save(update_fields=['user'])
        self.staff = User.objects.create(username='kyc_staff', is_staff=True)

    def _submit(self, **data):
        api = APIClient()
        api.force_authenticate(self.user)
        payload = {'document_type': 'national_id', 'file': SimpleUploadedFile('my-id.jpg', b'\xff\xd8\xff' + b'0' * 32), **data}
        return api.post('/api/players/me/kyc/', payload, format='multipart')

    def test_name_is_required_and_saved(self):
        self.assertEqual(self._submit().status_code, 400)
        res = self._submit(full_name='  Tendai   Moyo ')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(KYCSubmission.objects.get().full_name, 'Tendai Moyo')
        self.player.refresh_from_db()
        self.assertEqual((self.player.full_name, self.player.kyc_status), ('Tendai Moyo', Player.Kyc.PENDING))

    def test_staff_queue_shows_name_and_file(self):
        self._submit(full_name='Tendai Moyo')
        api = APIClient()
        api.force_authenticate(self.staff)
        row = api.get('/api/admin/kyc/').json()
        row = (row.get('results') if isinstance(row, dict) else row)[0]
        self.assertEqual((row['full_name'], row['username'], row['email']), ('Tendai Moyo', 'kyc_punter', 'kyc@example.com'))
        self.assertTrue(row['file_name'].startswith('my-id'))
