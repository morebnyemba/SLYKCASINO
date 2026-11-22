"""Shares of the partner pool: per-holder percentages, selling unsold shares,
approved buyers, consent for cuts, the 30-day price and the co-signing threshold."""
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog
from apps.revenue import agreement, audit, services, shares
from apps.revenue.models import RevenueDay, RevenueSettings, ShareChange, ShareRelease, ShareSale, ShareWallet
from apps.revenue.services import RevenueError

URL = '/api/admin/revenue-share/shares/'


def days(values, ggrs=None):
    """Closed days ending yesterday, oldest first, with these shared bases."""
    today = timezone.localdate()
    for i, base in enumerate(values):
        g = D(str(ggrs[i])) if ggrs else D(str(base))
        RevenueDay.objects.create(day=today - timedelta(days=len(values) - i), ggr=g, base=D(str(base)),
                                  share_percent=D('30'), pool=D(str(base)) * D('0.7'))


@override_settings(REVENUE_SHARE_CONTROLLER_IDS=[])   # ids depend on creation order; tests set them explicitly
class Base(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser('boss', 'b@example.com', 'x')        # wallet 1 → founder → controller
        self.root = User.objects.create_superuser('root', 'r@example.com', 'x')        # a superuser who isn't a controller
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
            shares.record_sale(buyer_id=self.buyer.id, percent='1', payment_reference='EC123', accepted_agreement=True, by_user=self.boss)

    def test_admin_records_a_paid_sale_out_of_unsold_shares(self):
        shares.set_share(slot=1, percent='5', by_user=self.boss)         # the founder frees 5% of their own
        self.assertEqual(shares.unsold_percent(), D('5.00'))
        sale = shares.record_sale(buyer_id=self.buyer.id, percent='2.5', payment_method='EcoCash',
                                  payment_reference='EC123', accepted_agreement=True, by_user=self.boss)
        self.assertEqual((sale.status, sale.price, sale.quoted_price), ('confirmed', D('9000.00'), D('9000.00')))
        wallet = ShareWallet.objects.get(holder=self.buyer)
        self.assertEqual((wallet.slot, wallet.percent), (4, D('2.50')))
        self.assertEqual(shares.unsold_percent(), D('2.50'))
        self.assertTrue(AuditLog.objects.filter(event_type='share_sale_recorded').exists())

    def test_an_agreed_price_is_kept_next_to_the_quote_and_a_reference_is_required(self):
        shares.set_share(slot=1, percent='5', by_user=self.boss)
        with self.assertRaisesMessage(RevenueError, 'payment reference'):
            shares.record_sale(buyer_id=self.buyer.id, percent='1', accepted_agreement=True, by_user=self.boss)
        sale = shares.record_sale(buyer_id=self.buyer.id, percent='1', price='3000', payment_reference='BANK9', accepted_agreement=True, by_user=self.boss)
        self.assertEqual((sale.price, sale.quoted_price), (D('3000.00'), D('3600.00')))

    def test_a_second_purchase_adds_to_the_same_wallet(self):
        shares.set_share(slot=1, percent='5', by_user=self.boss)
        for _ in range(2):
            shares.record_sale(buyer_id=self.buyer.id, percent='1', payment_reference='R', accepted_agreement=True, by_user=self.boss)
        self.assertEqual(ShareWallet.objects.get(holder=self.buyer).percent, D('2.00'))

    def test_only_a_superuser_records_sales(self):
        shares.set_share(slot=1, percent='5', by_user=self.boss)
        with self.assertRaises(RevenueError):
            shares.record_sale(buyer_id=self.buyer.id, percent='1', payment_reference='R', accepted_agreement=True, by_user=self.p2)


class BuyerTests(Base):
    def setUp(self):
        super().setUp()
        days([1000] * 30)
        shares.set_share(slot=1, percent='5', by_user=self.boss)          # 5% unsold

    def test_approved_buyer_asks_and_it_counts_once_payment_is_confirmed(self):
        with self.assertRaisesMessage(RevenueError, 'approved buyers'):
            shares.request_purchase(by_user=self.buyer, percent='2', accepted_agreement=True)
        shares.approve_buyer(user_id=self.buyer.id, by_user=self.boss)
        sale = shares.request_purchase(by_user=self.buyer, percent='2', accepted_agreement=True)
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
        shares.request_purchase(by_user=self.buyer, percent='4', accepted_agreement=True)
        with self.assertRaisesMessage(RevenueError, 'unsold'):
            shares.request_purchase(by_user=other, percent='2', accepted_agreement=True)           # only 1% left after the 4% waiting

    def test_requests_can_be_rejected_cancelled_and_expire(self):
        shares.approve_buyer(user_id=self.buyer.id, by_user=self.boss)
        sale = shares.request_purchase(by_user=self.buyer, percent='1', accepted_agreement=True)
        shares.reject_sale(sale.id, by_user=self.buyer)
        self.assertEqual(ShareSale.objects.get(pk=sale.id).status, 'cancelled')
        sale = shares.request_purchase(by_user=self.buyer, percent='1', accepted_agreement=True)
        ShareSale.objects.filter(pk=sale.id).update(created_at=timezone.now() - timedelta(days=8))
        with self.assertRaisesMessage(RevenueError, 'isn’t waiting'):
            shares.confirm_sale(sale.id, by_user=self.boss, payment_reference='late')


class NoApprovalTests(Base):
    """Superusers and share controllers change any share at once: no approval
    from the holder or other admins."""

    def test_a_superuser_cuts_someone_elses_share_at_once(self):
        res = shares.set_share(slot=2, percent='4', by_user=self.root, reason='Agreed at the meeting')
        self.assertTrue(res['applied'])
        self.assertEqual(self.pct(2), D('4.00'))
        change = ShareChange.objects.get()
        self.assertEqual(change.status, 'applied')
        self.assertIn('no approval needed', change.decided_note)

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

    def test_handing_a_wallet_over_applies_at_once(self):
        res = shares.transfer_wallet(slot=3, new_holder_id=self.buyer.id, by_user=self.root)
        self.assertTrue(res['applied'])
        self.assertEqual(ShareWallet.objects.get(slot=3).holder_id, self.buyer.id)

    def test_a_change_left_pending_from_before_can_still_be_answered(self):
        wallet = ShareWallet.objects.get(slot=2)
        old = ShareChange.objects.create(wallet=wallet, holder=self.p2, from_percent=D('10'), to_percent=D('5'),
                                         requested_by='root')
        shares.decide_change(old.id, by_user=self.p2, approve=True)
        self.assertEqual(self.pct(2), D('5.00'))
        stale = ShareChange.objects.create(wallet=wallet, holder=self.p2, from_percent=D('10'), to_percent=D('4'),
                                           requested_by='root')
        with self.assertRaisesMessage(RevenueError, 'changed'):
            shares.decide_change(stale.id, by_user=self.p2, approve=True)
        shares.decide_change(stale.id, by_user=self.root, approve=False)          # the asker withdraws it
        self.assertEqual(ShareChange.objects.get(pk=stale.pk).status, 'cancelled')


class AddMemberTests(Base):
    """A superuser or controller adds a staff login as a member, with a share from the unsold part."""

    def test_add_a_member_with_a_share(self):
        shares.set_share(slot=1, percent='5', by_user=self.boss, for_sale=False)   # 5% unsold now
        res = shares.add_member(user_id=self.buyer.id, percent='3', label='Tendai (investor)', by_user=self.boss)
        wallet = ShareWallet.objects.get(holder=self.buyer)
        self.assertEqual((res['slot'], wallet.slot, wallet.percent, wallet.label), (wallet.slot, 4, D('3.00'), 'Tendai (investor)'))
        self.assertEqual(shares.unsold_percent(), D('2.00'))
        from apps.accounts.models import AuditLog
        self.assertTrue(AuditLog.objects.filter(event_type='share_member_added').exists())

    def test_rules(self):
        with self.assertRaisesMessage(RevenueError, 'unsold'):
            shares.add_member(user_id=self.buyer.id, percent='1', by_user=self.boss)    # all 30% held
        shares.add_member(user_id=self.buyer.id, percent='0', by_user=self.boss)        # a member with 0% for now
        with self.assertRaisesMessage(RevenueError, 'already holds wallet'):
            shares.add_member(user_id=self.buyer.id, by_user=self.boss)
        with self.assertRaisesMessage(RevenueError, 'share controller'):
            shares.add_member(user_id=self.buyer.id, by_user=self.p2)
        player = User.objects.create_user('punter', 'pu@example.com', 'x')               # not a staff login
        with self.assertRaisesMessage(RevenueError, 'staff login'):
            shares.add_member(user_id=player.id, by_user=self.boss)

    def test_api(self):
        shares.set_share(slot=1, percent='6', by_user=self.boss, for_sale=False)
        res = self.api(self.boss).post(URL + 'member-add/', {'user_id': self.buyer.id, 'percent': '2.5'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        row = next(w for w in res.json()['wallets'] if w['holder'] == 'tendai')
        self.assertEqual(row['percent'], '2.50')
        res = self.api(self.p2).post(URL + 'member-add/', {'user_id': self.p3.id}, format='json')
        self.assertEqual(res.status_code, 400)


class PayoutTests(Base):
    def test_each_wallet_earns_its_own_share_and_the_unheld_part_goes_to_the_pool(self):
        days([1000] * 20)
        RevenueDay.objects.all().delete()
        cfg = RevenueSettings.load()
        cfg.started_on = timezone.localdate() - timedelta(days=1)
        cfg.save()
        shares.set_share(slot=1, percent='5', by_user=self.boss)
        shares.record_sale(buyer_id=self.buyer.id, percent='2.5', price='1', payment_reference='R', accepted_agreement=True, by_user=self.boss)
        with patch.object(services, 'day_ggr', return_value=D('1000')):
            services.close_days()
        day = RevenueDay.objects.get()
        # 5 + 10 + 10 + 2.5 = 27.5% held; 2.5% unsold stays in the pool.
        self.assertEqual((day.share_percent, day.shared, day.pool), (D('27.50'), D('275.00'), D('725.00')))
        buyer_wallet = ShareWallet.objects.get(holder=self.buyer)
        self.assertEqual(services.wallet_balance(buyer_wallet), D('25.00'))
        # Boss's 5% day share ($50) plus 90% of the $1 sale of share boss released ($0.90).
        self.assertEqual(services.wallet_balance(ShareWallet.objects.get(slot=1)), D('50.90'))


class SignerTests(Base):
    def test_small_holders_dont_cosign_audits(self):
        days([1000] * 30)
        shares.set_share(slot=1, percent='5', by_user=self.boss)
        shares.record_sale(buyer_id=self.buyer.id, percent='2', payment_reference='R', accepted_agreement=True, by_user=self.boss)
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
        self.assertEqual(mine['agreement']['version'], agreement.VERSION)
        res = self.api(self.buyer).post(URL + 'buy/', {'percent': '1', 'accepted_agreement': True}, format='json')
        self.assertEqual(res.status_code, 400)                                  # nothing unsold yet
        self.api(self.boss).post(URL + 'set/', {'slot': 1, 'percent': '5'}, format='json')
        res = self.api(self.buyer).post(URL + 'buy/', {'percent': '1'}, format='json')
        self.assertEqual(res.status_code, 400)                                  # agreement not accepted
        self.assertIn('agreement', res.json()['detail'])
        res = self.api(self.buyer).post(URL + 'buy/', {'percent': '1', 'accepted_agreement': True}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['sales'][0]['agreement_sha256'], agreement.TEXT_SHA256)
        sale_id = res.json()['sales'][0]['id']
        res = self.api(self.boss).post(f'{URL}sales/{sale_id}/', {'action': 'confirm', 'payment_reference': 'EC1'}, format='json')
        self.assertEqual(res.json()['sales'][0]['status'], 'confirmed')
        q = self.api(self.buyer).get(URL + 'quote/?percent=0.5').json()
        self.assertEqual(q['total'], '1800.00')
        # A superuser's cut of someone else applies at once: no approval.
        res = self.api(self.root).post(URL + 'set/', {'slot': 2, 'percent': '9'}, format='json').json()
        self.assertTrue(res['result']['applied'])
        self.assertEqual(self.pct(2), D('9.00'))
        self.assertEqual(self.api(self.p2).get(URL).json()['pending_for_me'], [])


class ResaleTests(Base):
    """Share a holder releases is sold for them: they get 90% of its part of the price."""

    def setUp(self):
        super().setUp()
        days([1000] * 30)                                      # 1% = $3,600

    def balance(self, slot):
        return services.wallet_balance(ShareWallet.objects.get(slot=slot))

    def test_releaser_gets_ninety_percent_and_the_house_ten(self):
        shares.set_share(slot=1, percent='6', by_user=self.boss)          # boss releases 4%
        sale = shares.record_sale(buyer_id=self.buyer.id, percent='2', payment_reference='R', accepted_agreement=True, by_user=self.boss)
        # 2% x $3,600 = $7,200: boss $6,480, house $720.
        self.assertEqual((self.balance(1), sale.house_amount), (D('6480.00'), D('720.00')))
        self.assertEqual(sale.seller_payouts, [{'slot': 1, 'holder': 'boss', 'percent': '2.00', 'amount': '6480.00'}])
        self.assertEqual(shares.released_percent(), D('2.00'))
        entry = ShareWallet.objects.get(slot=1).entries.get(kind='sale')
        self.assertEqual((entry.sale_id, entry.get_kind_display()), (sale.id, 'Your released share was sold'))

    def test_oldest_release_sells_first_across_holders(self):
        shares.set_share(slot=2, percent='9', by_user=self.p2)            # p2 releases 1% first
        shares.set_share(slot=3, percent='7', by_user=self.p3)            # then p3 releases 3%
        sale = shares.record_sale(buyer_id=self.buyer.id, percent='2', payment_reference='R', accepted_agreement=True, by_user=self.boss)
        # 1% from p2, 1% from p3: $3,240 each, house $720.
        self.assertEqual((self.balance(2), self.balance(3), sale.house_amount), (D('3240.00'), D('3240.00'), D('720.00')))
        self.assertEqual(ShareRelease.objects.get(wallet__slot=3).remaining, D('2.00'))

    def test_an_agreed_price_is_what_gets_split(self):
        shares.set_share(slot=1, percent='6', by_user=self.boss)
        shares.record_sale(buyer_id=self.buyer.id, percent='1', price='1000', payment_reference='R', accepted_agreement=True, by_user=self.boss)
        self.assertEqual(self.balance(1), D('900.00'))

    def test_giving_back_to_the_house_pays_nobody(self):
        shares.set_share(slot=1, percent='6', by_user=self.boss, for_sale=False)
        sale = shares.record_sale(buyer_id=self.buyer.id, percent='2', payment_reference='R', accepted_agreement=True, by_user=self.boss)
        self.assertEqual((self.balance(1), sale.house_amount, sale.seller_payouts), (D('0'), D('7200.00'), []))

    def test_share_nobody_released_is_the_houses(self):
        shares.update_share_settings(partner_pool_percent='35', by_user=self.boss)    # 5% new, house-owned
        shares.set_share(slot=1, percent='9', by_user=self.boss)                      # boss releases 1%
        sale = shares.record_sale(buyer_id=self.buyer.id, percent='3', payment_reference='R', accepted_agreement=True, by_user=self.boss)
        # Oldest release first: boss's 1% ($3,240 to boss); the other 2% is the house's.
        self.assertEqual((self.balance(1), sale.house_amount), (D('3240.00'), D('7560.00')))

    def test_an_admins_cut_is_sold_for_the_holder(self):
        shares.set_share(slot=2, percent='8', by_user=self.root)
        shares.record_sale(buyer_id=self.buyer.id, percent='2', payment_reference='R', accepted_agreement=True, by_user=self.boss)
        self.assertEqual(self.balance(2), D('6480.00'))

    def test_a_buyers_request_pays_the_releaser_when_confirmed(self):
        shares.set_share(slot=1, percent='6', by_user=self.boss)
        shares.approve_buyer(user_id=self.buyer.id, by_user=self.boss)
        sale = shares.request_purchase(by_user=self.buyer, percent='1', accepted_agreement=True)
        self.assertEqual(self.balance(1), D('0'))                          # not before payment
        shares.confirm_sale(sale.id, by_user=self.boss, payment_reference='EC1')
        self.assertEqual(self.balance(1), D('3240.00'))

    def test_unsold_release_can_be_taken_back(self):
        shares.set_share(slot=2, percent='6', by_user=self.p2)
        lot = ShareRelease.objects.get()
        with self.assertRaisesMessage(RevenueError, 'Only the holder'):
            shares.reclaim_release(lot.id, by_user=self.p3)
        shares.reclaim_release(lot.id, by_user=self.p2)
        self.assertEqual((self.pct(2), shares.released_percent()), (D('10.00'), D('0')))

    def test_reclaim_respects_buyers_waiting_to_pay(self):
        shares.set_share(slot=2, percent='8', by_user=self.p2)            # 2% released
        shares.approve_buyer(user_id=self.buyer.id, by_user=self.boss)
        shares.request_purchase(by_user=self.buyer, percent='1', accepted_agreement=True)
        with self.assertRaisesMessage(RevenueError, 'waiting to pay'):
            shares.reclaim_release(ShareRelease.objects.get().id, by_user=self.p2)

    def test_pool_cant_shrink_below_share_up_for_sale(self):
        shares.set_share(slot=1, percent='6', by_user=self.boss)
        with self.assertRaisesMessage(RevenueError, 'up for sale'):
            shares.update_share_settings(partner_pool_percent='27', by_user=self.boss)

    def test_seller_part_is_a_setting(self):
        shares.update_share_settings(seller_percent='100', by_user=self.boss)
        shares.set_share(slot=1, percent='6', by_user=self.boss)
        sale = shares.record_sale(buyer_id=self.buyer.id, percent='1', payment_reference='R', accepted_agreement=True, by_user=self.boss)
        self.assertEqual((self.balance(1), sale.house_amount), (D('3600.00'), D('0.00')))

    def test_payouts_can_be_withdrawn_like_earnings(self):
        shares.set_share(slot=2, percent='9', by_user=self.p2)
        shares.record_sale(buyer_id=self.buyer.id, percent='1', payment_reference='R', accepted_agreement=True, by_user=self.boss)
        w = services.request_withdrawal(user=self.p2, method='ecocash', account='0771234567')
        self.assertEqual(w.amount, D('3240.00'))


class AgreementTests(Base):
    def setUp(self):
        super().setUp()
        days([1000] * 30)
        shares.set_share(slot=1, percent='5', by_user=self.boss, for_sale=False)
        shares.approve_buyer(user_id=self.buyer.id, by_user=self.boss)

    def test_buyer_must_accept_and_acceptance_is_recorded(self):
        with self.assertRaisesMessage(RevenueError, 'must accept'):
            shares.request_purchase(by_user=self.buyer, percent='1')
        with self.assertRaisesMessage(RevenueError, 'must accept'):
            shares.request_purchase(by_user=self.buyer, percent='1', accepted_agreement='no')
        self.assertFalse(ShareSale.objects.exists())
        sale = shares.request_purchase(by_user=self.buyer, percent='1', accepted_agreement='true')
        self.assertEqual((sale.agreement_version, sale.agreement_sha256, sale.agreement_confirmed_by),
                         (agreement.VERSION, agreement.TEXT_SHA256, 'tendai'))
        self.assertIsNotNone(sale.agreement_accepted_at)

    def test_recorded_sale_needs_the_admin_to_confirm_the_buyer_accepted(self):
        with self.assertRaisesMessage(RevenueError, 'The buyer must accept'):
            shares.record_sale(buyer_id=self.buyer.id, percent='1', payment_reference='R', by_user=self.boss)
        sale = shares.record_sale(buyer_id=self.buyer.id, percent='1', payment_reference='R', accepted_agreement=True,
                                  by_user=self.boss)
        self.assertEqual((sale.status, sale.agreement_confirmed_by), (ShareSale.Status.CONFIRMED, 'boss'))

    def test_fingerprint_tracks_the_text(self):
        import hashlib
        self.assertEqual(len(agreement.TEXT_SHA256), 64)
        self.assertEqual(agreement.TEXT_SHA256, hashlib.sha256(agreement._canonical().encode()).hexdigest())
        p = agreement.payload()
        self.assertTrue(p['sections'] and all(s['paragraphs'] for s in p['sections']))


class ControllerTests(Base):
    """The founder (wallet 1's holder) and the configured user ids edit anyone's
    share at once, another controller's included."""

    def test_founder_cuts_and_hands_over_without_consent(self):
        self.assertTrue(shares.is_controller(self.boss))                      # holds wallet 1
        res = shares.set_share(slot=2, percent='4', by_user=self.boss)
        self.assertTrue(res['applied'])
        self.assertEqual(self.pct(2), D('4.00'))
        change = ShareChange.objects.get()
        self.assertIn('Applied by boss', change.decided_note)
        self.assertEqual(ShareRelease.objects.get().holder_id, self.p2.id)    # still sold for p2 (90%)
        res = shares.transfer_wallet(slot=3, new_holder_id=self.buyer.id, by_user=self.boss)
        self.assertTrue(res['applied'])
        self.assertEqual(ShareWallet.objects.get(slot=3).holder_id, self.buyer.id)

    def test_configured_ids_are_controllers_even_without_superuser(self):
        with override_settings(REVENUE_SHARE_CONTROLLER_IDS=[self.p3.id]):
            self.assertTrue(shares.is_controller(self.p3))
            self.assertFalse(shares.is_controller(self.p2))
            self.assertTrue(shares.set_share(slot=2, percent='5', by_user=self.p3, for_sale=False)['applied'])
            self.assertEqual(self.pct(2), D('5.00'))
            self.assertTrue(shares.set_share(slot=2, percent='7', by_user=self.p3)['applied'])   # raise from unsold
            self.assertEqual(sorted(shares.controller_names()), ['boss', 'p3'])
        self.assertFalse(shares.is_controller(self.p3))

    def test_another_controllers_share_changes_at_once_too(self):
        with override_settings(REVENUE_SHARE_CONTROLLER_IDS=[self.p2.id]):
            self.assertTrue(shares.set_share(slot=1, percent='5', by_user=self.p2)['applied'])   # p2 cutting the founder
            self.assertEqual(self.pct(1), D('5.00'))
            self.assertTrue(shares.set_share(slot=2, percent='5', by_user=self.boss)['applied'])  # the founder cutting p2
            self.assertEqual(self.pct(2), D('5.00'))

    def test_non_controllers_cannot_edit_others(self):
        with self.assertRaisesMessage(RevenueError, 'share controller'):
            shares.set_share(slot=3, percent='5', by_user=self.p2)
        with self.assertRaisesMessage(RevenueError, 'share controller'):
            shares.transfer_wallet(slot=3, new_holder_id=self.buyer.id, by_user=self.p2)

    def test_api_flags_and_controller_view(self):
        with override_settings(REVENUE_SHARE_CONTROLLER_IDS=[self.p3.id]):
            body = self.api(self.p3).get(URL).json()
            self.assertTrue(body['is_controller'])
            self.assertFalse(body['can_admin'])
            self.assertTrue(body['staff'])                                      # can pick a new holder
            protected = {w['slot']: w['protected'] for w in body['wallets']}
            self.assertEqual(protected, {1: False, 2: False, 3: False})                # nothing needs approval
            res = self.api(self.p3).post(URL + 'set/', {'slot': 2, 'percent': '6'}, format='json')
            self.assertTrue(res.json()['result']['applied'], res.content)
        self.assertFalse(self.api(self.p2).get(URL).json()['is_controller'])
