"""Shares of the partner pool: per-holder percentages, selling unsold shares,
approved buyers, consent for cuts, the 30-day price and the co-signing threshold."""
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog
from apps.revenue import audit, services, shares
from apps.revenue.models import RevenueDay, RevenueSettings, ShareChange, ShareSale, ShareWallet
from apps.revenue.services import RevenueError

URL = '/api/admin/revenue-share/shares/'


def days(values, ggrs=None):
    """Closed days ending yesterday, oldest first, with these shared bases."""
    today = timezone.localdate()
    for i, base in enumerate(values):
        g = D(str(ggrs[i])) if ggrs else D(str(base))
        RevenueDay.objects.create(day=today - timedelta(days=len(values) - i), ggr=g, base=D(str(base)),
                                  share_percent=D('30'), pool=D(str(base)) * D('0.7'))


class Base(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser('boss', 'b@example.com', 'x')
        self.p2 = User.objects.create_user('p2', 'p2@example.com', 'x', is_staff=True)
        self.p3 = User.objects.create_user('p3', 'p3@example.com', 'x', is_staff=True)
        self.buyer = User.objects.create_user('tendai', 't@example.com', 'x', is_staff=True)
        ShareWallet.ensure()
        for slot, user in ((1, self.boss), (2, self.p2), (3, self.p3)):
            ShareWallet.objects.filter(slot=slot).update(holder=user)

    def pct(self, slot):
        return ShareWallet.objects.get(slot=slot).percent

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c


class PriceTests(TestCase):
    def test_steady_winning_month_prices_at_twelve_months(self):
        days([1000] * 30)
        q = shares.price_per_percent()
        # 1% earns 1000 x 30 days x 1% = 300 a month; steady -> factor 1; 12 months -> 3600.
        self.assertEqual((q['monthly_per_percent'], q['factor'], q['price_per_percent']), ('300.00', '1.000', '3600.00'))
        self.assertEqual(shares.quote('2.5')['total'], '9000.00')

    def test_jumpy_or_losing_days_cost_less_but_never_below_sixty_percent(self):
        days([2000, 0] * 15, ggrs=[2000, -100] * 15)      # same average, half the days lose
        q = shares.price_per_percent()
        # volatility 1 (capped) -> -0.25; losing share 0.5 -> -0.25; factor 0.5 -> floored at 0.60.
        self.assertEqual((q['factor'], q['losing_days'], q['price_per_percent']), ('0.600', 15, '2160.00'))
        days_more = RevenueDay.objects.order_by('day')
        self.assertEqual(days_more.count(), 30)

    def test_no_formula_price_without_enough_history_or_earnings(self):
        days([500] * 10)
        self.assertIsNone(shares.price_per_percent()['price_per_percent'])
        RevenueDay.objects.all().delete()
        days([0] * 20, ggrs=[-50] * 20)
        q = shares.price_per_percent()
        self.assertIsNone(q['price_per_percent'])
        self.assertIn('earned nothing', q['reason'])

    def test_only_the_last_thirty_days_count_and_months_is_a_setting(self):
        days([99999] * 10 + [1000] * 30)                  # the older 10 fall out of the window
        cfg = RevenueSettings.load()
        cfg.price_months = 18
        cfg.save()
        self.assertEqual(shares.price_per_percent()['price_per_percent'], '5400.00')


class SaleTests(Base):
    def setUp(self):
        super().setUp()
        days([1000] * 30)

    def test_nothing_to_sell_while_the_founders_hold_all_thirty_percent(self):
        self.assertEqual(shares.unsold_percent(), D('0'))
        with self.assertRaisesMessage(RevenueError, 'Only 0.00%'):
            shares.record_sale(buyer_id=self.buyer.id, percent='1', payment_reference='EC123', by_user=self.boss)

    def test_admin_records_a_paid_sale_out_of_unsold_shares(self):
        shares.set_share(slot=1, percent='5', by_user=self.boss)         # the founder frees 5% of their own
        self.assertEqual(shares.unsold_percent(), D('5.00'))
        sale = shares.record_sale(buyer_id=self.buyer.id, percent='2.5', payment_method='EcoCash',
                                  payment_reference='EC123', by_user=self.boss)
        self.assertEqual((sale.status, sale.price, sale.quoted_price), ('confirmed', D('9000.00'), D('9000.00')))
        wallet = ShareWallet.objects.get(holder=self.buyer)
        self.assertEqual((wallet.slot, wallet.percent), (4, D('2.50')))
        self.assertEqual(shares.unsold_percent(), D('2.50'))
        self.assertTrue(AuditLog.objects.filter(event_type='share_sale_recorded').exists())

    def test_an_agreed_price_is_kept_next_to_the_quote_and_a_reference_is_required(self):
        shares.set_share(slot=1, percent='5', by_user=self.boss)
        with self.assertRaisesMessage(RevenueError, 'payment reference'):
            shares.record_sale(buyer_id=self.buyer.id, percent='1', by_user=self.boss)
        sale = shares.record_sale(buyer_id=self.buyer.id, percent='1', price='3000', payment_reference='BANK9', by_user=self.boss)
        self.assertEqual((sale.price, sale.quoted_price), (D('3000.00'), D('3600.00')))

    def test_a_second_purchase_adds_to_the_same_wallet(self):
        shares.set_share(slot=1, percent='5', by_user=self.boss)
        for _ in range(2):
            shares.record_sale(buyer_id=self.buyer.id, percent='1', payment_reference='R', by_user=self.boss)
        self.assertEqual(ShareWallet.objects.get(holder=self.buyer).percent, D('2.00'))

    def test_only_a_superuser_records_sales(self):
        shares.set_share(slot=1, percent='5', by_user=self.boss)
        with self.assertRaises(RevenueError):
            shares.record_sale(buyer_id=self.buyer.id, percent='1', payment_reference='R', by_user=self.p2)


class BuyerTests(Base):
    def setUp(self):
        super().setUp()
        days([1000] * 30)
        shares.set_share(slot=1, percent='5', by_user=self.boss)          # 5% unsold

    def test_approved_buyer_asks_and_it_counts_once_payment_is_confirmed(self):
        with self.assertRaisesMessage(RevenueError, 'approved buyers'):
            shares.request_purchase(by_user=self.buyer, percent='2')
        shares.approve_buyer(user_id=self.buyer.id, by_user=self.boss)
        sale = shares.request_purchase(by_user=self.buyer, percent='2')
        self.assertEqual((sale.status, sale.price), ('requested', D('7200.00')))
        self.assertFalse(ShareWallet.objects.filter(holder=self.buyer).exists())   # not until paid
        with self.assertRaisesMessage(RevenueError, 'payment reference'):
            shares.confirm_sale(sale.id, by_user=self.boss)
        shares.confirm_sale(sale.id, by_user=self.boss, payment_method='EcoCash', payment_reference='EC77')
        self.assertEqual(ShareWallet.objects.get(holder=self.buyer).percent, D('2.00'))

    def test_waiting_requests_reserve_their_share(self):
        other = User.objects.create_user('rudo', 'r@example.com', 'x', is_staff=True)
        for u in (self.buyer, other):
            shares.approve_buyer(user_id=u.id, by_user=self.boss)
        shares.request_purchase(by_user=self.buyer, percent='4')
        with self.assertRaisesMessage(RevenueError, 'unsold'):
            shares.request_purchase(by_user=other, percent='2')           # only 1% left after the 4% waiting

    def test_requests_can_be_rejected_cancelled_and_expire(self):
        shares.approve_buyer(user_id=self.buyer.id, by_user=self.boss)
        sale = shares.request_purchase(by_user=self.buyer, percent='1')
        shares.reject_sale(sale.id, by_user=self.buyer)
        self.assertEqual(ShareSale.objects.get(pk=sale.id).status, 'cancelled')
        sale = shares.request_purchase(by_user=self.buyer, percent='1')
        ShareSale.objects.filter(pk=sale.id).update(created_at=timezone.now() - timedelta(days=8))
        with self.assertRaisesMessage(RevenueError, 'isn’t waiting'):
            shares.confirm_sale(sale.id, by_user=self.boss, payment_reference='late')


class ConsentTests(Base):
    def test_cutting_someone_elses_share_waits_for_them(self):
        res = shares.set_share(slot=2, percent='4', by_user=self.boss, reason='Agreed at the meeting')
        self.assertFalse(res['applied'])
        self.assertEqual(self.pct(2), D('10.00'))
        change = ShareChange.objects.get()
        with self.assertRaisesMessage(RevenueError, 'holder'):
            shares.decide_change(change.id, by_user=self.p3, approve=True)    # not theirs to answer
        shares.decide_change(change.id, by_user=self.p2, approve=True)
        self.assertEqual(self.pct(2), D('4.00'))

    def test_a_holder_can_refuse(self):
        shares.set_share(slot=2, percent='0', by_user=self.boss)
        shares.decide_change(ShareChange.objects.get().id, by_user=self.p2, approve=False, note='No')
        self.assertEqual((self.pct(2), ShareChange.objects.get().status), (D('10.00'), 'rejected'))

    def test_a_holder_cuts_their_own_share_at_once(self):
        self.assertTrue(shares.set_share(slot=2, percent='6', by_user=self.p2)['applied'])
        self.assertEqual(self.pct(2), D('6.00'))

    def test_raises_need_a_superuser_and_unsold_room(self):
        with self.assertRaises(RevenueError):
            shares.set_share(slot=2, percent='12', by_user=self.p2)
        with self.assertRaisesMessage(RevenueError, 'unsold'):
            shares.set_share(slot=2, percent='12', by_user=self.boss)          # all 30% held
        shares.set_share(slot=1, percent='8', by_user=self.boss)
        shares.set_share(slot=2, percent='12', by_user=self.boss)
        self.assertEqual(self.pct(2), D('12.00'))

    def test_handing_a_wallet_over_needs_its_holder(self):
        res = shares.transfer_wallet(slot=3, new_holder_id=self.buyer.id, by_user=self.boss)
        self.assertFalse(res['applied'])
        self.assertEqual(ShareWallet.objects.get(slot=3).holder_id, self.p3.id)
        shares.decide_change(ShareChange.objects.get().id, by_user=self.p3, approve=True)
        self.assertEqual(ShareWallet.objects.get(slot=3).holder_id, self.buyer.id)

    def test_a_stale_request_cant_be_approved(self):
        shares.set_share(slot=2, percent='5', by_user=self.boss)
        shares.set_share(slot=2, percent='8', by_user=self.p2)                 # changed meanwhile
        with self.assertRaisesMessage(RevenueError, 'changed'):
            shares.decide_change(ShareChange.objects.filter(to_percent=D('5')).get().id, by_user=self.p2, approve=True)


class PayoutTests(Base):
    def test_each_wallet_earns_its_own_share_and_the_unheld_part_goes_to_the_pool(self):
        days([1000] * 20)
        RevenueDay.objects.all().delete()
        cfg = RevenueSettings.load()
        cfg.started_on = timezone.localdate() - timedelta(days=1)
        cfg.save()
        shares.set_share(slot=1, percent='5', by_user=self.boss)
        shares.record_sale(buyer_id=self.buyer.id, percent='2.5', price='1', payment_reference='R', by_user=self.boss)
        with patch.object(services, 'day_ggr', return_value=D('1000')):
            services.close_days()
        day = RevenueDay.objects.get()
        # 5 + 10 + 10 + 2.5 = 27.5% held; 2.5% unsold stays in the pool.
        self.assertEqual((day.share_percent, day.shared, day.pool), (D('27.50'), D('275.00'), D('725.00')))
        buyer_wallet = ShareWallet.objects.get(holder=self.buyer)
        self.assertEqual(services.wallet_balance(buyer_wallet), D('25.00'))
        self.assertEqual(services.wallet_balance(ShareWallet.objects.get(slot=1)), D('50.00'))


class SignerTests(Base):
    def test_small_holders_dont_cosign_audits(self):
        days([1000] * 30)
        shares.set_share(slot=1, percent='5', by_user=self.boss)
        shares.record_sale(buyer_id=self.buyer.id, percent='2', payment_reference='R', by_user=self.boss)
        names = {u.username for u in audit.signers()}
        self.assertEqual(names, {'boss', 'p2', 'p3'})                          # tendai holds 2% < 5%
        shares.update_share_settings(signer_min_percent='1', by_user=self.boss)
        self.assertIn('tendai', {u.username for u in audit.signers()})


class ApiTests(Base):
    def test_who_sees_shares_and_actions(self):
        days([1000] * 30)
        stranger = User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True)
        self.assertEqual(self.api(stranger).get(URL).status_code, 403)
        boss = self.api(self.boss).get(URL).json()
        self.assertEqual((boss['can_admin'], boss['price']['price_per_percent'], boss['unsold_percent']), (True, '3600.00', '0.00'))
        self.api(self.boss).post(URL + 'buyer-add/', {'user_id': self.buyer.id}, format='json')
        mine = self.api(self.buyer).get(URL).json()
        self.assertEqual((mine['can_admin'], mine['is_buyer'], mine['buyers']), (False, True, []))
        res = self.api(self.buyer).post(URL + 'buy/', {'percent': '1'}, format='json')
        self.assertEqual(res.status_code, 400)                                  # nothing unsold yet
        self.api(self.boss).post(URL + 'set/', {'slot': 1, 'percent': '5'}, format='json')
        res = self.api(self.buyer).post(URL + 'buy/', {'percent': '1'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        sale_id = res.json()['sales'][0]['id']
        res = self.api(self.boss).post(f'{URL}sales/{sale_id}/', {'action': 'confirm', 'payment_reference': 'EC1'}, format='json')
        self.assertEqual(res.json()['sales'][0]['status'], 'confirmed')
        q = self.api(self.buyer).get(URL + 'quote/?percent=0.5').json()
        self.assertEqual(q['total'], '1800.00')
        # A superuser's cut of someone else waits for them (202-style result in the body).
        res = self.api(self.boss).post(URL + 'set/', {'slot': 2, 'percent': '9'}, format='json').json()
        self.assertFalse(res['result']['applied'])
        pending = self.api(self.p2).get(URL).json()['pending_for_me']
        res = self.api(self.p2).post(f'{URL}changes/{pending[0]["id"]}/', {'approve': True}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.pct(2), D('9.00'))
