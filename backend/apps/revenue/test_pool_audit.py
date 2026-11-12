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
from apps.revenue.models import PoolAudit, RevenueDay, RevenueSettings, ShareWallet
from apps.wallet.models import PaymentTransaction, WithdrawalRequest

PW = 'Str0ng-pass-123'
WEEK = audit.week_of(timezone.localdate()) - timedelta(days=14)


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
        cfg.save()
        services.update_settings(wallets=[{'slot': 1, 'holder_id': self.boss.id, 'label': 'Founder'},
                                          {'slot': 2, 'holder_id': self.partner.id}], by='boss')

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


class SignOffTests(Base):
    def balanced_week(self):
        self.deposit('BB-1', '10')
        self.payout('8')
        audit.upload(WEEK, 'paynow', user=self.boss, file=csv_file('Reference,Amount\nBB-1,10\n'))
        return audit.upload(WEEK, 'payouts', user=self.boss, file=csv_file('Phone,Amount\n0772222222,8\n'))

    def test_only_the_founder_uploads_and_signs(self):
        with self.assertRaisesMessage(audit.AuditError, 'founder'):
            audit.upload(WEEK, 'paynow', user=self.other_boss, total='0')
        res = self.api(self.partner).post(f'/api/admin/revenue-share/audits/{WEEK}/upload/', {'kind': 'paynow', 'total': '0'})
        self.assertEqual(res.status_code, 400)
        services.update_settings(founder_id=self.other_boss.id, by='boss')
        self.assertTrue(audit.is_founder(self.other_boss))
        self.assertFalse(audit.is_founder(self.boss))
        with self.assertRaisesMessage(services.RevenueError, 'superuser'):
            services.update_settings(founder_id=self.partner.id, by='boss')

    def test_sign_off_freezes_the_week_and_locks_its_costs(self):
        a = self.balanced_week()
        self.assertEqual(a.status, PoolAudit.Status.REVIEW)
        expense = services.record_expense(day=WEEK + timedelta(days=2), category='hosting', amount='12', by='boss')
        a = audit.sign_off(WEEK, user=self.boss)
        self.assertEqual((a.status, a.signed_by, a.snapshot['deposits']['total']), (PoolAudit.Status.SIGNED, 'boss', '10.00'))
        self.deposit('BB-LATE', '99')                           # a later change can't move a signed week
        self.assertEqual(audit.audit_row(PoolAudit.objects.get(week_start=WEEK))['system']['deposits']['total'], '10.00')
        with self.assertRaisesMessage(services.RevenueError, 'locked'):
            services.record_expense(day=WEEK, category='ai', amount='1', by='boss')
        with self.assertRaisesMessage(services.RevenueError, 'locked'):
            services.delete_expense(expense.id, by='boss')
        with self.assertRaisesMessage(audit.AuditError, 'signed off'):
            audit.upload(WEEK, 'paynow', user=self.boss, total='1')

    def test_unbalanced_weeks_need_an_explanation(self):
        with self.assertRaisesMessage(audit.AuditError, 'both reports'):
            audit.sign_off(WEEK, user=self.boss)
        self.deposit('BB-1', '10')
        audit.upload(WEEK, 'paynow', user=self.boss, total='9')
        audit.upload(WEEK, 'payouts', user=self.boss, total='0')
        with self.assertRaisesMessage(audit.AuditError, 'explain'):
            audit.sign_off(WEEK, user=self.boss, note='ok')
        a = audit.sign_off(WEEK, user=self.boss, note='Paynow fee of $1 taken at source.')
        self.assertEqual(a.status, PoolAudit.Status.SIGNED)

    def test_api_flow_and_private_file_download(self):
        self.deposit('BB-1', '10')
        boss = self.api(self.boss)
        weeks = boss.get('/api/admin/revenue-share/audits/').json()
        self.assertTrue(weeks['is_founder'])
        self.assertEqual({a['week_start'] for a in weeks['audits']}, {str(WEEK - timedelta(days=7)), str(WEEK), str(WEEK + timedelta(days=7))})
        res = boss.post(f'/api/admin/revenue-share/audits/{WEEK}/upload/',
                        {'kind': 'paynow', 'file': csv_file('Reference,Amount\nBB-1,10\n')}, format='multipart')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['paynow']['balanced'])
        url = f'/api/admin/revenue-share/audits/{WEEK}/file/paynow/'
        self.assertEqual(self.api(self.partner).get(url).status_code, 200)
        self.assertEqual(self.api(self.clerk).get(url).status_code, 403)
        self.assertEqual(APIClient().get(url).status_code, 401)
