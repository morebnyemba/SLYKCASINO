"""WhatsApp betting: the signed webhook, linking, browsing, the slip, betting
behind YES (caps, PIN, price changes), balance, tickets and deposits."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.accounts.models import Player
from apps.chatbot import engine, services
from apps.chatbot.models import ChatbotSettings, ChatLink, ChatTicket, InboundMessage
from apps.sportsbook.models import Bet, BetSlip, Event, Market, MarketOutcome
from apps.wallet import services as wallet

D = Decimal
NUMBER = '263771234567'
SECRET = 'app-secret'


def text(replies) -> str:
    return '\n'.join(r['text'] for r in replies)


class _Base(TestCase):
    def setUp(self):
        self.player = accounts.register_player(username='rudo', email='rudo@example.com', password='Pass-word-123')
        wallet.credit(player_id=self.player.id, amount=D('100'), kind='deposit', idempotency_key='chat:dep')
        soon = timezone.now() + timedelta(hours=3)
        self.e1 = Event.objects.create(name='Dynamos vs Highlanders', starts_at=soon, status='NS',
                                       odds=D('2.00'), odds_draw=D('3.20'), odds_away=D('3.80'))
        self.e2 = Event.objects.create(name='CAPS United vs FC Platinum', starts_at=soon + timedelta(hours=1), status='NS',
                                       odds=D('1.70'), odds_draw=D('3.40'), odds_away=D('4.50'))
        btts = Market.objects.create(event=self.e2, key='btts:ft', name='Both teams to score', kind='btts')
        MarketOutcome.objects.create(market=btts, key='yes', label='Yes', odds=D('1.80'))
        MarketOutcome.objects.create(market=btts, key='no', label='No', odds=D('1.95'))
        ou = Market.objects.create(event=self.e1, key='over_under:ft:2.5', name='Over/Under 2.5', kind='over_under',
                                   line=D('2.5'))
        MarketOutcome.objects.create(market=ou, key='over', label='Over 2.5', odds=D('2.10'))
        MarketOutcome.objects.create(market=ou, key='under', label='Under 2.5', odds=D('1.70'))

    def say(self, msg, number=NUMBER):
        return engine.handle(number, msg)

    def linked(self):
        code = services.new_link_code(self.player.id)
        self.say(f'LINK {code.code}')
        return ChatLink.objects.get(player_id=self.player.id)

    def deposit_balance(self):
        return wallet.get_balances(self.player.id)['deposit']


class BrowsingAndSlipTests(_Base):
    def test_menu_and_games_with_ids_need_no_account(self):
        self.assertIn('LINK 123456', text(self.say('hi')))
        out = text(self.say('GAMES'))
        self.assertIn(f'#{self.e1.id} Dynamos vs Highlanders', out)
        self.assertIn('1 2.00 X 3.20 2 3.80', out)
        self.assertIn(f'#{self.e2.id}', text(self.say('games caps')))
        self.assertNotIn(f'#{self.e1.id}', text(self.say('games caps')))

    def test_a_match_offers_its_picks_to_tap(self):
        [reply] = self.say(str(self.e1.id))
        for line in ('1 · Match result: Dynamos @ 2.00', 'X · Match result: Draw @ 3.20',
                     '2 · Match result: Highlanders @ 3.80', 'O2.5 · Total goals: Over 2.5 @ 2.10'):
            self.assertIn(line, reply['text'])
        rows = reply['list']['rows']
        self.assertEqual(rows[0], [f'{self.e1.id} 1', '1 @ 2.00', 'Match result: Dynamos'])
        self.assertEqual([r[0] for r in rows], [f'{self.e1.id} {c}' for c in ('1', 'X', '2', 'O2.5', 'U2.5')])
        from apps.chatbot import whatsapp
        body = whatsapp.payload_for(NUMBER, reply)
        self.assertEqual(body['interactive']['type'], 'list')
        self.assertEqual(body['interactive']['action']['sections'][0]['rows'][0]['id'], f'{self.e1.id} 1')
        self.assertIn('no match', text(self.say('999999')).lower().replace('there is no match', 'no match'))

    def test_building_a_slip(self):
        [reply] = self.say(f'{self.e1.id} 1, {self.e2.id} GG')
        out = reply['text']
        self.assertEqual(out.count('✅ Selection confirmed'), 2)    # every selection is confirmed back
        self.assertIn(f'#{self.e1.id} Dynamos vs Highlanders', out)
        self.assertIn('Match result: Dynamos (1)\nOdds 2.00', out)
        self.assertIn('Both teams to score: Yes (GG)\nOdds 1.80', out)
        self.assertIn('2 selections · total odds 3.60', out)       # 2.00 × 1.80
        self.assertEqual([b[1] for b in reply['buttons']], ['➕ Add more', '🧾 View slip', '✅ Place bet'])
        self.assertIn('not a pick', text(self.say(f'{self.e1.id} ZZ')))
        self.assertIn('not available', text(self.say(f'{self.e2.id} O2.5')))
        self.assertIn('Total odds 2.00', text(self.say(f'REMOVE {self.e2.id}')))
        self.assertIn('empty', text(self.say('CLEAR')))

    def test_money_commands_need_a_linked_account(self):
        self.say(f'{self.e1.id} 1')
        for cmd in ('BET 5', 'BALANCE', 'TICKETS', 'DEPOSIT 10'):
            self.assertIn('Link your account first', text(self.say(cmd)), cmd)

    def test_blocked_countries_are_refused(self):
        self.assertIn('not available in your country', text(self.say('GAMES', number='14155550100')))


class LinkingTests(_Base):
    def test_link_with_a_one_time_code(self):
        code = services.new_link_code(self.player.id)
        self.assertIn('Linked to rudo', text(self.say(f'LINK {code.code}')))
        self.assertTrue(ChatLink.objects.filter(address=NUMBER, player_id=self.player.id).exists())
        self.assertIn('wrong or has expired', text(self.say(f'LINK {code.code}', number='263779999999')))   # used

    def test_expired_and_guessed_codes_fail_and_guessing_is_capped(self):
        code = services.new_link_code(self.player.id)
        type(code).objects.filter(pk=code.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIn('expired', text(self.say(f'LINK {code.code}')))
        for _ in range(4):
            self.say('LINK 000001')
        fresh = services.new_link_code(self.player.id)
        self.assertIn('Too many wrong codes', text(self.say(f'LINK {fresh.code}')))

    def test_relinking_moves_the_number_and_stop_unlinks(self):
        self.linked()
        code = services.new_link_code(self.player.id)
        self.say(f'LINK {code.code}', number='263770000000')
        self.assertEqual(list(ChatLink.objects.values_list('address', flat=True)), ['263770000000'])
        self.assertIn('unlinked', text(self.say('STOP', number='263770000000')))
        self.assertFalse(ChatLink.objects.exists())


class BettingTests(_Base):
    def setUp(self):
        super().setUp()
        self.link = self.linked()

    def test_single_bet_needs_yes_then_places_through_the_sportsbook(self):
        self.say(f'{self.e1.id} 1')
        [prompt] = self.say('STAKE')                               # the Place bet button
        self.assertEqual([b[0] for b in prompt['buttons']], ['BET 1', 'BET 2', 'BET 5'])
        [ticket] = self.say('BET 5')
        self.assertIn('Confirm your ticket (Single)', ticket['text'])
        self.assertIn('Match result: Dynamos @ 2.00', ticket['text'])
        self.assertIn('Stake $5.00 from your deposit wallet', ticket['text'])
        self.assertIn('possible win $10.00', ticket['text'])
        self.assertEqual(ticket['buttons'], [['CONFIRM', '✅ Confirm'], ['NO', '✖ Cancel']])
        self.assertFalse(Bet.objects.exists())
        out = text(self.say('CONFIRM'))                            # pressing Confirm
        bet = Bet.objects.get()
        self.assertIn(f'Ticket {bet.code}', out)
        self.assertEqual((bet.stake, bet.odds, bet.event_ref_id, bet.selection), (D('5.00'), D('2.00'), self.e1.id, 'home'))
        self.assertEqual(self.deposit_balance(), D('95.00'))
        self.assertEqual(ChatTicket.objects.get().object_id, bet.id)
        self.assertIn('empty', text(self.say('SLIP')))
        self.assertIn(bet.code, text(self.say('TICKETS')))

    def test_every_match_on_the_ticket_shows_its_kick_off(self):
        tz = services.local_tz()                                         # players' time (Harare), not the server's UTC
        k1 = timezone.localtime(self.e1.starts_at, tz).strftime('%a %d %b %Y, %H:%M')
        k2 = timezone.localtime(self.e2.starts_at, tz).strftime('%a %d %b %Y, %H:%M')

        def both(out):
            self.assertIn(f'#{self.e1.id} Dynamos vs Highlanders\n    🕒 {k1}', out)
            self.assertIn(f'#{self.e2.id} CAPS United vs FC Platinum\n    🕒 {k2}', out)

        added = text(self.say(f'{self.e1.id} 1, {self.e2.id} GG'))       # each selection confirmed
        self.assertIn(f'🕒 {k1}', added)
        self.assertIn(f'🕒 {k2}', added)
        both(text(self.say('SLIP')))                                     # the slip
        both(text(self.say('BET 4')))                                    # the ticket to confirm
        # A rescheduled match shows its new kick-off on the ticket.
        Event.objects.filter(pk=self.e2.pk).update(starts_at=self.e2.starts_at + timedelta(days=1))
        k2 = timezone.localtime(self.e2.starts_at + timedelta(days=1), tz).strftime('%a %d %b %Y, %H:%M')
        placed = text(self.say('CONFIRM'))                               # the placed ticket
        both(placed)
        out = text(self.say('TICKETS'))                                  # the ticket list
        self.assertIn(f'#{self.e1.id} Dynamos vs Highlanders\n     🕒 {k1}', out)
        self.assertIn(f'#{self.e2.id} CAPS United vs FC Platinum\n     🕒 {k2}', out)
        self.assertIn(f'🕒 {k1}', text(self.say('GAMES')))                 # and the match list

    def test_kick_off_is_in_harare_time_not_server_utc(self):
        from apps.chatbot.engine import kickoff
        e = Event(name='A vs B', starts_at=datetime(2026, 11, 28, 16, 0, tzinfo=dt_timezone.utc), status='NS')
        self.assertEqual(kickoff(e), '🕒 Sat 28 Nov 2026, 18:00')        # 16:00 UTC = 18:00 CAT

    def test_multiple_bet(self):
        self.say(f'{self.e1.id} U2.5, {self.e2.id} GG')
        self.say('BET 4')
        self.say('YES')
        slip = BetSlip.objects.get()
        self.assertEqual((slip.stake, slip.combined_odds, slip.legs.count()), (D('4.00'), D('3.06'), 2))

    def test_a_price_change_places_nothing_and_updates_the_slip(self):
        self.say(f'{self.e1.id} 1')
        self.say('BET 5')
        Event.objects.filter(pk=self.e1.pk).update(odds=D('1.90'))
        out = text(self.say('YES'))
        self.assertIn('changed', out)
        self.assertIn('@ 1.90', out)
        self.assertFalse(Bet.objects.exists())
        self.say('BET 5')
        self.say('YES')
        self.assertEqual(Bet.objects.get().odds, D('1.90'))

    def test_no_confirmation_no_bet_and_it_expires(self):
        self.say(f'{self.e1.id} 1')
        self.assertIn('no ticket waiting', text(self.say('YES')))
        self.say('BET 5')
        later = timezone.now() + timedelta(minutes=3)
        self.assertIn('expired', text(engine.handle(NUMBER, 'YES', now=later)))
        self.say('BET 5')
        self.assertIn('Cancelled', text(self.say('NO')))
        self.assertFalse(Bet.objects.exists())

    def test_chat_limits(self):
        ChatbotSettings.objects.filter(pk=1).update(max_stake=D('10'), daily_cap=D('15'), pin_above=D('50'))
        self.say(f'{self.e1.id} 1')
        self.assertIn('most you can stake', text(self.say('BET 11')))
        self.say('BET 10')
        self.say('YES')
        self.say(f'{self.e1.id} 1')
        self.assertIn('You can still stake $5.00 today', text(self.say('BET 6')))
        ChatLink.objects.filter(pk=self.link.pk).update(daily_cap=D('8'))
        self.assertIn('daily chat limit ($8.00)', text(self.say('BET 1')))

    def test_pin_above_the_threshold_and_always_once_set(self):
        ChatbotSettings.objects.filter(pk=1).update(pin_above=D('20'))
        self.say(f'{self.e1.id} 1')
        self.assertIn('need a chat PIN', text(self.say('BET 25')))
        self.assertIn('Press Confirm within', text(self.say('BET 5')))   # small stake, no PIN set
        self.say('NO')
        services.set_pin(ChatLink.objects.get(pk=self.link.pk), '4321')
        [reply] = self.say('BET 5')
        self.assertIn('CONFIRM and your PIN', reply['text'])
        self.assertNotIn(['CONFIRM', '✅ Confirm'], reply['buttons'])     # a PIN can't ride on a button
        self.assertIn('Wrong or missing PIN', text(self.say('YES')))
        self.assertIn('Wrong or missing PIN', text(self.say('YES 1111')))
        self.assertIn('too many times', text(self.say('YES 2222')))
        self.say('BET 5')
        self.say('CONFIRM 4321')
        self.assertTrue(Bet.objects.exists())

    def test_wallet_choice_and_not_enough_money(self):
        self.say(f'{self.e1.id} 1')
        self.say('BET 5 WIN')
        self.assertIn('Not enough money in your winnings wallet', text(self.say('YES')))
        self.assertIn('DEP (deposit)', text(self.say('BET 5 CARD')))

    def test_self_excluded_players_cannot_bet_or_deposit(self):
        Player.objects.filter(pk=self.player.pk).update(self_excluded=True)
        self.say(f'{self.e1.id} 1')
        self.assertIn('self-excluded', text(self.say('BET 5')))
        self.assertIn('self-excluded', text(self.say('DEPOSIT 10')))

    def test_balance_book_and_load_a_code(self):
        self.assertIn('Deposit $100.00', text(self.say('BALANCE')))
        self.say(f'{self.e1.id} 1, {self.e2.id} NG')
        out = text(self.say('BOOK'))
        code = out.split('Booking code ')[1].split('.')[0]
        self.say('CLEAR')
        self.assertIn('Total odds 3.90', text(self.say(f'CODE {code}')))     # 2.00 × 1.95

    def test_deposit(self):
        self.assertIn('website', text(self.say('DEPOSIT 10')))            # no gateway in tests
        from apps.wallet.models import PaymentTransaction
        txn = PaymentTransaction(reference='DEPCHAT1', amount=D('10'), instructions='')
        with patch('apps.wallet.payments.gateway_enabled', return_value=True), \
                patch('apps.wallet.payments.check_deposit'), \
                patch('apps.wallet.payments.start_deposit', return_value=txn) as start:
            out = text(self.say('DEPOSIT 10'))
        self.assertIn('ref DEPCHAT1', out)
        self.assertEqual((start.call_args.kwargs['method'], start.call_args.kwargs['phone']), ('ecocash', NUMBER))


@override_settings(WHATSAPP_APP_SECRET=SECRET, WHATSAPP_VERIFY_TOKEN='verify-me')
class WebhookTests(_Base):
    def delivery(self, body_text='GAMES', msg_id='wamid.1', sender=NUMBER):
        return {'object': 'whatsapp_business_account', 'entry': [{'changes': [{'value': {
            'messages': [{'from': sender, 'id': msg_id, 'type': 'text', 'text': {'body': body_text}}]}}]}]}

    def post(self, payload, *, secret=SECRET, **headers):
        raw = json.dumps(payload).encode()
        sig = 'sha256=' + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return APIClient().generic('POST', '/api/chatbot/whatsapp/webhook/', raw, content_type='application/json',
                                   HTTP_X_HUB_SIGNATURE_256=sig, **headers)

    def test_meta_verification(self):
        url = '/api/chatbot/whatsapp/webhook/?hub.mode=subscribe&hub.challenge=42&hub.verify_token='
        self.assertEqual(APIClient().get(url + 'verify-me').content, b'42')
        self.assertEqual(APIClient().get(url + 'wrong').status_code, 403)

    def test_unsigned_or_forged_deliveries_are_refused(self):
        self.assertEqual(self.post(self.delivery(), secret='forged').status_code, 403)
        self.assertFalse(InboundMessage.objects.exists())

    def test_a_delivery_is_answered_once_even_if_redelivered(self):
        with patch.object(services, 'deliver') as deliver:
            self.assertEqual(self.post(self.delivery()).status_code, 200)
            self.assertEqual(self.post(self.delivery()).status_code, 200)
        self.assertEqual(InboundMessage.objects.count(), 1)
        deliver.assert_called_once()
        self.assertIn('Upcoming', deliver.call_args.args[1][0]['text'])

    def test_meta_calling_from_a_blocked_country_still_gets_through(self):
        with patch.object(services, 'deliver') as deliver:
            self.assertEqual(self.post(self.delivery(), HTTP_CF_IPCOUNTRY='US').status_code, 200)
        deliver.assert_called_once()

    def test_button_taps_read_like_typing(self):
        from apps.chatbot import whatsapp
        payload = {'entry': [{'changes': [{'value': {'messages': [{'from': NUMBER, 'id': 'wamid.b', 'type': 'interactive',
                   'interactive': {'type': 'button_reply', 'button_reply': {'id': 'SLIP', 'title': 'SLIP'}}}]}}]}]}
        self.assertEqual(whatsapp.parse(payload)[0].text, 'SLIP')
        body = whatsapp.payload_for(NUMBER, {'text': 'hi', 'buttons': ['YES', 'NO']})
        self.assertEqual([b['reply']['id'] for b in body['interactive']['action']['buttons']], ['YES', 'NO'])

    def test_flooding_is_ignored(self):
        with patch.object(services, 'deliver') as deliver:
            for i in range(services.MESSAGES_PER_MINUTE + 3):
                self.post(self.delivery(msg_id=f'wamid.f{i}'))
        self.assertEqual(deliver.call_count, services.MESSAGES_PER_MINUTE)


class AccountApiTests(_Base):
    def api(self):
        c = APIClient()
        c.force_authenticate(self.player.user)
        return c

    def test_link_code_status_pin_limit_unlink(self):
        c = self.api()
        self.assertFalse(c.get('/api/chatbot/me/').json()['linked'])
        code = c.post('/api/chatbot/me/link-code/').json()['code']
        self.say(f'LINK {code}')
        body = c.get('/api/chatbot/me/').json()
        self.assertEqual((body['linked'], body['number']), (True, '+263 ••• 4567'))
        self.assertEqual(c.post('/api/chatbot/me/pin/', {'pin': '12'}, format='json').status_code, 400)
        self.assertTrue(c.post('/api/chatbot/me/pin/', {'pin': '2468'}, format='json').json()['has_pin'])
        self.assertEqual(c.post('/api/chatbot/me/limit/', {'daily_limit': '30'}, format='json').json()['daily_limit'], '30.00')
        self.assertFalse(c.delete('/api/chatbot/me/').json()['linked'])

    def test_admin_settings(self):
        from django.contrib.auth.models import User
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        body = staff.get('/api/admin/chatbot/').json()
        self.assertEqual((body['enabled'], body['max_stake'], body['configured']), (True, '50.00', False))
        body = staff.put('/api/admin/chatbot/', {'enabled': False, 'daily_cap': '75'}, format='json').json()
        self.assertEqual((body['enabled'], body['daily_cap']), (False, '75.00'))
        self.assertIn('paused', text(self.say('GAMES')))
        self.assertEqual(APIClient().get('/api/admin/chatbot/').status_code, 401)
