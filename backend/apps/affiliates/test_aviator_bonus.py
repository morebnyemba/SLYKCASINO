"""Agents earn on their customers' lost Aviator bets too; bonus-wallet tickets
and free bets never pay an agent."""
import secrets
from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.affiliates import services
from apps.affiliates.models import Affiliate, AffiliateProgramme, Commission
from apps.affiliates.testing import backdate_links
from apps.jet.models import JetBet, JetRound
from apps.sportsbook.models import Bet, BetSlip

PASSWORD = secrets.token_urlsafe(16)


class Base(TestCase):
    def setUp(self):
        agent = accounts.create_player(username='agent')
        self.agent = services.apply(player_id=agent.id, code='AGENT')
        services.set_status(self.agent.id, Affiliate.Status.ACTIVE)
        self.customer = accounts.create_player(username='customer')
        services.attach_referral(player_id=self.customer.id, code='AGENT')
        backdate_links()
        AffiliateProgramme.objects.update(aviator_commission_since=timezone.now() - timedelta(days=30))
        self.round = JetRound.objects.create(server_seed='s', seed_hash='h', crash_point=D('1.20'),
                                             house_edge_percent=D('3'), betting_ends_at=timezone.now())
        self.slot = 0

    def aviator(self, stake, ago=timedelta(minutes=10), status='lost', wallet='deposit', is_free=False):
        self.slot += 1
        return JetBet.objects.create(round=self.round, player_id=self.customer.id, display_name='c***r', slot=self.slot,
                                     stake=D(stake), wallet=wallet, status=status, is_free=is_free,
                                     settled_at=timezone.now() - ago)

    def sports(self, stake, wallet='deposit', ago=timedelta(minutes=10), slip=False):
        if slip:
            return BetSlip.objects.create(wallet=wallet, player_id=self.customer.id, stake=D(stake), combined_odds=D('9'),
                                          status='lost', settled_at=timezone.now() - ago)
        return Bet.objects.create(wallet=wallet, player_id=self.customer.id, stake=D(stake), odds=D('2'), event='x',
                                  status='lost', settled_at=timezone.now() - ago)

    def credited(self):
        return dict(Commission.objects.filter(kind='stake').values_list('ticket', 'amount'))


class AviatorTests(Base):
    def test_lost_aviator_bets_earn_the_agent_their_percent(self):
        lost = self.aviator('10')
        self.aviator('20', status='cashed')                       # won: nothing
        self.aviator('5', status='refunded')
        self.aviator('1', is_free=True, wallet='bonus')           # free bet: no stake was taken
        self.assertEqual(services.credit_losing_tickets(), 1)
        self.assertEqual(self.credited(), {f'A{lost.id}': D('3.00')})
        self.assertEqual(services.credit_losing_tickets(), 0)    # once

    def test_programme_can_set_a_separate_aviator_rate(self):
        services.update_programme(aviator_commission_percent='10')
        lost = self.aviator('50')
        sport = self.sports('50')
        services.credit_losing_tickets()
        self.assertEqual(self.credited(), {f'A{lost.id}': D('5.00'), f'S{sport.id}': D('15.00')})
        c = Commission.objects.get(ticket=f'A{lost.id}')
        self.assertEqual(c.rate, D('10'))
        services.update_programme(aviator_commission_percent='')
        self.assertIsNone(AffiliateProgramme.load().aviator_commission_percent)

    def test_rounds_before_the_start_never_pay(self):
        """Switching it on (and the deploy) never back-pays earlier rounds, even
        through the 35-day catch-up."""
        old = self.aviator('100', ago=timedelta(days=31))
        self.assertEqual(services.catch_up_losing_tickets(), 0)
        rows = {r['ticket']: r for r in services.ticket_audit(Affiliate.objects.get(pk=self.agent.pk))['tickets']}
        self.assertEqual(rows[f'A{old.id}']['reason'], 'aviator_before_start')

    def test_kill_switch(self):
        services.update_programme(aviator_commission=False)
        during = self.aviator('10')
        self.assertEqual(services.catch_up_losing_tickets(), 0)
        rows = {r['ticket']: r for r in services.ticket_audit(Affiliate.objects.get(pk=self.agent.pk))['tickets']}
        self.assertEqual(rows[f'A{during.id}']['reason'], 'aviator_off')
        services.update_programme(aviator_commission=True)       # back on: from now, not for the time it was off
        self.assertEqual(services.catch_up_losing_tickets(), 0)
        self.assertGreater(AffiliateProgramme.load().aviator_commission_since, during.settled_at)

    def test_dashboard_counts_aviator_losses(self):
        self.aviator('10', ago=timedelta(minutes=1))
        self.sports('20', ago=timedelta(minutes=1))
        self.sports('30', wallet='bonus', ago=timedelta(minutes=1))
        stats = services.dashboard(Affiliate.objects.get(pk=self.agent.pk))
        self.assertEqual((stats['lost_stakes_today'], stats['losing_tickets_today']), (D('30'), 2))


class BonusTests(Base):
    def test_bonus_wallet_tickets_never_pay_the_agent(self):
        bonus_single = self.sports('40', wallet='bonus')
        bonus_multi = self.sports('15', wallet='bonus', slip=True)
        real = self.sports('10', wallet='winnings')
        self.assertEqual(services.credit_losing_tickets(), 1)
        self.assertEqual(services.catch_up_losing_tickets(), 0)
        self.assertEqual(services.credit_missed_tickets(self.agent.id), 0)
        self.assertEqual(self.credited(), {f'S{real.id}': D('3.00')})
        audit = services.ticket_audit(Affiliate.objects.get(pk=self.agent.pk))
        rows = {r['ticket']: r for r in audit['tickets']}
        self.assertEqual((rows[f'S{bonus_single.id}']['reason'], rows[f'M{bonus_multi.id}']['reason']), ('bonus', 'bonus'))
        self.assertEqual(audit['counts']['missing'], 0)
        self.assertEqual(services.crediting_health()['missing_tickets'], 0)


class ProgrammeApiTests(Base):
    def test_admin_edits_aviator_settings(self):
        api = APIClient()
        api.force_authenticate(User.objects.create_user('ops', 'ops@example.com', PASSWORD, is_staff=True))
        body = api.get('/api/admin/affiliate-programme/').json()
        self.assertEqual((body['aviator_commission'], body['aviator_commission_percent']), (True, None))
        res = api.put('/api/admin/affiliate-programme/', {**body, 'aviator_commission_percent': '12.5'}, format='json')
        self.assertEqual(res.json()['aviator_commission_percent'], '12.50')
        res = api.put('/api/admin/affiliate-programme/', {'aviator_commission': False}, format='json')
        self.assertEqual((res.json()['aviator_commission'], res.json()['aviator_commission_percent']), (False, '12.50'))
        res = api.put('/api/admin/affiliate-programme/', {'aviator_commission_percent': '101'}, format='json')
        self.assertEqual(res.status_code, 400)
