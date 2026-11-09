"""Fraud players leave through the fraud system: confirm the case as fraud and
delete the account, one at a time or in bulk — superuser-only, reviewed first,
with the number typed to confirm. The case, signals and identity links stay."""
from __future__ import annotations

import secrets
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.accounts.models import AuditLog, Player
from apps.risk.models import RiskCase, RiskSignal
from apps.wallet import services as wallet_services

BULK = '/api/admin/risk/cases/bulk/'


def new_player(name):
    return account_services.register_player(username=name, email=f'{name}@example.com',
                                            password=secrets.token_urlsafe(16), currency='USD')


class PurgeTests(TestCase):
    def setUp(self):
        self.players = [new_player(f'fraud_{i}') for i in range(3)]
        self.cases = [RiskCase.objects.create(player_id=p.id, action=RiskCase.Action.SUSPENDED, score=100,
                                              reason='Linked accounts') for p in self.players]
        self.ids = [c.id for c in self.cases]
        self.boss = APIClient()
        self.boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))

    def bulk(self, client=None, **body):
        return (client or self.boss).post(BULK, {'decision': 'confirm_delete', 'case_ids': self.ids, **body}, format='json')

    def alive(self):
        return Player.objects.filter(pk__in=[p.id for p in self.players]).count()

    def test_only_a_superuser(self):
        self.assertEqual(self.bulk(self.staff, note='fraud ring', confirm='DELETE 3').status_code, 403)
        self.assertEqual(self.alive(), 3)

    def test_dry_run_changes_nothing_and_shows_what_is_forfeited(self):
        wallet_services.credit(player_id=self.players[0].id, amount=Decimal('40'), kind='deposit', idempotency_key='f:0')
        body = self.bulk(dry_run=True).json()
        self.assertEqual((body['dry_run'], body['deletable'], body['confirm_phrase'], body['balance_forfeited']),
                         (True, 3, 'DELETE 3', '40.00'))
        self.assertEqual(self.alive(), 3)
        self.assertEqual(RiskCase.objects.filter(status=RiskCase.Status.OPEN).count(), 3)

    def test_needs_the_typed_number_and_a_note(self):
        for confirm in ('', 'DELETE 2', 'delete 3'):
            self.assertEqual(self.bulk(note='fraud ring', confirm=confirm).status_code, 400, confirm)
        self.assertEqual(self.bulk(note=' ', confirm='DELETE 3').status_code, 400)
        self.assertEqual(self.alive(), 3)

    def test_confirm_and_delete_removes_the_players_even_with_money_and_keeps_the_record(self):
        wallet_services.credit(player_id=self.players[0].id, amount=Decimal('40'), kind='deposit', idempotency_key='f:0')
        RiskSignal.objects.create(player_id=self.players[1].id, code='signup_shared_ip', severity='low', points=10,
                                  detail='Shared IP', dedupe_key='purge:test')
        res = self.bulk(note='Confirmed multi-account ring', confirm='DELETE 3')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual((res.json()['done'], res.json()['failed_count']), (3, 0))
        self.assertEqual(self.alive(), 0)
        self.assertFalse(User.objects.filter(username__startswith='fraud_').exists())
        for case in RiskCase.objects.filter(pk__in=self.ids):
            self.assertEqual(case.status, RiskCase.Status.CONFIRMED)
            self.assertEqual(case.decided_by, 'boss')
            self.assertIn('Confirmed multi-account ring', case.decision_note)
        self.assertIn('fraud_0 deleted ($40.00 forfeited)', RiskCase.objects.get(pk=self.ids[0]).decision_note)
        self.assertTrue(RiskSignal.objects.filter(player_id=self.players[1].id).exists())   # evidence survives
        self.assertEqual(AuditLog.objects.filter(event_type='player_deleted').count(), 3)
        self.assertEqual(AuditLog.objects.filter(event_type='risk_cases_confirmed_deleted').count(), 1)

    def test_staff_accounts_closed_cases_and_missing_players_are_skipped(self):
        User.objects.filter(pk=self.players[0].user_id).update(is_staff=True)
        RiskCase.objects.filter(pk=self.ids[1]).update(status=RiskCase.Status.DISMISSED)
        reasons = {s['case_id']: s['reason'] for s in self.bulk(dry_run=True).json()['skipped']}
        self.assertEqual(reasons, {self.ids[0]: 'Staff account', self.ids[1]: 'Case already closed'})
        res = self.bulk(note='fraud ring', confirm='DELETE 1').json()
        self.assertEqual((res['done'], res['skipped_count']), (1, 2))
        self.assertEqual(self.alive(), 2)

    def test_a_list_that_changed_after_review_is_caught(self):
        RiskCase.objects.filter(pk=self.ids[2]).update(status=RiskCase.Status.DISMISSED)   # decided meanwhile
        res = self.bulk(note='fraud ring', confirm='DELETE 3')
        self.assertEqual(res.status_code, 400)
        self.assertIn('DELETE 2', res.json()['detail'])
        self.assertEqual(self.alive(), 3)

    def test_too_many_cases_are_refused(self):
        from apps.risk import services
        original = services.MAX_PURGE
        services.MAX_PURGE = 2
        try:
            res = self.bulk(note='fraud ring', confirm='DELETE 3')
        finally:
            services.MAX_PURGE = original
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.alive(), 3)

    def test_a_single_case_needs_the_username_typed(self):
        url = f'/api/admin/risk/cases/{self.ids[0]}/decide/'
        res = self.boss.post(url, {'decision': 'confirm_delete', 'note': 'fraud', 'confirm': 'wrong'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.alive(), 3)
        res = self.boss.post(url, {'decision': 'confirm_delete', 'note': 'confirmed fraud', 'confirm': 'fraud_0'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['status'], 'confirmed')
        self.assertEqual(self.alive(), 2)
        self.assertEqual(self.staff.post(url, {'decision': 'confirm_delete', 'confirm': 'fraud_1'}, format='json').status_code, 403)

    def test_bulk_dismiss_and_confirm_without_deleting(self):
        res = self.boss.post(BULK, {'decision': 'dismiss', 'case_ids': self.ids[:2], 'note': 'innocent family'}, format='json').json()
        self.assertEqual((res['done'], res['skipped_count']), (2, 0))
        res = self.boss.post(BULK, {'decision': 'confirm', 'case_ids': self.ids, 'note': 'confirmed'}, format='json').json()
        self.assertEqual((res['done'], res['skipped_count']), (1, 2))      # two were already closed
        self.assertEqual(self.alive(), 3)
        self.assertEqual(self.boss.post(BULK, {'decision': 'confirm', 'case_ids': self.ids, 'note': ' '}, format='json').status_code, 400)

    def test_the_players_list_points_deletion_of_fraud_players_here(self):
        res = self.boss.post('/api/players/bulk/', {'action': 'delete', 'ids': [self.players[0].id], 'dry_run': True}, format='json').json()
        self.assertEqual(res['deletable'], 0)
        self.assertIn('Confirm fraud & delete', res['skipped'][0]['reason'])
