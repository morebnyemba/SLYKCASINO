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


class NewLogoPaletteMigrationTests(TestCase):
    """0009 moves stored themes still on the old defaults; hand-edited sides stay."""

    def _run(self):
        import importlib
        from django.apps import apps
        importlib.import_module('apps.branding.migrations.0009_new_logo_palette').forwards(apps, None)

    def test_untouched_theme_moves_and_edited_side_is_kept(self):
        import importlib
        from apps.branding.models import SiteTheme
        from apps.branding.tokens import DEFAULT_DARK, DEFAULT_LIGHT
        mig = importlib.import_module('apps.branding.migrations.0009_new_logo_palette')
        edited_dark = {**mig.PREVIOUS_DARK, 'primary': '#123456'}
        theme = SiteTheme.objects.create(light=dict(mig.PREVIOUS_LIGHT), dark=edited_dark)
        self._run()
        theme.refresh_from_db()
        self.assertEqual(theme.light, DEFAULT_LIGHT)
        self.assertEqual(theme.dark, edited_dark)
