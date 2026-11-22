"""Aviator house edge schedule: the clock decides the edge, fixed on each round
when it opens and published with it; nothing else changes it."""
from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from . import edge_schedule, engine, services
from .models import JetEdgeRule, JetSettings

D = Decimal
HARARE = ZoneInfo('Africa/Harare')


def at(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=HARARE)


# 2026-11-23 is a Monday.
MON_20H, MON_10H, SAT_01H, SUN_01H = at(2026, 11, 23, 20), at(2026, 11, 23, 10), at(2026, 11, 28, 1), at(2026, 11, 29, 1)


@override_settings(PLAYER_TIME_ZONE='Africa/Harare')
class ScheduleTests(TestCase):
    def setUp(self):
        cfg = JetSettings.load()
        cfg.house_edge_percent, cfg.edge_schedule_enabled = D('3.00'), True
        cfg.save()

    def rule(self, **kw):
        values = {'name': 'Evenings', 'days': '01234', 'starts': time(18), 'ends': time(23), 'house_edge_percent': D('4.00')}
        values.update(kw)
        return JetEdgeRule.objects.create(**values)

    def test_the_window_sets_the_edge_and_outside_it_the_standard_applies(self):
        self.rule()
        self.assertEqual(edge_schedule.edge_at(MON_20H)[0], D('4.00'))
        self.assertEqual(edge_schedule.edge_at(MON_10H), (D('3.00'), None))
        self.assertEqual(edge_schedule.edge_at(at(2026, 11, 28, 20))[0], D('3.00'))     # Saturday: not a weekday

    def test_a_window_past_midnight_belongs_to_the_day_it_starts(self):
        self.rule(name='Late', days='4', starts=time(22), ends=time(2), house_edge_percent=D('2.50'))   # Friday night
        self.assertEqual(edge_schedule.edge_at(SAT_01H)[0], D('2.50'))            # Saturday 01:00 is Friday's window
        self.assertEqual(edge_schedule.edge_at(SUN_01H)[0], D('3.00'))            # Sunday 01:00 is not

    def test_first_rule_by_order_wins_and_disabled_rules_or_schedule_do_nothing(self):
        self.rule(sort_order=2, house_edge_percent=D('5.00'))
        first = self.rule(sort_order=1, house_edge_percent=D('4.50'))
        self.assertEqual(edge_schedule.edge_at(MON_20H)[0], D('4.50'))
        JetEdgeRule.objects.filter(pk=first.pk).update(enabled=False)
        self.assertEqual(edge_schedule.edge_at(MON_20H)[0], D('5.00'))
        JetSettings.objects.filter(pk=1).update(edge_schedule_enabled=False)
        self.assertEqual(edge_schedule.edge_at(MON_20H), (D('3.00'), None))

    def test_a_round_is_drawn_and_published_with_the_edge_in_force_when_it_opens(self):
        self.rule()
        rnd = services.open_round(now=MON_20H)
        self.assertEqual((rnd.house_edge_percent, rnd.edge_rule), (D('4.00'), 'Evenings'))
        self.assertEqual(rnd.crash_point, engine.crash_point(rnd.server_seed, rnd.id, D('4.00'), JetSettings.load().max_multiplier))
        payload = services.round_payload(rnd)
        self.assertEqual((payload['house_edge_percent'], payload['rtp_percent']), ('4.00', '96.00'))
        later = services.open_round(now=MON_10H)
        self.assertEqual((later.house_edge_percent, later.edge_rule), (D('3.00'), ''))

    def test_next_change(self):
        self.rule()
        change = edge_schedule.next_change(MON_10H)
        self.assertEqual((change['at'][:16], change['house_edge_percent'], change['rule']), ('2026-11-23T18:00', '4.00', 'Evenings'))
        change = edge_schedule.next_change(MON_20H)
        self.assertEqual((change['at'][:16], change['house_edge_percent']), ('2026-11-23T23:00', '3.00'))


class ScheduleApiTests(TestCase):
    def setUp(self):
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.url = '/api/admin/jet/edge-schedule/'

    def test_add_edit_delete_rules_and_switch_on(self):
        body = self.staff.post(self.url + 'rules/', {'name': 'Weekend', 'days': '56', 'starts': '00:00', 'ends': '00:00',
                                                     'house_edge_percent': '2.5'}, format='json').json()
        [rule] = body['rules']
        self.assertEqual((rule['days_label'], rule['house_edge_percent'], rule['rtp_percent']), ('Weekends', '2.50', '97.50'))
        self.assertFalse(body['enabled'])
        body = self.staff.put(self.url, {'enabled': True}, format='json').json()
        self.assertTrue(body['enabled'])
        body = self.staff.patch(f'{self.url}rules/{rule["id"]}/', {'house_edge_percent': '3.5', 'days': '0123456'}, format='json').json()
        self.assertEqual((body['rules'][0]['house_edge_percent'], body['rules'][0]['days_label']), ('3.50', 'Every day'))
        self.assertEqual(body['now']['house_edge_percent'], '3.50')           # all day, every day: in force now
        self.assertEqual(self.staff.get('/api/jet/state/').json()['settings']['rtp_percent'], '96.50')
        self.assertEqual(self.staff.delete(f'{self.url}rules/{rule["id"]}/').json()['rules'], [])
        from apps.accounts.models import AuditLog
        self.assertEqual(AuditLog.objects.filter(event_type='jet_edge_rule').count(), 3)

    def test_bad_rules_are_refused(self):
        for body, word in (({'days': '', 'starts': '10:00', 'ends': '11:00', 'house_edge_percent': '3'}, 'day'),
                           ({'days': '0', 'starts': '25:00', 'ends': '11:00', 'house_edge_percent': '3'}, 'HH:MM'),
                           ({'days': '0', 'starts': '10:00', 'ends': '11:00', 'house_edge_percent': '60'}, '0% and 50%')):
            res = self.staff.post(self.url + 'rules/', body, format='json')
            self.assertEqual(res.status_code, 400)
            self.assertIn(word, res.json()['detail'])
        self.assertEqual(APIClient().get(self.url).status_code, 401)
