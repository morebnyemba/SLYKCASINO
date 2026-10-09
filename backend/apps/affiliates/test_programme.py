"""The referral programme extras: referred players' welcome bonus (and the
wagering lock on bonus money), the affiliate's deposit commission, and
carrying a losing month into the next revenue share."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.affiliates import services, utils
from apps.affiliates.models import Affiliate, Commission, RevshareMonth
from apps.promotions.models import PromotionClaim
from apps.wallet import services as wallet_services
from apps.wallet.models import LedgerEntry

D = Decimal


class UtilTests(SimpleTestCase):
    def test_deposit_commission(self):
        self.assertEqual(utils.deposit_commission(D('50'), D('0'), D('30'), D('100')), D('15.00'))
        self.assertEqual(utils.deposit_commission(D('1000'), D('0'), D('30'), D('100')), D('100.00'))  # capped
        self.assertEqual(utils.deposit_commission(D('1000'), D('0'), D('30'), D('0')), D('300.00'))    # no cap
        self.assertEqual(utils.deposit_commission(D('50'), D('5'), D('30'), D('100')), D('20.00'))     # + flat

    def test_welcome_bonus(self):
        self.assertEqual(utils.welcome_bonus(D('50'), D('30'), D('100'), D('1')), D('15.00'))
        self.assertEqual(utils.welcome_bonus(D('500'), D('30'), D('100'), D('1')), D('100.00'))
        self.assertEqual(utils.welcome_bonus(D('5'), D('30'), D('100'), D('10')), D('0.00'))  # under minimum
        self.assertEqual(utils.welcome_bonus(D('50'), D('0'), D('100'), D('1')), D('0.00'))   # off

    def test_carry(self):
        self.assertEqual(utils.carry(D('-100'), D('0'), True), (D('-100'), D('-100')))
        self.assertEqual(utils.carry(D('60'), D('-100'), True), (D('-40'), D('-40')))
        self.assertEqual(utils.carry(D('100'), D('-40'), True), (D('60'), D('0')))
        self.assertEqual(utils.carry(D('60'), D('-100'), False), (D('60'), D('0')))


class ProgrammeBase(TestCase):
    def setUp(self):
        self.programme = services.update_programme(
            welcome_bonus_percent=30, welcome_bonus_cap=100, welcome_bonus_wagering=5, welcome_bonus_min_deposit=1,
            default_cpa_percent=30, default_cpa_cap=100, cpa_min_turnover_multiple=1, negative_carryover=True,
        )
        self.partner = account_services.create_player(username='partner')
        self.affiliate = services.apply(player_id=self.partner.id, code='PARTNER')
        services.set_status(self.affiliate.id, Affiliate.Status.ACTIVE)
        self.affiliate.refresh_from_db()

    def referred(self, name):
        player = account_services.create_player(username=name)
        services.attach_referral(player_id=player.id, code=self.affiliate.code)
        return player

    def balance(self, player):
        return wallet_services.get_balance_dto(player.id).balance

    def deposit(self, player, amount, key):
        return wallet_services.deposit(player_id=player.id, amount=D(amount), idempotency_key=key)

    def stake(self, player, amount, key, kind='bet_stake'):
        return wallet_services.debit(player_id=player.id, amount=D(amount), kind=kind, idempotency_key=key)


class FreshProgrammeTests(TestCase):
    def test_defaults_work_before_anyone_saves_settings(self):
        from apps.affiliates.models import AffiliateProgramme
        AffiliateProgramme.objects.all().delete()
        partner = account_services.create_player(username='partner')
        affiliate = services.apply(player_id=partner.id, code='FRESH')
        services.set_status(affiliate.id, Affiliate.Status.ACTIVE)
        kid = account_services.create_player(username='kid')
        services.attach_referral(player_id=kid.id, code='FRESH')
        AffiliateProgramme.objects.all().delete()
        wallet_services.deposit(player_id=kid.id, amount=D('50'), idempotency_key='fresh')
        self.assertEqual(wallet_services.get_balance_dto(kid.id).balance, D('65.00'))


class WelcomeBonusTests(ProgrammeBase):
    def test_first_deposit_only_and_referred_only(self):
        alice = self.referred('alice')
        self.deposit(alice, '50', 'a1')
        self.assertEqual(self.balance(alice), D('65.00'))           # 50 + 30% bonus
        claim = PromotionClaim.objects.get(player_id=alice.id)
        self.assertEqual((claim.bonus_amount, claim.wagering_required), (D('15.00'), D('75.00')))
        self.deposit(alice, '50', 'a2')
        self.assertEqual(self.balance(alice), D('115.00'))          # second deposit: no bonus
        self.assertEqual(LedgerEntry.objects.filter(wallet__player_id=alice.id, kind='bonus').count(), 1)

        outsider = account_services.create_player(username='outsider')
        self.deposit(outsider, '50', 'o1')
        self.assertEqual(self.balance(outsider), D('50.00'))

        big = self.referred('big')
        self.deposit(big, '1000', 'b1')
        self.assertEqual(self.balance(big), D('1100.00'))           # capped at 100

    def test_replayed_deposit_does_not_pay_twice(self):
        alice = self.referred('alice')
        self.deposit(alice, '50', 'same-key')
        self.deposit(alice, '50', 'same-key')
        self.assertEqual(self.balance(alice), D('65.00'))

    def test_hidden_from_promotions_catalog(self):
        self.deposit(self.referred('alice'), '50', 'a1')
        names = [p['name'] for p in APIClient().get('/api/promotions/').json().get('results', [])]
        self.assertNotIn('Welcome bonus', names)


class WageringLockTests(ProgrammeBase):
    def client_for(self, player):
        user = User.objects.create_user(username=player.username, password='pw')
        player.user = user
        player.kyc_status = player.Kyc.VERIFIED
        player.save(update_fields=['user', 'kyc_status'])
        api = APIClient()
        api.force_authenticate(user)
        return api

    def test_bonus_is_locked_until_wagered(self):
        alice = self.referred('alice')
        api = self.client_for(alice)
        self.deposit(alice, '50', 'a1')                              # balance 65, 15 locked, wager 75
        wallet = api.get('/api/wallet/').json()
        self.assertEqual((wallet['bonus_locked'], wallet['withdrawable']), ('15.00', '50.00'))

        res = api.post('/api/wallet/withdraw/', {'amount': '60'}, format='json')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()['withdrawable'], '50.00')

        self.stake(alice, '40', 's1')
        wallet_services.credit(player_id=alice.id, amount=D('20'), kind='bet_payout', idempotency_key='w1')
        self.assertEqual(api.get('/api/wallet/').json()['bonus_locked'], '15.00')  # 40 of 75 wagered
        self.stake(alice, '35', 's2', kind='casino_debit')           # 75 wagered: unlocked
        self.assertEqual(api.get('/api/wallet/').json()['bonus_locked'], '0.00')
        self.assertEqual(api.post('/api/wallet/withdraw/', {'amount': '-10'}, format='json').status_code, 400)
        self.assertEqual(api.post('/api/wallet/withdraw/', {'amount': str(self.balance(alice))}, format='json').status_code, 201)


class DepositCommissionTests(ProgrammeBase):
    def test_new_affiliates_start_on_programme_defaults(self):
        self.assertEqual((self.affiliate.cpa_percent, self.affiliate.cpa_cap), (D('30.00'), D('100.00')))

    def test_paid_once_after_turnover(self):
        services.update_terms(self.affiliate.id, cpa_min_deposit='20')
        self.affiliate.refresh_from_db()
        alice = self.referred('alice')
        self.deposit(alice, '50', 'a1')
        self.assertEqual(services.compute_cpa(self.affiliate), 0)    # deposited but not played
        self.stake(alice, '30', 's1')
        self.assertEqual(services.compute_cpa(self.affiliate), 0)    # 30 staked < 50 first deposit
        self.stake(alice, '20', 's2')
        self.assertEqual(services.compute_cpa(self.affiliate), 1)
        self.assertEqual(services.compute_cpa(self.affiliate), 0)
        c = Commission.objects.get(kind='cpa')
        self.assertEqual((c.base_amount, c.amount, c.status), (D('50.00'), D('15.00'), Commission.Status.PENDING))

        bob = self.referred('bob')
        self.deposit(bob, '1000', 'b1')
        self.stake(bob, '1000', 's3')
        services.compute_cpa(self.affiliate)
        self.assertEqual(Commission.objects.get(kind='cpa', referral__player_id=bob.id).amount, D('100.00'))


class CarryOverTests(ProgrammeBase):
    def setUp(self):
        super().setUp()
        services.update_programme(welcome_bonus_percent=0)  # keep the maths to stakes and wins
        self.player = self.referred('alice')
        wallet_services.credit(player_id=self.player.id, amount=D('10000'), kind='deposit', idempotency_key='bank')

    def month_result(self, month: date, ngr: int):
        """Make the referred player's net revenue for `month` equal `ngr`."""
        key = f'{month.isoformat()}'
        entries = [self.stake(self.player, '200', f'{key}:s')]
        entries.append(wallet_services.credit(
            player_id=self.player.id, amount=D(200 - ngr), kind='bet_payout', idempotency_key=f'{key}:w'))
        when = timezone.make_aware(datetime.combine(month.replace(day=10), time(12)))
        LedgerEntry.objects.filter(pk__in=[e.pk for e in entries]).update(created_at=when)

    def test_losing_month_is_earned_back_first(self):
        m1, m2, m3 = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)
        self.month_result(m1, -100)
        self.month_result(m2, 60)
        self.month_result(m3, 100)
        self.assertIsNone(services.compute_revshare(self.affiliate, m1))
        self.assertIsNone(services.compute_revshare(self.affiliate, m2))    # 60 - 100: still behind
        c = services.compute_revshare(self.affiliate, m3)                    # 100 - 40 = 60 × 25%
        self.assertEqual((c.base_amount, c.amount), (D('60.00'), D('15.00')))
        self.assertEqual(services.carryover_balance(self.affiliate), D('0'))
        self.assertEqual(
            list(RevshareMonth.objects.order_by('period').values_list('carry_out', flat=True)),
            [D('-100.00'), D('-40.00'), D('0.00')],
        )
        # Idempotent: closing the months again changes nothing.
        self.assertIsNone(services.compute_revshare(self.affiliate, m2))
        self.assertEqual(services.compute_revshare(self.affiliate, m3).pk, c.pk)
        self.assertEqual(Commission.objects.filter(kind='revshare').count(), 1)

    def test_switched_off_every_month_stands_alone(self):
        services.update_programme(negative_carryover=False)
        m1, m2 = date(2026, 1, 1), date(2026, 2, 1)
        self.month_result(m1, -100)
        self.month_result(m2, 60)
        self.assertIsNone(services.compute_revshare(self.affiliate, m1))
        self.assertEqual(services.compute_revshare(self.affiliate, m2).amount, D('15.00'))


class ProgrammeApiTests(ProgrammeBase):
    def test_admin_edits_and_public_terms(self):
        staff = User.objects.create_user('staff', 'staff@example.com', 'x', is_staff=True)
        api = APIClient()
        api.force_authenticate(staff)
        res = api.put('/api/admin/affiliate-programme/', {'welcome_bonus_percent': '20', 'negative_carryover': False}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.json()['welcome_bonus_percent'], res.json()['negative_carryover']), ('20.00', False))
        self.assertEqual(api.put('/api/admin/affiliate-programme/', {'welcome_bonus_percent': '150'}, format='json').status_code, 400)
        terms = APIClient().get('/api/affiliates/terms/').json()
        self.assertEqual((terms['cpa_percent'], terms['programme']['welcome_bonus_percent']), ('30.00', '20.00'))

        player = account_services.create_player(username='nonstaff')
        user = User.objects.create_user(username='nonstaff', password='pw')
        player.user = user
        player.save(update_fields=['user'])
        api.force_authenticate(user)
        self.assertEqual(api.get('/api/admin/affiliate-programme/').status_code, 403)
