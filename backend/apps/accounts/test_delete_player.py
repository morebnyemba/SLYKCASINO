"""Permanent player deletion: guarded, superuser-only, and thorough across
every app — while other players' records (e.g. an affiliate's earnings on
the deleted player) survive."""
from __future__ import annotations

import os
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import AuditLog, KYCSubmission, Player
from apps.affiliates import services as affiliate_services
from apps.affiliates.models import Affiliate, Commission, Payout, Referral
from apps.livechat.models import ChatMessage
from apps.notifications.models import Notification
from apps.promotions.models import PromotionClaim
from apps.sportsbook.models import Bet
from apps.wallet import services as wallet_services
from apps.wallet.models import LedgerEntry, Wallet

D = Decimal
MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class DeletePlayerTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        affiliate_services.update_programme(welcome_bonus_percent=30, cpa_min_turnover_multiple=0)
        # The partner who referred our player, and the player to delete.
        self.partner = services.create_player(username='partner')
        self.aff = affiliate_services.apply(player_id=self.partner.id, code='PARTNER')
        affiliate_services.set_status(self.aff.id, Affiliate.Status.ACTIVE)
        self.player = services.register_player(username='gone_soon', email='gone@example.com', password='Passw0rd!Long', currency='USD')
        affiliate_services.attach_referral(player_id=self.player.id, code='PARTNER')
        wallet_services.deposit(player_id=self.player.id, amount=D('50'), idempotency_key='gone:dep')  # + welcome bonus
        wallet_services.debit(player_id=self.player.id, amount=D('10'), kind='bet_stake', idempotency_key='gone:bet')
        Bet.objects.create(player_id=self.player.id, event='Match', selection='home', stake=D('10'), odds=D('2.0'),
                           status=Bet.Status.LOST)
        affiliate_services.update_terms(self.aff.id, cpa_percent='30', cpa_cap='100', cpa_min_deposit='1')
        self.aff.refresh_from_db()
        affiliate_services.compute_cpa(self.aff)  # the partner earns on our player
        ChatMessage.objects.create(player_id=self.player.id, channel='support', body='hi')
        self.kyc = KYCSubmission.objects.create(
            player=self.player, document_type='passport',
            file=SimpleUploadedFile('passport.png', b'\x89PNG fake', content_type='image/png'),
        )
        # Our player is an affiliate too, with earnings already paid out.
        own = affiliate_services.apply(player_id=self.player.id, code='GONESOON')
        affiliate_services.set_status(own.id, Affiliate.Status.ACTIVE)
        c = Commission.objects.create(affiliate=own, kind=Commission.Kind.CPA, amount=D('5'))
        affiliate_services.approve(c.id)
        affiliate_services.request_payout(affiliate_id=own.id, amount='5', method='wallet')
        services.audit(self.player.id, 'login', None)
        self.superuser = User.objects.create_superuser('boss', 'boss@example.com', 'x')

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_guards(self):
        staff = User.objects.create_user('ops', 'ops@example.com', 'x', is_staff=True)
        url = f'/api/players/{self.player.id}/delete/'
        self.assertEqual(self.api(staff).post(url, {'confirm': 'gone_soon'}, format='json').status_code, 403)
        boss = self.api(self.superuser)
        check = boss.get(f'/api/players/{self.player.id}/deletion-check/').json()
        self.assertTrue(check['can_delete'])
        self.assertEqual(check['balance'], f"{wallet_services.get_balance(self.player.id):.2f}")
        res = boss.post(url, {'confirm': 'wrong'}, format='json')
        self.assertEqual(res.status_code, 409)
        res = boss.post(url, {'confirm': 'gone_soon'}, format='json')
        self.assertEqual(res.status_code, 409)               # still has a balance
        self.assertIn('balance', res.json()['detail'])
        self.assertTrue(Player.objects.filter(pk=self.player.id).exists())

    def test_staff_accounts_are_refused(self):
        staff_user = User.objects.create_user('opsplayer', 'o@example.com', 'x', is_staff=True)
        self.player.user = staff_user
        self.player.save(update_fields=['user'])
        res = self.api(self.superuser).post(f'/api/players/{self.player.id}/delete/', {'confirm': 'gone_soon', 'force': True}, format='json')
        self.assertEqual(res.status_code, 409)

    def test_force_deletes_everything_and_keeps_others_records(self):
        pid, user_id = self.player.id, self.player.user_id
        file_path = self.kyc.file.path
        self.assertTrue(os.path.exists(file_path))
        partner_cpa = Commission.objects.get(affiliate=self.aff, kind='cpa')

        with self.captureOnCommitCallbacks(execute=True):
            res = self.api(self.superuser).post(
                f'/api/players/{pid}/delete/', {'confirm': 'gone_soon', 'force': True}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['forced'])

        self.assertFalse(Player.objects.filter(pk=pid).exists())
        self.assertFalse(User.objects.filter(pk=user_id).exists())
        self.assertFalse(Wallet.objects.filter(player_id=pid).exists())
        self.assertFalse(LedgerEntry.objects.filter(wallet__player_id=pid).exists())
        self.assertFalse(Bet.objects.filter(player_id=pid).exists())
        self.assertFalse(PromotionClaim.objects.filter(player_id=pid).exists())
        self.assertFalse(Notification.objects.filter(player_id=pid).exists())
        self.assertFalse(ChatMessage.objects.filter(player_id=pid).exists())
        self.assertFalse(KYCSubmission.objects.filter(player_id=pid).exists())
        self.assertFalse(os.path.exists(file_path))
        self.assertFalse(Referral.objects.filter(player_id=pid).exists())
        self.assertFalse(Affiliate.objects.filter(player_id=pid).exists())
        self.assertFalse(Payout.objects.filter(affiliate__player_id=pid).exists())
        self.assertFalse(AuditLog.objects.filter(player_id=pid).exists())

        # The partner keeps what they earned on the deleted player.
        partner_cpa.refresh_from_db()
        self.assertIsNone(partner_cpa.referral_id)
        record = AuditLog.objects.get(event_type='player_deleted')
        self.assertEqual((record.metadata['username'], record.metadata['deleted_by']), ('gone_soon', 'boss'))

    def test_clean_account_needs_no_force(self):
        empty = services.create_player(username='empty_one')
        result = services.delete_player(empty.id, confirm_username='empty_one')
        self.assertFalse(result['forced'])
        self.assertFalse(Player.objects.filter(pk=empty.id).exists())
