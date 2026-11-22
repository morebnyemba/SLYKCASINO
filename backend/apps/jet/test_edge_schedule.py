"""Aviator house edge schedule: the clock decides the edge, fixed on each round
when it opens and published with it; nothing else changes it."""
from __future__ import annotations

from datetime import datetime, time, timedelta
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


class RotationTests(TestCase):
    """The edge steps through a list every N minutes, round the clock."""

    def setUp(self):
        cfg = JetSettings.load()
        cfg.house_edge_percent, cfg.edge_rotation_enabled = D('3.00'), True
        cfg.edge_rotation_minutes = 5
        cfg.edge_rotation_steps = [{'edge': str(v), 'on': True} for v in (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)]
        cfg.save()

    def test_steps_every_five_minutes_through_the_list_and_wraps(self):
        from datetime import timezone as dt_tz
        start = datetime(2026, 11, 23, 0, 0, tzinfo=dt_tz.utc)        # a 50-minute boundary from the epoch
        seen = [edge_schedule.current(start + timedelta(minutes=5 * i, seconds=30))[0] for i in range(12)]
        first = seen[0]
        values = [D(v) for v in (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)]
        k = values.index(first)
        self.assertEqual(seen, [values[(k + i) % 10] for i in range(12)])   # in order, then round again
        self.assertEqual(edge_schedule.current(start + timedelta(seconds=10))[0],
                         edge_schedule.current(start + timedelta(minutes=4, seconds=59))[0])   # same 5-minute slot

    def test_rounds_use_the_slot_they_open_in_and_publish_it(self):
        when = datetime(2026, 11, 23, 12, 2, tzinfo=HARARE)
        edge, label = edge_schedule.current(when)
        rnd = services.open_round(now=when)
        self.assertEqual((rnd.house_edge_percent, rnd.edge_rule), (edge, label))
        self.assertTrue(label.startswith('Rotation '))
        self.assertEqual(services.round_payload(rnd)['house_edge_percent'], str(edge))
        self.assertEqual(rnd.crash_point, engine.crash_point(rnd.server_seed, rnd.id, edge, JetSettings.load().max_multiplier))

    def test_rotation_beats_windows_and_off_falls_back(self):
        JetSettings.objects.filter(pk=1).update(edge_schedule_enabled=True)
        JetEdgeRule.objects.create(days='0123456', starts=time(0), ends=time(0), house_edge_percent=D('2.00'))
        self.assertNotEqual(edge_schedule.current()[0], D('2.00'))
        JetSettings.objects.filter(pk=1).update(edge_rotation_enabled=False)
        self.assertEqual(edge_schedule.current()[0], D('2.00'))

    def test_each_edge_can_be_switched_off_and_is_then_skipped(self):
        from datetime import timezone as dt_tz
        steps = [{'edge': str(v), 'on': v in (5, 15, 25)} for v in (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)]
        JetSettings.objects.filter(pk=1).update(edge_rotation_steps=steps)
        start = datetime(2026, 11, 23, 0, 0, tzinfo=dt_tz.utc)
        seen = {edge_schedule.current(start + timedelta(minutes=5 * i, seconds=30))[0] for i in range(9)}
        self.assertEqual(seen, {D('5'), D('15'), D('25')})                 # only the edges switched on
        self.assertIn('(1/3)', edge_schedule.current(start)[1] + edge_schedule.current(start + timedelta(minutes=5))[1]
                      + edge_schedule.current(start + timedelta(minutes=10))[1])

    def test_all_edges_off_falls_back_to_the_standard_edge(self):
        steps = [{'edge': '5', 'on': False}, {'edge': '10', 'on': False}]
        JetSettings.objects.filter(pk=1).update(edge_rotation_steps=steps)
        self.assertEqual(edge_schedule.current(), (D('3.00'), ''))
        rnd = services.open_round(now=datetime(2026, 11, 23, 12, 2, tzinfo=HARARE))
        self.assertEqual(rnd.house_edge_percent, D('3.00'))

    def test_next_change_is_the_next_slot(self):
        from datetime import timezone as dt_tz
        now = datetime(2026, 11, 23, 10, 2, 10, tzinfo=dt_tz.utc)
        change = edge_schedule.upcoming(now)
        self.assertEqual(datetime.fromisoformat(change['at']).astimezone(dt_tz.utc), datetime(2026, 11, 23, 10, 5, tzinfo=dt_tz.utc))
        self.assertEqual(D(change['house_edge_percent']), edge_schedule.current(now + timedelta(minutes=3))[0])

    def test_admin_sets_the_rotation(self):
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        url = '/api/admin/jet/edge-schedule/'
        body = staff.put(url, {'rotation': {'enabled': True, 'minutes': 10, 'values': '2, 3, 4%'}}, format='json').json()
        self.assertEqual(body['rotation']['minutes'], 10)
        self.assertEqual(body['rotation']['steps'], [{'edge': '2.00', 'on': True}, {'edge': '3.00', 'on': True},
                                                     {'edge': '4.00', 'on': True}])
        self.assertEqual((body['rotation']['average_edge_percent'], body['rotation']['average_rtp_percent']), ('3.00', '97.00'))
        self.assertIn(body['now']['house_edge_percent'], ('2.00', '3.00', '4.00'))
        # Switch one edge off: it leaves the rotation and the average.
        steps = [{'edge': '2', 'on': True}, {'edge': '3', 'on': False}, {'edge': '4', 'on': True}]
        body = staff.put(url, {'rotation': {'steps': steps}}, format='json').json()
        self.assertEqual((body['rotation']['active'], body['rotation']['average_edge_percent']), (2, '3.00'))
        self.assertFalse(body['rotation']['steps'][1]['on'])
        self.assertIn(body['now']['house_edge_percent'], ('2.00', '4.00'))
        for rot, word in (({'values': '5, 60'}, '0% and 50%'), ({'values': ''}, 'at least one'),
                          ({'values': 'x'}, 'not a percentage'), ({'minutes': 0}, '1 to 1440'),
                          ({'steps': [{'edge': '70', 'on': True}]}, '0% and 50%'), ({'steps': []}, 'at least one')):
            res = staff.put(url, {'rotation': rot}, format='json')
            self.assertEqual(res.status_code, 400, rot)
            self.assertIn(word, res.json()['detail'])
        from apps.accounts.models import AuditLog
        self.assertTrue(AuditLog.objects.filter(event_type='jet_edge_schedule').exists())
