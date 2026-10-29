from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class WhatsAppNumberTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))

    def test_number_is_stored_as_digits_and_public(self):
        res = self.api.patch('/api/branding/identity/', {'whatsapp_number': '+263 77-123 4567'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(APIClient().get('/api/branding/identity/').json()['whatsapp_number'], '263771234567')

    def test_rejects_numbers_without_country_code_and_allows_blank(self):
        self.assertEqual(self.api.patch('/api/branding/identity/', {'whatsapp_number': '0771234'}, format='json').status_code, 400)
        self.assertEqual(self.api.patch('/api/branding/identity/', {'whatsapp_number': 'call me'}, format='json').status_code, 400)
        self.assertEqual(self.api.patch('/api/branding/identity/', {'whatsapp_number': ''}, format='json').status_code, 200)
