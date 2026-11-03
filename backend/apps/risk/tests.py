"""The fraud engine: detectors, automatic actions and the staff review."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts_services
from apps.accounts.models import AuditLog, Player
from apps.promotions import services as promotions
from apps.promotions.models import DepositBonus, PromotionClaim
from apps.risk import linking, services as risk
from apps.risk.models import RiskCase, RiskProfile, RiskSignal
from apps.wallet import services as wallet, withdrawals
from apps.wallet.models import PaymentTransaction, WithdrawalRequest, WithdrawalSettings

D = Decimal


def make_player(name, *, verified=True):
    p = accounts_services.create_player(username=name)
    p.user = User.objects.create(username=name)
    if verified:
        p.kyc_status = p.Kyc.VERIFIED
    p.save(update_fields=['user', 'kyc_status'])
    return p


def deposit(player, amount, phone, ref):
    PaymentTransaction.objects.create(reference=ref, player_id=player.id, method='ecocash', phone=phone,
                                      amount=D(amount), status='pending')
    wallet.deposit(player_id=player.id, amount=D(amount), idempotency_key=f'dep:{ref}', reference=f'psp:paynow:{ref}')


def give_winnings(player, amount, key):
    wallet.credit(player_id=player.id, amount=D(amount), kind='adjustment', bucket='winnings', idempotency_key=key)


def ask(player, amount='10', number='0771234567'):
    return withdrawals.request(wallet='winnings', player=player, amount=amount, method='ecocash', account_number=number)


class Base(TestCase):
    def setUp(self):
        WithdrawalSettings.objects.update_or_create(pk=1, defaults={'min_turnover_percent': 0, 'fee_percent': 0})
        self.alice = make_player('alice')
        self.bob = make_player('bob')

    def refreshed(self, player):
        return Player.objects.get(pk=player.id)


class LinkingTests(Base):
    def test_numbers_match_whatever_the_format(self):
        self.assertEqual(linking.normalize_number('+263 77 123 4567'), linking.normalize_number('0771234567'))
        deposit(self.alice, '10', '0771234567', 'R1')
        give_winnings(self.bob, '50', 'w')
        ask(self.bob, number='+263771234567')
        self.assertEqual(linking.linked_accounts(self.bob.id), {self.alice.id: {'deposit number'}})


@override_settings(RISK_ALERT_EMAILS=['fraud@example.com'])
class SharedNumberTests(Base):
    def test_second_account_on_a_deposit_number_goes_under_review_and_gets_no_bonus(self):
        DepositBonus.objects.create(name='Double up', min_deposit=D('1'), percent=D('100'))
        deposit(self.alice, '10', '0771234567', 'R1')
        self.assertEqual(wallet.get_balances(self.alice.id)['bonus'], D('10.00'))   # first account: fine
        with self.captureOnCommitCallbacks(execute=True):
            deposit(self.bob, '10', '0771234567', 'R2')
        signal = RiskSignal.objects.get(player_id=self.bob.id)
        self.assertEqual((signal.code, signal.severity, signal.linked_player_ids),
                         ('shared_deposit_number', 'high', [self.alice.id]))
        prof = RiskProfile.objects.get(player_id=self.bob.id)
        self.assertTrue(prof.under_review and prof.bonus_blocked and not prof.withdrawals_frozen)
        self.assertEqual(wallet.get_balances(self.bob.id)['bonus'], D('0.00'))      # bonus refused
        self.assertEqual(PromotionClaim.objects.get(player_id=self.bob.id).status, 'forfeited')
        self.assertEqual(RiskCase.objects.get(player_id=self.bob.id).action, 'review')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('bob', mail.outbox[0].subject)
        # Under review: a withdrawal is accepted but held, and can't be paid.
        give_winnings(self.bob, '50', 'w')
        req = ask(self.bob, number='0712000000')
        self.assertTrue(req.risk_hold)
        with self.assertRaisesMessage(withdrawals.WithdrawalError, 'fraud check'):
            withdrawals.mark_paid(req.id, reference='MP-1')
        # Recovery never credits the forfeited bonus later.
        from apps.promotions.recovery import RecoveryManager
        RecoveryManager().run()
        self.assertEqual(wallet.get_balances(self.bob.id)['bonus'], D('0.00'))

    def test_payout_number_of_a_suspended_account_suspends_at_once(self):
        give_winnings(self.alice, '50', 'wa')
        ask(self.alice, number='0779999999')
        accounts_services.suspend_player(self.alice.id, reason='fraud')
        give_winnings(self.bob, '50', 'wb')
        first = ask(self.bob, amount='10', number='0712000000')            # own number: fine
        self.assertFalse(first.risk_hold)
        ask(self.bob, amount='10', number='0779999999')
        bob = self.refreshed(self.bob)
        self.assertTrue(bob.is_suspended)
        self.assertIn('Automatic fraud check', bob.suspended_reason)
        self.assertTrue(RiskProfile.objects.get(player_id=bob.id).withdrawals_frozen)
        self.assertTrue(all(r.risk_hold for r in WithdrawalRequest.objects.filter(player_id=bob.id)))
        with self.assertRaisesMessage(withdrawals.WithdrawalError, 'suspended'):
            ask(bob)
        self.assertEqual(RiskCase.objects.get(player_id=bob.id).action, 'suspended')


class DetectorTests(Base):
    def test_tampered_withdrawal_request_suspends(self):
        api = APIClient()
        api.force_authenticate(self.alice.user)
        res = api.post('/api/wallet/withdraw/', {'amount': '10', 'wallet': 'bonus', 'method': 'ecocash',
                                                 'account_number': '0771234567'}, format='json')
        self.assertEqual(res.status_code, 403)
        self.assertTrue(self.refreshed(self.alice).is_suspended)
        self.assertEqual(RiskSignal.objects.get(player_id=self.alice.id).code, 'wallet_tamper')

    def test_two_medium_signals_reach_review(self):
        wallet.deposit(player_id=self.alice.id, amount=D('500'), idempotency_key='d')
        from apps.sportsbook import services as sb
        sb.place_bet(event='A v B', stake=D('150'), odds=D('6'), player_id=self.alice.id, wallet='deposit')
        self.assertEqual(RiskSignal.objects.get(player_id=self.alice.id).code, 'big_bet_new_account')
        self.assertFalse(RiskProfile.objects.get(player_id=self.alice.id).under_review)  # 25 < 40
        wallet.credit(player_id=self.alice.id, amount=D('5'), kind='bonus', idempotency_key='b')
        give_winnings(self.alice, '50', 'w')
        ask(self.alice)                                                         # withdrawal right after a bonus
        self.assertEqual(sorted(RiskSignal.objects.filter(player_id=self.alice.id).values_list('code', flat=True)),
                         ['big_bet_new_account', 'withdraw_after_bonus'])
        self.assertTrue(RiskProfile.objects.get(player_id=self.alice.id).under_review)   # 50 >= 40
        self.assertFalse(self.refreshed(self.alice).is_suspended)

    def test_many_accounts_from_one_ip_is_only_low(self):
        import secrets
        password = secrets.token_urlsafe(16)  # generated per run; test-only
        api = APIClient(REMOTE_ADDR='10.0.0.1')
        for i in range(5):
            res = api.post('/api/auth/register/', {'username': f'ip{i}', 'email': f'ip{i}@example.com',
                                                   'password': password, 'accept_terms': True},
                           format='json', HTTP_X_FORWARDED_FOR='41.1.1.1')
            self.assertEqual(res.status_code, 201, res.content)
        flagged = RiskSignal.objects.filter(code='many_accounts_one_ip')
        self.assertEqual({s.severity for s in flagged}, {'low'})
        self.assertFalse(RiskProfile.objects.filter(under_review=True).exists())

    def test_a_broken_detector_never_breaks_a_deposit(self):
        with mock.patch.object(risk, 'check_number', side_effect=RuntimeError('boom')):
            deposit(self.alice, '10', '0771234567', 'R9')
        self.assertEqual(wallet.get_balances(self.alice.id)['deposit'], D('10.00'))

    def test_duplicate_bonus_across_linked_accounts_is_refused(self):
        deposit(self.alice, '10', '0771234567', 'R1')
        promotions.grant_bonus(player_id=self.alice.id, amount=D('5'), wagering_multiplier=D('1'),
                               system_code='welcome', name='Welcome')
        RiskProfile.objects.filter(player_id=self.bob.id).delete()
        # Bob is tied to Alice by her deposit number, used as his payout number.
        give_winnings(self.bob, '20', 'w')
        WithdrawalRequest.objects.create(player_id=self.bob.id, amount=D('1'), method='ecocash', account_number='0771234567',
                                         status='rejected')
        claim = promotions.grant_bonus(player_id=self.bob.id, amount=D('5'), wagering_multiplier=D('1'),
                                       system_code='welcome', name='Welcome')
        self.assertEqual(claim.status, 'forfeited')
        self.assertEqual(wallet.get_balances(self.bob.id)['bonus'], D('0.00'))
        self.assertTrue(RiskSignal.objects.filter(player_id=self.bob.id, code='duplicate_bonus').exists())


class SweepTests(Base):
    def test_big_winnings_and_linked_accounts_backing_the_same_pick(self):
        from apps.sportsbook import services as sb
        from apps.sportsbook.models import Event
        give_winnings(self.alice, '10', 'x')
        wallet.credit(player_id=self.alice.id, amount=D('1500'), kind='bet_payout', bucket='winnings', idempotency_key='p')
        ev = Event.objects.create(name='C v D', odds=D('6'), odds_draw=D('3'), odds_away=D('2'), is_open=True)
        for p, ref in ((self.alice, 'R1'), (self.bob, 'R2')):
            deposit(p, '50', '0775555555', ref)
            sb.place_bet(event='C v D', stake=D('10'), odds=D('6'), player_id=p.id, wallet='deposit',
                         event_id=ev.id, selection='home')
        found = risk.sweep()
        self.assertEqual(found, {'winnings': 1, 'coordinated': 2})
        self.assertEqual(risk.sweep(), {'winnings': 0, 'coordinated': 0})   # recorded once


class ReviewTests(Base):
    def setUp(self):
        super().setUp()
        risk.on_wallet_tamper(self.alice.id, wallet='bonus')
        give_winnings(self.alice, '50', 'w')
        WithdrawalRequest.objects.create(player_id=self.alice.id, amount=D('5'), method='ecocash',
                                         account_number='0771234567', risk_hold=True)
        self.case = RiskCase.objects.get(player_id=self.alice.id)
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.boss = APIClient()
        self.boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))

    def test_report_lists_everything_staff_need(self):
        body = self.staff.get(f'/api/admin/risk/cases/{self.case.id}/').json()
        self.assertEqual(body['case']['action'], 'suspended')
        report = body['report']
        self.assertEqual(report['signals'][0]['code'], 'wallet_tamper')
        self.assertEqual(report['wallets']['winnings'], '50.00')
        self.assertTrue(report['transactions'] and report['withdrawals'])
        listing = self.staff.get('/api/admin/risk/cases/').json()
        self.assertEqual((listing['open'], listing['held_withdrawals']), (1, 1))
        self.assertEqual(self.staff.get('/api/admin/stats/').json()['queues']['risk_cases_open'], 1)

    def test_only_a_superuser_closes_a_case_and_dismissing_reinstates(self):
        url = f'/api/admin/risk/cases/{self.case.id}/decide/'
        self.assertEqual(self.staff.post(url, {'decision': 'dismiss', 'note': 'ok'}, format='json').status_code, 403)
        self.assertEqual(self.boss.post(url, {'decision': 'dismiss', 'note': ''}, format='json').status_code, 400)
        res = self.boss.post(url, {'decision': 'dismiss', 'note': 'Tested by the player’s developer'}, format='json')
        self.assertEqual((res.status_code, res.json()['status']), (200, 'dismissed'))
        self.assertFalse(self.refreshed(self.alice).is_suspended)
        prof = RiskProfile.objects.get(player_id=self.alice.id)
        self.assertFalse(prof.under_review or prof.withdrawals_frozen or prof.bonus_blocked)
        self.assertFalse(WithdrawalRequest.objects.filter(player_id=self.alice.id, risk_hold=True).exists())
        # Old signals no longer count; a new low one alone doesn't restrict.
        risk.flag(self.alice.id, 'test', 'low', 'later', dedupe='x')
        self.assertEqual(RiskProfile.objects.get(player_id=self.alice.id).score, 10)
        self.assertTrue(AuditLog.objects.filter(event_type='risk_case_dismissed').exists())

    def test_staff_can_freeze_but_only_a_superuser_unfreezes(self):
        url = f'/api/admin/risk/players/{self.bob.id}/'
        self.assertEqual(self.staff.post(url, {'withdrawals_frozen': True}, format='json').status_code, 200)
        self.assertEqual(self.staff.post(url, {'withdrawals_frozen': False}, format='json').status_code, 403)
        self.assertEqual(self.boss.post(url, {'withdrawals_frozen': False}, format='json').status_code, 200)

    def test_an_open_case_blocks_permanent_deletion(self):
        with self.assertRaisesMessage(accounts_services.DeletionBlocked, 'open fraud case'):
            accounts_services.delete_player(self.alice.id, confirm_username='alice', force=True)

    def test_settings_are_superuser_only_and_validated(self):
        self.assertEqual(self.staff.put('/api/admin/risk/settings/', {'review_score': 5}, format='json').status_code, 403)
        self.assertEqual(self.boss.put('/api/admin/risk/settings/', {'review_score': 200}, format='json').status_code, 400)
        res = self.boss.put('/api/admin/risk/settings/', {'review_score': 30, 'big_bet_amount': '50'}, format='json')
        self.assertEqual((res.json()['review_score'], res.json()['big_bet_amount']), (30, '50.00'))


class RateLimitTests(Base):
    def test_withdrawal_requests_are_rate_limited(self):
        api = APIClient()
        api.force_authenticate(self.bob.user)
        codes = [api.post('/api/wallet/withdraw/', {'wallet': 'winnings', 'amount': '1'}, format='json').status_code for _ in range(11)]
        self.assertEqual(codes[-1], 429)
        self.assertNotIn(429, codes[:10])


class CloudflareTests(Base):
    """Before nginx resolved visitor IPs behind Cloudflare, every request was
    logged with a Cloudflare edge address. Those must never link players."""

    def test_cloudflare_ranges(self):
        from common.cloudflare import is_cloudflare
        self.assertTrue(is_cloudflare('172.68.10.1'))
        self.assertTrue(is_cloudflare('2606:4700::1'))
        self.assertFalse(is_cloudflare('41.60.10.20'))
        self.assertFalse(is_cloudflare('not-an-ip'))

    def test_django_reads_the_visitor_ip_nginx_resolved(self):
        from django.test import RequestFactory

        from common.client_ip import client_ip
        # What nginx forwards once it has swapped Cloudflare's address for the
        # visitor's (verified against a real nginx with this config).
        req = RequestFactory().get('/', REMOTE_ADDR='172.18.0.5', HTTP_X_FORWARDED_FOR='6.6.6.6, 41.60.10.20')
        self.assertEqual(client_ip(req), '41.60.10.20')

    def test_cloudflare_addresses_never_link_players(self):
        cf = '172.68.10.1'
        for p in (self.alice, self.bob):
            AuditLog.objects.create(player_id=p.id, event_type='login', ip_address=cf)
        self.assertEqual(linking.linked_accounts(self.alice.id), {})
        AuditLog.objects.create(player_id=self.alice.id, event_type='login', ip_address='41.60.10.20')
        AuditLog.objects.create(player_id=self.bob.id, event_type='login', ip_address='41.60.10.20')
        self.assertEqual(linking.linked_accounts(self.alice.id), {self.bob.id: {'IP address'}})

    def test_signup_from_a_cloudflare_address_raises_nothing(self):
        carol = make_player('carol')
        for p in (self.alice, self.bob, carol):
            AuditLog.objects.create(player_id=p.id, event_type='register', ip_address='172.68.10.1')
        dave = make_player('dave')
        risk.on_register(dave.id, '172.68.10.1')
        self.assertFalse(RiskSignal.objects.exists())

    def test_audit_log_marks_cloudflare_addresses(self):
        AuditLog.objects.create(player_id=self.alice.id, event_type='login', ip_address='172.68.10.1')
        api = APIClient()
        api.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        row = api.get('/api/admin/audit-log/', {'player_id': self.alice.id}).json()['results'][0]
        self.assertTrue(row['ip_is_cloudflare'])
