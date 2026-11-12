"""The operating pool's ledger and the founder's weekly audit against Paynow
and the payouts report."""
import io
from datetime import datetime, time, timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.revenue import audit, services
from apps.revenue.models import PoolAudit, PoolProposal, RevenueDay, RevenueSettings, ShareWallet
from apps.wallet.models import PaymentTransaction, WithdrawalRequest

PW = 'Str0ng-pass-123'
WEEK = audit.week_of(timezone.localdate()) - timedelta(days=7)      # last week: open for audit


def at(day, hour=12):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def csv_file(text, name='report.csv'):
    return SimpleUploadedFile(name, text.encode(), content_type='text/csv')


class Base(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser('boss', 'b@example.com', PW)
        self.other_boss = User.objects.create_superuser('other', 'o@example.com', PW)
        self.partner = User.objects.create_user('partner', 'p@example.com', PW, is_staff=True)
        self.clerk = User.objects.create_user('clerk', 'c@example.com', PW, is_staff=True)
        cfg = RevenueSettings.load()
        cfg.started_on = WEEK - timedelta(days=7)
        cfg.audits_from = WEEK
        cfg.save()
        services.update_settings(wallets=[{'slot': 1, 'holder_id': self.boss.id, 'label': 'Founder'},
                                          {'slot': 2, 'holder_id': self.partner.id}], by='boss')
        self.partner3 = User.objects.create_user('partner3', 'p3@example.com', PW, is_staff=True)
        services.update_settings(wallets=[{'slot': 3, 'holder_id': self.partner3.id}], by='boss')

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def deposit(self, ref, amount, day=WEEK, status='paid', provider_ref=''):
        tx = PaymentTransaction.objects.create(reference=ref, provider_ref=provider_ref, player_id=1, method='ecocash',
                                               phone='0771111111', amount=D(amount), status=status)
        PaymentTransaction.objects.filter(pk=tx.pk).update(completed_at=at(day) if status == 'paid' else None)
        return tx

    def payout(self, amount, fee='0', account='0772222222', reference='', day=WEEK):
        return WithdrawalRequest.objects.create(player_id=2, amount=D(amount), fee=D(fee), method='ecocash',
                                                account_number=account, status='paid', reference=reference,
                                                decided_at=at(day), decided_by='boss')


class LedgerTests(Base):
    def test_running_balance_and_affiliate_breakdown(self):
        RevenueDay.objects.create(day=WEEK, ggr=D('1000'), share_percent=D('10'), share_each=D('100'), pool=D('700'),
                                  affiliate_costs=D('50'), base=D('1000'))
        RevenueDay.objects.create(day=WEEK + timedelta(days=1), ggr=D('500'), share_percent=D('10'), share_each=D('50'),
                                  pool=D('350'), base=D('500'))
        services.record_expense(day=WEEK, category='ai', amount='45.50', note='Claude', by='boss')
        ledger = audit.pool_ledger()
        self.assertEqual([r['balance'] for r in ledger['rows']], ['700.00', '650.00', '604.50', '954.50'])
        self.assertEqual((ledger['in'], ledger['out'], ledger['closing']), ('1050.00', '95.50', '954.50'))
        later = audit.pool_ledger(start=WEEK + timedelta(days=1))
        self.assertEqual((later['opening'], len(later['rows'])), ('604.50', 1))

    def test_holders_can_audit_the_pool_other_staff_cannot(self):
        self.assertEqual(self.api(self.partner).get('/api/admin/revenue-share/pool/').status_code, 200)
        self.assertEqual(self.api(self.partner).get('/api/admin/revenue-share/audits/').status_code, 200)
        self.assertIn('pool', self.api(self.partner).get('/api/admin/revenue-share/').json())
        self.assertEqual(self.api(self.clerk).get('/api/admin/revenue-share/pool/').status_code, 403)
        self.assertEqual(self.api(self.clerk).get('/api/admin/revenue-share/audits/').status_code, 403)


class DepositMatchTests(Base):
    def test_paynow_report_is_matched_line_by_line(self):
        self.deposit('BB-1', '10')                               # matched
        self.deposit('BB-2', '25')                               # credited, not in Paynow's report
        self.deposit('BB-3', '5', status='pending')              # Paynow paid, never credited
        self.deposit('BB-4', '20')                               # amount differs
        self.deposit('BB-5', '7', day=WEEK + timedelta(days=7))  # next week (timing)
        report = ('Date,Reference,Paynow Reference,Amount,Status\n'
                  f'{WEEK},BB-1,111,10.00,Paid\n'
                  f'{WEEK},bb-3,113,"$5.00",Awaiting Delivery\n'
                  f'{WEEK},BB-4,114,22.00,Paid\n'
                  f'{WEEK},BB-5,115,7.00,Paid\n'
                  f'{WEEK},ZZ-9,119,3.00,Paid\n'
                  f'{WEEK},BB-6,116,9.00,Cancelled\n')
        a = audit.upload(WEEK, 'paynow', user=self.boss, file=csv_file(report))
        r = a.paynow_result
        self.assertEqual(r['counts'], {'matched': 1, 'missing_from_report': 1, 'not_credited': 1, 'amount_mismatch': 1,
                                       'other_week': 1, 'unknown': 1})
        self.assertEqual((r['report_total'], r['system_total'], r['skipped'], r['balanced']), ('47.00', '55.00', 1, False))
        self.assertEqual({p['issue']: p['reference'] for p in r['problems']}['missing_from_report'], 'BB-2')
        self.assertEqual(a.status, PoolAudit.Status.OPEN)       # still waiting for the payouts report

    def test_excel_with_a_title_above_the_header(self):
        import openpyxl
        book = openpyxl.Workbook()
        ws = book.active
        ws.append(['Paynow transaction history'])
        ws.append([])
        ws.append(['Created', 'Merchant Reference', 'Amount', 'Status'])
        ws.append([datetime.combine(WEEK, time(12)), 'BB-1', 10, 'Paid'])
        buf = io.BytesIO()
        book.save(buf)
        self.deposit('BB-1', '10')
        a = audit.upload(WEEK, 'paynow', user=self.boss,
                         file=SimpleUploadedFile('history.xlsx', buf.getvalue()))
        self.assertTrue(a.paynow_result['balanced'])
        self.assertEqual(a.paynow_result['columns']['reference'], 'Merchant Reference')

    def test_unreadable_reports_are_refused_with_a_reason(self):
        with self.assertRaisesMessage(audit.AuditError, 'Amount column'):
            audit.upload(WEEK, 'paynow', user=self.boss, file=csv_file('a,b\n1,2\n'))
        with self.assertRaisesMessage(audit.AuditError, 'PDF'):
            audit.upload(WEEK, 'paynow', user=self.boss, file=SimpleUploadedFile('statement.pdf', b'%PDF-1.4'))

    def test_a_pdf_statement_can_be_checked_by_its_total(self):
        self.deposit('BB-1', '10')
        a = audit.upload(WEEK, 'paynow', user=self.boss, total='10.00')
        self.assertEqual((a.paynow_result['manual'], a.paynow_result['balanced']), (True, True))


class PayoutMatchTests(Base):
    def test_founders_payouts_report_is_matched(self):
        by_ref = self.payout('50', fee='2.50', reference='MP1234')
        by_number = self.payout('20', fee='1', account='+263 77 333 4444')
        forgotten = self.payout('15')
        report = ('Phone,Reference,Amount\n'
                  '0772222222,mp1234,47.50\n'        # sent after the fee
                  '0773334444,,19.00\n'
                  '0779999999,X1,30.00\n')            # paid with no request on the platform
        a = audit.upload(WEEK, 'payouts', user=self.boss, file=csv_file(report))
        r = a.payouts_result
        self.assertEqual(r['counts'], {'matched': 2, 'unknown': 1, 'missing_from_report': 1})
        missing = [p for p in r['problems'] if p['issue'] == 'missing_from_report'][0]
        self.assertEqual(missing['request_id'], forgotten.id)
        self.assertEqual((r['report_total'], r['system_total']), ('96.50', '81.50'))
        del by_ref, by_number


class CosignTests(Base):
    def balanced_week(self):
        self.deposit('BB-1', '10')
        self.payout('8')
        RevenueDay.objects.create(day=WEEK, ggr=D('100'), base=D('100'), share_percent=D('10'), share_each=D('10'), pool=D('70'))
        audit.upload(WEEK, 'paynow', user=self.boss, file=csv_file('Reference,Amount\nBB-1,10\n'))
        return audit.upload(WEEK, 'payouts', user=self.boss, file=csv_file('Phone,Amount\n0772222222,8\n'))

    def test_founder_submits_and_every_partner_must_cosign(self):
        self.balanced_week()
        with self.assertRaisesMessage(audit.AuditError, 'statement'):
            audit.submit(WEEK, user=self.boss, declared_balance='70', payouts_source='own sheet')
        with self.assertRaisesMessage(audit.AuditError, 'founder'):
            audit.submit(WEEK, user=self.partner, declared_balance='70', payouts_source='ecocash')
        a = audit.submit(WEEK, user=self.boss, declared_balance='70.00', payouts_source='ecocash')
        self.assertEqual(a.status, PoolAudit.Status.SUBMITTED)
        self.assertEqual(audit.outstanding(a), ['partner', 'partner3'])
        a = audit.cosign(WEEK, user=self.partner, decision='approve')
        self.assertEqual(a.status, PoolAudit.Status.SUBMITTED)
        with self.assertRaisesMessage(audit.AuditError, 'co-sign'):
            audit.cosign(WEEK, user=self.clerk, decision='approve')
        a = audit.cosign(WEEK, user=self.partner3, decision='approve')
        self.assertEqual((a.status, a.snapshot['deposits']['total']), (PoolAudit.Status.APPROVED, '10.00'))
        self.deposit('BB-LATE', '99')                           # a later change can't move an approved week
        self.assertEqual(audit.audit_row(PoolAudit.objects.get(week_start=WEEK))['system']['deposits']['total'], '10.00')
        with self.assertRaisesMessage(services.RevenueError, 'locked'):
            services.record_expense(day=WEEK, category='ai', amount='1', by='boss')
        with self.assertRaisesMessage(audit.AuditError, 'approved'):
            audit.upload(WEEK, 'paynow', user=self.boss, total='1')

    def test_declared_balance_must_match_the_ledger_or_be_explained(self):
        self.balanced_week()
        services.record_expense(day=WEEK + timedelta(days=1), category='ai', amount='20', by='boss')
        with self.assertRaisesMessage(audit.AuditError, 'explain'):
            audit.submit(WEEK, user=self.boss, declared_balance='30', payouts_source='bank')
        a = audit.submit(WEEK, user=self.boss, declared_balance='30', payouts_source='bank',
                         note='Paid $20 cash for an advert, receipt missing')
        row = audit.audit_row(a)
        self.assertEqual((row['expected_balance'], row['declared_balance'], row['balance_difference']), ('50.00', '30.00', '-20.00'))

    def test_a_dispute_sends_it_back_and_resubmitting_needs_fresh_signatures(self):
        self.balanced_week()
        audit.submit(WEEK, user=self.boss, declared_balance='70', payouts_source='ecocash')
        audit.cosign(WEEK, user=self.partner, decision='approve')
        with self.assertRaisesMessage(audit.AuditError, 'dispute'):
            audit.cosign(WEEK, user=self.partner3, decision='reject', note='no')
        a = audit.cosign(WEEK, user=self.partner3, decision='reject', note='Where is the hosting invoice?')
        self.assertEqual(a.status, PoolAudit.Status.DISPUTED)
        with self.assertRaisesMessage(audit.AuditError, 'co-signatures'):
            audit.cosign(WEEK, user=self.partner, decision='approve')
        a = audit.submit(WEEK, user=self.boss, declared_balance='70', payouts_source='ecocash', note='Invoice attached in chat')
        self.assertEqual(audit.outstanding(a), ['partner', 'partner3'])     # earlier approvals cleared

    def test_unbalanced_reports_need_an_explanation(self):
        self.deposit('BB-1', '10')
        audit.upload(WEEK, 'paynow', user=self.boss, total='9')
        audit.upload(WEEK, 'payouts', user=self.boss, total='0')
        with self.assertRaisesMessage(audit.AuditError, 'explain'):
            audit.submit(WEEK, user=self.boss, declared_balance='0', payouts_source='ecocash', note='ok')
        a = audit.submit(WEEK, user=self.boss, declared_balance='0', payouts_source='ecocash',
                         note='Paynow fee of $1 taken at source.')
        self.assertEqual(a.status, PoolAudit.Status.SUBMITTED)

    def test_api_flow_and_private_file_download(self):
        self.deposit('BB-1', '10')
        boss = self.api(self.boss)
        weeks = boss.get('/api/admin/revenue-share/audits/').json()
        self.assertTrue(weeks['is_founder'])
        self.assertEqual([a['week_start'] for a in weeks['audits']], [str(WEEK)])
        res = boss.post(f'/api/admin/revenue-share/audits/{WEEK}/upload/',
                        {'kind': 'paynow', 'file': csv_file('Reference,Amount\nBB-1,10\n')}, format='multipart')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['paynow']['balanced'])
        boss.post(f'/api/admin/revenue-share/audits/{WEEK}/upload/', {'kind': 'payouts', 'total': '0'}, format='json')
        res = boss.post(f'/api/admin/revenue-share/audits/{WEEK}/submit/',
                        {'declared_balance': '0', 'payouts_source': 'ecocash'}, format='json')
        self.assertEqual(res.json()['status'], 'submitted', res.content)
        res = self.api(self.partner).post(f'/api/admin/revenue-share/audits/{WEEK}/cosign/', {'decision': 'approve'}, format='json')
        self.assertEqual(res.json()['outstanding'], ['partner3'])
        url = f'/api/admin/revenue-share/audits/{WEEK}/file/paynow/'
        self.assertEqual(self.api(self.partner).get(url).status_code, 200)
        self.assertEqual(self.api(self.clerk).get(url).status_code, 403)
        self.assertEqual(APIClient().get(url).status_code, 401)


class GovernanceTests(Base):
    def setUp(self):
        super().setUp()
        cfg = RevenueSettings.load()
        cfg.started_on = cfg.audits_from = WEEK - timedelta(days=14)
        cfg.save()
        audit.ensure_weeks()

    def test_one_missed_week_warns_two_in_a_row_lock_the_money_controls(self):
        first = WEEK - timedelta(days=14)
        g = audit.governance(now=audit.deadline(first) + timedelta(hours=1))
        self.assertEqual((g['locked'], len(g['missed']), g['warning']), (False, 1, True))
        self.assertIn('boss (submit)', g['missed'][0]['waiting_for'])
        g = audit.governance()
        self.assertTrue(g['locked'])
        self.assertIn('boss (submit)', g['repeat_offenders'])
        with self.assertRaisesMessage(services.RevenueError, 'Locked'):
            services.record_expense(day=timezone.localdate(), category='ai', amount='5', by='boss')
        with self.assertRaisesMessage(services.RevenueError, 'Locked'):
            services.request_withdrawal(user=self.partner, method='ecocash', account='0771234567')
        with self.assertRaisesMessage(services.RevenueError, 'Locked'):
            services.update_settings(share_percent='20', by='boss')
        with self.assertRaisesMessage(services.RevenueError, 'Locked'):
            audit.propose(user=self.boss, kind='promotion', amount='1', note='Weekend promo')
        # Audits can always be caught up; once the missed weeks are approved, it unlocks.
        for week in (first, first + timedelta(days=7)):
            audit.upload(week, 'paynow', user=self.boss, total='0')
            audit.upload(week, 'payouts', user=self.boss, total='0')
            audit.submit(week, user=self.boss, declared_balance='0', payouts_source='ecocash')
            audit.cosign(week, user=self.partner, decision='approve')
            audit.cosign(week, user=self.partner3, decision='approve')
        self.assertFalse(audit.governance()['locked'])

    def test_a_partner_not_cosigning_counts_against_them(self):
        first = WEEK - timedelta(days=14)
        for week in (first, first + timedelta(days=7)):
            audit.upload(week, 'paynow', user=self.boss, total='0')
            audit.upload(week, 'payouts', user=self.boss, total='0')
            audit.submit(week, user=self.boss, declared_balance='0', payouts_source='ecocash')
            audit.cosign(week, user=self.partner, decision='approve')
        g = audit.governance()
        self.assertTrue(g['locked'])
        self.assertEqual(g['repeat_offenders'], ['partner3'])

    def test_weeks_before_audits_started_never_count(self):
        cfg = RevenueSettings.load()
        cfg.audits_from = audit.week_of(timezone.localdate())
        cfg.save()
        self.assertEqual((audit.governance()['locked'], audit.governance()['missed']), (False, []))


class ProposalTests(Base):
    def setUp(self):
        super().setUp()
        RevenueDay.objects.create(day=WEEK, ggr=D('1000'), base=D('1000'), share_percent=D('10'), share_each=D('100'), pool=D('700'))

    def test_equal_payout_needs_every_partner_then_splits_three_ways(self):
        p = audit.propose(user=self.partner, kind='disburse', amount='300', note='Quarterly split')
        self.assertEqual(p.status, 'open')
        audit.vote(p.id, user=self.boss, decision='approve')
        self.assertEqual(PoolProposal.objects.get(pk=p.id).status, 'open')
        p = audit.vote(p.id, user=self.partner3, decision='approve')
        self.assertEqual(p.status, 'done')
        self.assertEqual([str(services.wallet_balance(w)) for w in ShareWallet.ensure()], ['100.00', '100.00', '100.00'])
        self.assertEqual(audit.pool_available(), D('400.00'))
        with self.assertRaisesMessage(services.RevenueError, 'agreed'):
            services.delete_expense(p.expense_id, by='boss')

    def test_a_single_rejection_stops_a_promotion(self):
        p = audit.propose(user=self.boss, kind='promotion', amount='200', note='Derby day free bets')
        p = audit.vote(p.id, user=self.partner, decision='reject', note='Too much')
        self.assertEqual(p.status, 'rejected')
        self.assertEqual(audit.pool_available(), D('700.00'))

    def test_limits(self):
        with self.assertRaisesMessage(services.RevenueError, 'only holds'):
            audit.propose(user=self.boss, kind='promotion', amount='701', note='Too big')
        with self.assertRaisesMessage(services.RevenueError, 'partners'):
            audit.propose(user=self.clerk, kind='promotion', amount='1', note='Not a partner')

    def test_api(self):
        res = self.api(self.partner).post('/api/admin/revenue-share/proposals/',
                                          {'kind': 'promotion', 'amount': '50', 'note': 'Cup final promo'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        pid = res.json()['id']
        listing = self.api(self.boss).get('/api/admin/revenue-share/proposals/').json()
        self.assertTrue(listing['proposals'][0]['can_vote'])
        self.assertEqual(listing['proposals'][0]['waiting_for'], ['boss', 'partner3'])
        res = self.api(self.partner).post(f'/api/admin/revenue-share/proposals/{pid}/', {'cancel': True}, format='json')
        self.assertEqual(res.json()['status'], 'cancelled')


class WholeAdminLockTests(Base):
    """Two missed weeks in a row make every staff change fail, everywhere."""

    def api(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken
        c = APIClient()                     # a real token: the lock reads it before DRF does
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        return c

    def lock(self):
        cfg = RevenueSettings.load()
        cfg.started_on = cfg.audits_from = WEEK - timedelta(days=14)
        cfg.save()
        audit.ensure_weeks()
        from django.core.cache import cache
        cache.clear()

    def test_staff_changes_are_refused_reads_and_audits_still_work(self):
        boss = self.api(self.boss)
        self.lock()
        res = boss.post('/api/admin/revenue-share/expenses/', {'day': str(timezone.localdate()), 'category': 'ai', 'amount': '1'}, format='json')
        self.assertEqual(res.status_code, 423)
        self.assertIn('read-only', res.json()['detail'])
        self.assertEqual(boss.post('/api/events/', {'name': 'X v Y'}, format='json').status_code, 423)   # outside /admin/ too
        self.assertEqual(boss.get('/api/admin/revenue-share/').status_code, 200)                     # reading is fine
        self.assertTrue(self.api(self.clerk).get('/api/admin/lock-status/').json()['locked'])
        # The way out stays open: upload, submit, co-sign.
        first = WEEK - timedelta(days=14)
        for week in (first, first + timedelta(days=7)):
            for kind in ('paynow', 'payouts'):
                self.assertEqual(boss.post(f'/api/admin/revenue-share/audits/{week}/upload/', {'kind': kind, 'total': '0'},
                                           format='json').status_code, 200)
            self.assertEqual(boss.post(f'/api/admin/revenue-share/audits/{week}/submit/',
                                       {'declared_balance': '0', 'payouts_source': 'ecocash'}, format='json').status_code, 200)
            for partner in (self.partner, self.partner3):
                self.api(partner).post(f'/api/admin/revenue-share/audits/{week}/cosign/', {'decision': 'approve'}, format='json')
        self.assertFalse(self.api(self.clerk).get('/api/admin/lock-status/').json()['locked'])
        res = boss.post('/api/admin/revenue-share/expenses/', {'day': str(timezone.localdate()), 'category': 'ai', 'amount': '1'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)

    def test_players_are_not_affected(self):
        from apps.accounts import services as accounts
        self.lock()
        player = accounts.register_player(username='punter', email='pu@example.com', password=PW)
        res = self.api(player.user).post('/api/notifications/read-all/')
        self.assertNotEqual(res.status_code, 423)

    def test_django_admin_is_read_only_too(self):
        from django.test import Client
        self.lock()
        c = Client()
        c.force_login(self.boss)
        res = c.post(f'/django-admin/auth/user/{self.clerk.id}/change/', {'username': 'renamed'})
        self.assertEqual(res.status_code, 423)
        self.clerk.refresh_from_db()
        self.assertEqual(self.clerk.username, 'clerk')
