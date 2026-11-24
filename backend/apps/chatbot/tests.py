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

import pytest

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.accounts.models import Player
from apps.chatbot import engine, services, whatsapp
from apps.chatbot.models import ChatbotSettings, ChatLink, ChatSession, ChatTicket, InboundMessage
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
        self.assertIn('send *LOGIN*', text(self.say('hi')))
        out = text(self.say('GAMES'))
        self.assertIn(f'*{self.e1.id}* · ', out)
        self.assertIn('Dynamos v Highlanders', out)
        self.assertIn('`1 2.00 · X 3.20 · 2 3.80`', out)
        self.assertIn('CAPS United v FC Platinum', text(self.say('games caps')))
        self.assertNotIn('Dynamos', text(self.say('games caps')))

    def test_a_match_offers_its_picks_to_tap(self):
        [reply] = self.say(str(self.e1.id))
        for line in ('1 · Dynamos — *2.00*', 'X · Draw — *3.20*', '2 · Highlanders — *3.80*', 'O2.5 *2.10* · U2.5 *1.70*'):
            self.assertIn(line, reply['text'])
        result, markets = reply['list']['sections']
        self.assertEqual(result['rows'][0], [f'{self.e1.id} 1', '1 · 2.00', 'Match result: Dynamos'])
        self.assertEqual([r[0] for r in result['rows']], [f'{self.e1.id} {c}' for c in ('1', 'X', '2')])
        self.assertEqual(markets['rows'], [[f'{self.e1.id} G main', 'Main', '1 market'], ['BACK', '⬅️ Back', 'Up one level']])
        from apps.chatbot import whatsapp
        body = whatsapp.payload_for(NUMBER, reply)
        self.assertEqual(body['interactive']['type'], 'list')
        self.assertEqual(body['interactive']['action']['sections'][0]['rows'][0]['id'], f'{self.e1.id} 1')
        self.assertIn('no match', text(self.say('999999')).lower().replace('there is no match', 'no match'))

    def test_building_a_slip(self):
        [reply] = self.say(f'{self.e1.id} 1, {self.e2.id} GG')
        out = reply['text']
        self.assertEqual(out.count('✅ *Selection added*'), 2)      # every selection is confirmed back
        self.assertIn(f'#{self.e1.id} Dynamos vs Highlanders', out)
        self.assertIn('Match result: *Dynamos* (1)\nOdds *2.00*', out)
        self.assertIn('Both teams to score: *Yes* (GG)\nOdds *1.80*', out)
        self.assertIn('2 matches · total odds *3.60*', out)     # 2.00 × 1.80
        self.assertEqual([b[1] for b in reply['buttons']], ['➕ Add more', '🧾 View slip', '✅ Place bet'])
        self.assertIn('not a pick', text(self.say(f'{self.e1.id} ZZ')))
        self.assertIn('not available', text(self.say(f'{self.e2.id} O2.5')))
        self.assertIn('Total odds 2.00', text(self.say(f'REMOVE {self.e2.id}')))
        self.assertIn('empty', text(self.say('CLEAR')))

    def test_money_commands_need_a_linked_account(self):
        self.say(f'{self.e1.id} 1')
        for cmd in ('BET 5', 'BALANCE', 'TICKETS', 'DEPOSIT 10'):
            self.assertIn('send *LOGIN*', text(self.say(cmd)), cmd)

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
        games = text(self.say('GAMES'))                                  # and the match list: day, then time
        self.assertIn(f'📅 *{timezone.localtime(self.e1.starts_at, tz).strftime("%a %d %b")}*', games)
        self.assertIn(f'*{self.e1.id}* · {timezone.localtime(self.e1.starts_at, tz).strftime("%H:%M")} · ', games)

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
        self.assertEqual(body['webhook_url'], 'https://testserver/api/chatbot/whatsapp/webhook/')
        body = staff.put('/api/admin/chatbot/', {'enabled': False, 'daily_cap': '75'}, format='json').json()
        self.assertEqual((body['enabled'], body['daily_cap']), (False, '75.00'))
        self.assertIn('paused', text(self.say('GAMES')))
        self.assertEqual(APIClient().get('/api/admin/chatbot/').status_code, 401)


class ConnectionSettingsTests(_Base):
    """WhatsApp settings from the admin (secrets encrypted), .env.prod as fallback."""

    def setUp(self):
        super().setUp()
        from django.contrib.auth.models import User
        self.boss = APIClient()
        self.boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))
        self.clerk = APIClient()
        self.clerk.force_authenticate(User.objects.create_user('clerk', 'c@example.com', 'x', is_staff=True))

    def put(self, client, conn):
        return client.put('/api/admin/chatbot/', {'connection': conn}, format='json')

    @override_settings(WHATSAPP_PHONE_NUMBER_ID='111', WHATSAPP_TOKEN='env-token-123456')
    def test_admin_overrides_env_and_clearing_falls_back(self):
        from apps.chatbot import config
        conn = self.boss.get('/api/admin/chatbot/').json()['connection']
        self.assertEqual((conn['phone_number_id']['value'], conn['phone_number_id']['source']), ('111', 'env'))
        self.assertEqual((conn['graph_version']['value'], conn['graph_version']['source']), ('v21.0', 'default'))
        res = self.put(self.boss, {'phone_number_id': '222', 'token': 'admin-token-abcdef', 'time_zone': 'Africa/Lusaka'})
        self.assertEqual(res.status_code, 200, res.content)
        conn = res.json()['connection']
        self.assertEqual((conn['phone_number_id']['value'], conn['phone_number_id']['source']), ('222', 'admin'))
        self.assertEqual(config.value('token'), 'admin-token-abcdef')
        self.assertEqual(str(services.local_tz()), 'Africa/Lusaka')
        res = self.put(self.boss, {'clear': ['phone_number_id', 'token']})
        self.assertEqual(res.json()['connection']['phone_number_id']['value'], '111')
        self.assertEqual(config.value('token'), 'env-token-123456')

    def test_secrets_are_encrypted_and_never_sent_back(self):
        self.put(self.boss, {'token': 'EAAGsecret-token-9876', 'app_secret': 'shh-app-secret-1234'})
        cfg = ChatbotSettings.load()
        self.assertTrue(cfg.token_enc)
        self.assertNotIn('EAAGsecret', cfg.token_enc)                    # not stored in the clear
        raw = self.boss.get('/api/admin/chatbot/').content.decode()
        self.assertNotIn('EAAGsecret-token-9876', raw)
        self.assertNotIn('shh-app-secret', raw)
        conn = json.loads(raw)['connection']
        self.assertEqual((conn['token']['set'], conn['token']['hint'], conn['token']['source']), (True, '…9876', 'admin'))
        self.put(self.boss, {'token': ''})                               # a blank box keeps it
        from apps.chatbot import config
        self.assertEqual(config.value('token'), 'EAAGsecret-token-9876')
        from apps.accounts.models import AuditLog
        log = AuditLog.objects.filter(event_type='chatbot_connection').first()
        self.assertIn('token', str(log.metadata))
        self.assertNotIn('EAAGsecret', str(log.metadata))

    def test_only_superusers_change_the_connection(self):
        self.assertEqual(self.put(self.clerk, {'phone_number_id': '333'}).status_code, 403)
        self.assertFalse(self.clerk.get('/api/admin/chatbot/').json()['can_edit_connection'])
        self.assertEqual(self.clerk.put('/api/admin/chatbot/', {'max_stake': '20'}, format='json').status_code, 200)

    def test_bad_values_are_refused(self):
        for conn, word in (({'phone_number_id': '+263 77'}, 'digits'), ({'graph_version': '21'}, 'v21.0'),
                           ({'time_zone': 'Harare'}, 'time zone'), ({'verify_token': 'short'}, '12 characters'),
                           ({'token': 'has space'}, 'no spaces'), ({'clear': ['nope']}, 'Unknown')):
            res = self.put(self.boss, conn)
            self.assertEqual(res.status_code, 400, conn)
            self.assertIn(word, res.json()['detail'])

    def test_a_changed_key_makes_stored_secrets_unreadable_not_wrong(self):
        self.put(self.boss, {'token': 'EAAGsecret-token-9876'})
        from apps.chatbot import config
        with override_settings(CHATBOT_SECRET_KEY='a-different-key'):
            self.assertEqual(config.source('token', ChatbotSettings.load()), 'unreadable')
            self.assertEqual(config.value('token'), '')

    def test_webhook_uses_the_admin_verify_token_and_app_secret(self):
        self.put(self.boss, {'verify_token': 'admin-verify-token-1', 'app_secret': 'admin-app-secret-xyz'})
        url = '/api/chatbot/whatsapp/webhook/?hub.mode=subscribe&hub.challenge=7&hub.verify_token='
        self.assertEqual(APIClient().get(url + 'admin-verify-token-1').content, b'7')
        raw = json.dumps({'entry': [{'changes': [{'value': {'messages': [
            {'from': NUMBER, 'id': 'wamid.cfg', 'type': 'text', 'text': {'body': 'HI'}}]}}]}]}).encode()
        sig = 'sha256=' + hmac.new(b'admin-app-secret-xyz', raw, hashlib.sha256).hexdigest()
        with patch.object(services, 'deliver') as deliver:
            res = APIClient().generic('POST', '/api/chatbot/whatsapp/webhook/', raw, content_type='application/json',
                                      HTTP_X_HUB_SIGNATURE_256=sig)
        self.assertEqual(res.status_code, 200)
        deliver.assert_called_once()

    def test_check_connection_with_meta(self):
        self.assertFalse(self.boss.post('/api/admin/chatbot/test/').json()['ok'])
        self.put(self.boss, {'phone_number_id': '444', 'token': 'EAAGsecret-token-9876'})

        class Res:
            status_code = 200

            @staticmethod
            def json():
                return {'verified_name': 'BetBlits', 'display_phone_number': '+263 77 000 1111', 'quality_rating': 'GREEN'}
        with patch('requests.request', return_value=Res()) as get:
            body = self.boss.post('/api/admin/chatbot/test/').json()
        self.assertEqual((body['ok'], body['verified_name']), (True, 'BetBlits'))
        self.assertEqual(get.call_args.args[0], 'GET')
        self.assertIn('/444', get.call_args.args[1])
        self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer EAAGsecret-token-9876')


class _Res:
    """A stand-in for a requests response."""

    def __init__(self, status=200, body=None, text=''):
        self.status_code, self._body, self.text = status, body if body is not None else {}, text

    def json(self):
        return self._body


class _Inline:
    """threading.Thread that runs its target at once, so a background send can be tested."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target, self.args, self.kwargs = target, args, kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


@override_settings(WHATSAPP_APP_SECRET=SECRET, WHATSAPP_TOKEN='tok', WHATSAPP_PHONE_NUMBER_ID='555')
class DeliveryLogTests(_Base):
    """Every reply is logged, sent from the web process (no worker) and its outcome kept."""

    def post_hook(self, body_text='GAMES', msg_id='wamid.d1', statuses=None):
        value = {'messages': [{'from': NUMBER, 'id': msg_id, 'type': 'text', 'text': {'body': body_text}}]} if body_text else {}
        if statuses:
            value['statuses'] = statuses
        raw = json.dumps({'entry': [{'changes': [{'value': value}]}]}).encode()
        sig = 'sha256=' + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        return APIClient().generic('POST', '/api/chatbot/whatsapp/webhook/', raw, content_type='application/json',
                                   HTTP_X_HUB_SIGNATURE_256=sig)

    def receive(self, **kw):
        with patch.object(services.threading, 'Thread', _Inline), self.captureOnCommitCallbacks(execute=True):
            return self.post_hook(**kw)

    def test_a_reply_is_sent_directly_logged_and_marked_sent(self):
        from apps.chatbot.models import OutboundMessage
        with patch('requests.post', return_value=_Res(200, {'messages': [{'id': 'wamid.OUT1'}]})) as post:
            self.receive()
        row = OutboundMessage.objects.get()
        self.assertEqual((row.status, row.provider_id, row.source, row.address), ('sent', 'wamid.OUT1', 'bot', NUMBER))
        self.assertIn('Upcoming', row.text)
        sent = [c.kwargs['json'] for c in post.call_args_list]
        reply = next(b for b in sent if b.get('type') in ('text', 'interactive'))
        self.assertEqual((reply['to'], reply['messaging_product']), (NUMBER, 'whatsapp'))

    def test_blue_ticks_and_typing_are_requested_when_a_message_arrives(self):
        with patch('requests.post', return_value=_Res(200, {'messages': [{'id': 'x'}]})) as post:
            self.receive(msg_id='wamid.IN9')
        read = next(c.kwargs['json'] for c in post.call_args_list if c.kwargs['json'].get('status') == 'read')
        self.assertEqual((read['message_id'], read['typing_indicator']), ('wamid.IN9', {'type': 'text'}))

    def test_a_refused_send_keeps_metas_reason_in_plain_words(self):
        from apps.chatbot.models import OutboundMessage
        err = _Res(401, {'error': {'code': 190, 'message': 'Error validating access token: Session has expired'}})
        with patch('requests.post', return_value=err):
            self.receive()
        row = OutboundMessage.objects.get()
        self.assertEqual((row.status, row.error_code), ('failed', '190'))
        self.assertIn('expired', row.error)
        self.assertIn('permanent', row.error)                              # tells staff what to do about it

    @override_settings(WHATSAPP_TOKEN='', WHATSAPP_PHONE_NUMBER_ID='')
    def test_not_connected_is_recorded_not_silently_dropped(self):
        from apps.chatbot.models import OutboundMessage
        with patch('requests.post') as post:
            self.receive()
        post.assert_not_called()
        row = OutboundMessage.objects.get()
        self.assertEqual((row.status, row.error_code), ('failed', 'not_configured'))
        self.assertIn('access token and phone number ID', row.error)

    def test_delivery_reports_move_the_ticks_forward_never_back(self):
        from apps.chatbot.models import OutboundMessage
        row = OutboundMessage.objects.create(address=NUMBER, text='hi', provider_id='wamid.T1', status='sent')
        for state in ('delivered', 'read', 'delivered'):                   # the last arrives late
            self.post_hook(body_text='', statuses=[{'id': 'wamid.T1', 'status': state, 'recipient_id': NUMBER}])
        row.refresh_from_db()
        self.assertEqual(row.status, 'read')
        self.post_hook(body_text='', statuses=[{'id': 'wamid.T1', 'status': 'failed', 'errors': [
            {'code': 131047, 'title': 'Re-engagement message', 'message': 'window closed'}]}])
        row.refresh_from_db()
        self.assertEqual((row.status, row.error_code), ('failed', '131047'))

    def test_inbox_threads_staff_replies_and_the_24_hour_rule(self):
        from django.contrib.auth.models import User
        from apps.chatbot.models import OutboundMessage
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('desk', 'd@example.com', 'x', is_staff=True))
        ChatLink.objects.create(address=NUMBER, player_id=self.player.id)
        with patch('requests.post', return_value=_Res(200, {'messages': [{'id': 'wamid.O'}]})):
            self.receive(body_text='hello there')
        conv = staff.get('/api/admin/chatbot/inbox/').json()['conversations'][0]
        self.assertEqual((conv['address'], conv['player'], conv['incoming'], conv['outgoing'], conv['can_reply'], conv['unanswered']),
                         (NUMBER, 'rudo', 1, 1, True, False))
        thread = staff.get(f'/api/admin/chatbot/inbox/{NUMBER}/').json()
        self.assertEqual([m['direction'] for m in thread['messages']], ['in', 'out'])
        self.assertEqual(thread['messages'][1]['status'], 'sent')
        with patch('requests.post', return_value=_Res(200, {'messages': [{'id': 'wamid.S'}]})):
            res = staff.post(f'/api/admin/chatbot/inbox/{NUMBER}/', {'text': 'Hi, this is support'}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(OutboundMessage.objects.get(source='staff').sent_by, 'desk')
        InboundMessage.objects.all().update(received_at=timezone.now() - timedelta(hours=30))      # window closed
        res = staff.post(f'/api/admin/chatbot/inbox/{NUMBER}/', {'text': 'Too late'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('24 hours', res.json()['detail'])
        self.assertEqual(APIClient().get('/api/admin/chatbot/inbox/').status_code, 401)

    def test_health_names_the_problem(self):
        from django.contrib.auth.models import User
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('desk', 'd@example.com', 'x', is_staff=True))
        with patch('requests.post', return_value=_Res(400, {'error': {'code': 100, 'message': 'Unsupported post request'}})):
            self.receive()
        h = staff.get('/api/admin/chatbot/health/').json()
        self.assertEqual((h['incoming_24h'], h['outgoing_24h'], h['by_status']), (1, 1, {'failed': 1}))
        self.assertIn('Phone number ID', h['problem'])
        self.assertEqual(h['failures'][0]['code'], '100')

    def test_test_send_uses_text_inside_the_window_and_the_template_outside(self):
        from django.contrib.auth.models import User
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('desk', 'd@example.com', 'x', is_staff=True))
        with patch('requests.post', return_value=_Res(200, {'messages': [{'id': 'wamid.TT'}]})) as post:
            out = staff.post('/api/admin/chatbot/health/', {'to': '+263 77 123 4567'}, format='json').json()
        self.assertEqual((out['ok'], out['via']), (True, 'template'))        # nobody has written yet: template only
        self.assertEqual(post.call_args.kwargs['json']['template']['name'], 'hello_world')
        InboundMessage.objects.create(provider_id='w.t', address='263771234567', text='hi')
        with patch('requests.post', return_value=_Res(200, {'messages': [{'id': 'wamid.TU'}]})):
            out = staff.post('/api/admin/chatbot/health/', {'to': '263771234567'}, format='json').json()
        self.assertEqual((out['ok'], out['via']), (True, 'text'))
        with patch('requests.post', return_value=_Res(400, {'error': {'code': 131030, 'message': 'x'}})):
            out = staff.post('/api/admin/chatbot/health/', {'to': '263771234567'}, format='json').json()
        self.assertEqual(out['ok'], False)
        self.assertIn('allowed list', out['error'])


@override_settings(WHATSAPP_TOKEN='tok', WHATSAPP_PHONE_NUMBER_ID='555')
class ConnectionToolsTests(TestCase):
    """Find the right Phone number ID, see whether it is registered, register it."""

    def clients(self):
        from django.contrib.auth.models import User
        boss, clerk = APIClient(), APIClient()
        boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))
        clerk.force_authenticate(User.objects.create_user('clerk', 'c@example.com', 'x', is_staff=True))
        return boss, clerk

    def test_a_wrong_id_says_how_to_find_the_right_one(self):
        err = _Res(400, {'error': {'code': 100, 'message': "Unsupported post request. Object with ID '555' does not exist"}})
        with patch('requests.request', return_value=err):
            out = whatsapp.check_connection()
        self.assertEqual((out['ok'], out['code']), (False, '100'))
        self.assertIn('Find my numbers', out['error'])

    def test_an_unregistered_number_is_flagged(self):
        ok = _Res(200, {'verified_name': 'BetBlits', 'display_phone_number': '+263 77 1', 'quality_rating': 'GREEN'})
        extra = _Res(200, {'platform_type': 'NOT_APPLICABLE', 'status': 'PENDING'})
        with patch('requests.request', side_effect=[ok, extra]):
            out = whatsapp.check_connection()
        self.assertTrue(out['ok'])
        self.assertIn('Register number', out['warning'])

    def test_a_registered_number_has_no_warning_and_a_tolerated_second_failure_stays_ok(self):
        ok = _Res(200, {'verified_name': 'BetBlits', 'display_phone_number': '+263 77 1'})
        with patch('requests.request', side_effect=[ok, _Res(200, {'platform_type': 'CLOUD_API', 'status': 'CONNECTED'})]):
            self.assertNotIn('warning', whatsapp.check_connection())
        bad = _Res(400, {'error': {'code': 100, 'message': 'bad field'}})
        with patch('requests.request', side_effect=[ok, bad, bad]):       # extended fields, then the basic three
            out = whatsapp.check_connection()
        self.assertTrue(out['ok'])
        self.assertNotIn('warning', out)

    def test_numbers_are_listed_from_the_account_id(self):
        boss, _ = self.clients()
        body = {'data': [{'id': '109', 'display_phone_number': '+263 77 123', 'verified_name': 'BetBlits', 'quality_rating': 'GREEN'}]}
        with patch('requests.request', return_value=_Res(200, body)) as req:
            out = boss.post('/api/admin/chatbot/numbers/', {'waba_id': '777'}, format='json').json()
        self.assertTrue(req.call_args.args[1].endswith('/777/phone_numbers'))
        self.assertEqual((out['ok'], out['numbers'][0]['id'], out['current']), (True, '109', '555'))

    def test_a_bad_account_id_is_rejected_without_calling_meta(self):
        boss, _ = self.clients()
        with patch('requests.request') as req:
            out = boss.post('/api/admin/chatbot/numbers/', {'waba_id': 'abc'}, format='json').json()
        self.assertFalse(out['ok'])
        req.assert_not_called()

    def test_a_missing_account_explains_the_assignment_step(self):
        boss, _ = self.clients()
        err = _Res(400, {'error': {'code': 100, 'message': 'Object with ID does not exist'}})
        with patch('requests.request', return_value=err):
            out = boss.post('/api/admin/chatbot/numbers/', {'waba_id': '777'}, format='json').json()
        self.assertEqual((out['ok'], out['code']), (False, '100'))
        self.assertIn('assigned', out['error'])

    def test_register_sends_the_pin_and_never_audits_it(self):
        from apps.accounts.models import AuditLog
        boss, _ = self.clients()
        with patch('requests.request', return_value=_Res(200, {'success': True})) as req:
            out = boss.post('/api/admin/chatbot/register/', {'pin': '123456'}, format='json').json()
        self.assertTrue(out['ok'])
        self.assertEqual(req.call_args.kwargs['json'], {'messaging_product': 'whatsapp', 'pin': '123456'})
        self.assertTrue(req.call_args.args[1].endswith('/555/register'))
        self.assertNotIn('123456', ' '.join(str(a.metadata) for a in AuditLog.objects.all()))

    def test_register_rejects_a_bad_pin_and_reports_metas_refusal(self):
        boss, _ = self.clients()
        with patch('requests.request') as req:
            self.assertFalse(boss.post('/api/admin/chatbot/register/', {'pin': '12'}, format='json').json()['ok'])
        req.assert_not_called()
        err = _Res(400, {'error': {'code': 133005, 'message': 'Two step verification PIN Mismatch'}})
        with patch('requests.request', return_value=err):
            out = boss.post('/api/admin/chatbot/register/', {'pin': '654321'}, format='json').json()
        self.assertEqual((out['ok'], out['code']), (False, '133005'))
        self.assertIn('PIN is wrong', out['error'])

    def test_only_superusers_can_use_the_tools(self):
        _, clerk = self.clients()
        with patch('requests.request') as req:
            self.assertEqual(clerk.post('/api/admin/chatbot/numbers/', {'waba_id': '777'}, format='json').status_code, 403)
            self.assertEqual(clerk.post('/api/admin/chatbot/register/', {'pin': '123456'}, format='json').status_code, 403)
        req.assert_not_called()


@override_settings(WHATSAPP_TOKEN='tok', WHATSAPP_PHONE_NUMBER_ID='555', WHATSAPP_BUSINESS_ACCOUNT_ID='777')
class BusinessAccountIdTests(TestCase):
    """The WABA ID is never used to send, but with it the check can say which ID is wrong."""

    NUMBERS = _Res(200, {'data': [{'id': '109', 'display_phone_number': '+263 77 123', 'verified_name': 'BetBlits'}]})
    NOT_FOUND = _Res(400, {'error': {'code': 100, 'message': 'Object with ID does not exist'}})

    def test_sending_uses_only_the_phone_number_id(self):
        with patch('requests.post', return_value=_Res(200, {'messages': [{'id': 'w'}]})) as post:
            whatsapp.send('263771234567', {'text': 'hi'})
        self.assertTrue(post.call_args.args[0].endswith('/555/messages'))
        self.assertNotIn('777', post.call_args.args[0])

    def test_a_wrong_phone_number_id_is_named_and_the_right_ones_listed(self):
        with patch('requests.request', side_effect=[self.NOT_FOUND, self.NUMBERS]):
            out = whatsapp.check_connection()
        self.assertFalse(out['ok'])
        self.assertIn('phone number ID is wrong', out['diagnosis'])
        self.assertIn('109', out['diagnosis'])

    def test_a_token_that_cannot_see_the_account_is_called_a_token_problem(self):
        with patch('requests.request', side_effect=[self.NOT_FOUND, self.NOT_FOUND]):
            out = whatsapp.check_connection()
        self.assertIn('token problem', out['diagnosis'])

    @override_settings(WHATSAPP_PHONE_NUMBER_ID='777')
    def test_the_same_id_in_both_boxes_is_caught_without_calling_meta(self):
        with patch('requests.request') as req:
            out = whatsapp.check_connection()
        self.assertEqual((out['ok'], out['code']), (False, 'same_id'))
        req.assert_not_called()

    def test_a_number_outside_the_account_and_no_webhook_subscription_are_warned(self):
        ok = _Res(200, {'verified_name': 'BetBlits', 'display_phone_number': '+263 77 1'})
        reg = _Res(200, {'platform_type': 'CLOUD_API'})
        acct = _Res(200, {'name': 'BetBlits Ltd', 'currency': 'USD', 'account_review_status': 'APPROVED'})
        with patch('requests.request', side_effect=[ok, reg, acct, self.NUMBERS, _Res(200, {'data': []})]):
            out = whatsapp.check_connection()
        self.assertTrue(out['ok'])
        self.assertEqual((out['account']['name'], out['account']['account_review_status']), ('BetBlits Ltd', 'APPROVED'))
        self.assertIn('not under the WhatsApp Business Account', out['warning'])
        self.assertIn('No app is subscribed', out['warning'])

    def test_find_my_numbers_defaults_to_the_configured_account(self):
        with patch('requests.request', return_value=self.NUMBERS) as req:
            out = whatsapp.list_numbers()
        self.assertTrue(out['ok'])
        self.assertTrue(req.call_args.args[1].endswith('/777/phone_numbers'))

    def test_saving_the_same_id_twice_is_refused(self):
        from apps.chatbot import config
        with self.assertRaises(config.ConfigError):
            config.update({'phone_number_id': '1818', 'waba_id': '1818'}, by='boss')
        changed = config.update({'phone_number_id': '1818', 'waba_id': '2929'}, by='boss')
        self.assertEqual(sorted(changed), ['phone_number_id', 'waba_id'])


@override_settings(WHATSAPP_TOKEN='tok', WHATSAPP_PHONE_NUMBER_ID='555', WHATSAPP_APP_ID='4242')
class NumberDetailsAndProfileTests(TestCase):
    """Test connection shows the number's details; staff edit its WhatsApp business profile."""

    def clients(self):
        from django.contrib.auth.models import User
        boss, clerk = APIClient(), APIClient()
        boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))
        clerk.force_authenticate(User.objects.create_user('clerk', 'c@example.com', 'x', is_staff=True))
        return boss, clerk

    def test_test_connection_shows_the_numbers_details(self):
        ok = _Res(200, {'verified_name': 'BetBlits', 'display_phone_number': '+263 77 1', 'quality_rating': 'GREEN'})
        details = _Res(200, {'platform_type': 'CLOUD_API', 'status': 'CONNECTED', 'name_status': 'APPROVED',
                             'messaging_limit_tier': 'TIER_1K', 'account_mode': 'LIVE', 'throughput': {'level': 'STANDARD'}})
        with patch('requests.request', side_effect=[ok, details]):
            out = whatsapp.check_connection()
        self.assertEqual((out['ok'], out['name_status'], out['messaging_limit_tier'], out['throughput'], out['account_mode']),
                         (True, 'APPROVED', 'TIER_1K', 'STANDARD', 'LIVE'))
        self.assertNotIn('warning', out)

    def test_the_profile_is_read_from_the_phone_number(self):
        boss, clerk = self.clients()
        body = {'data': [{'about': 'Bet on WhatsApp', 'websites': ['https://betblits.com'], 'vertical': 'ENTERTAIN'}]}
        with patch('requests.request', return_value=_Res(200, body)) as req:
            out = clerk.get('/api/admin/chatbot/profile/').json()            # any staff member can read it
        self.assertTrue(req.call_args.args[1].endswith('/555/whatsapp_business_profile'))
        self.assertEqual((out['profile']['about'], out['profile']['websites']), ('Bet on WhatsApp', ['https://betblits.com']))

    def test_a_superuser_updates_only_the_fields_sent(self):
        boss, _ = self.clients()
        with patch('requests.request', return_value=_Res(200, {'success': True})) as req:
            out = boss.put('/api/admin/chatbot/profile/', {'about': 'Bet on WhatsApp', 'websites': ['https://betblits.com', ''],
                                                          'vertical': 'entertain'}, format='json').json()
        self.assertTrue(out['ok'])
        self.assertEqual(req.call_args.kwargs['json'], {'messaging_product': 'whatsapp', 'about': 'Bet on WhatsApp',
                                                        'websites': ['https://betblits.com'], 'vertical': 'ENTERTAIN'})

    def test_values_meta_would_refuse_are_caught_first(self):
        boss, _ = self.clients()
        bad = [{'about': 'x' * 140}, {'about': ''}, {'websites': ['a.com']}, {'websites': ['https://a', 'https://b', 'https://c']},
               {'email': 'not-an-email'}, {'vertical': 'CASINO'}, {}]
        with patch('requests.request') as req:
            for body in bad:
                self.assertFalse(boss.put('/api/admin/chatbot/profile/', body, format='json').json()['ok'], body)
        req.assert_not_called()

    def test_only_a_superuser_changes_the_profile(self):
        _, clerk = self.clients()
        with patch('requests.request') as req:
            self.assertEqual(clerk.put('/api/admin/chatbot/profile/', {'about': 'x'}, format='json').status_code, 403)
        req.assert_not_called()

    def test_the_photo_goes_through_metas_resumable_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        boss, _ = self.clients()
        photo = SimpleUploadedFile('logo.png', b'\x89PNG fake', content_type='image/png')
        with patch('requests.request', side_effect=[_Res(200, {'id': 'upload:abc'}), _Res(200, {'success': True})]) as req, \
                patch('requests.post', return_value=_Res(200, {'h': 'HANDLE'})) as post:
            out = boss.post('/api/admin/chatbot/profile/photo/', {'file': photo}, format='multipart').json()
        self.assertTrue(out['ok'], out)
        self.assertTrue(req.call_args_list[0].args[1].endswith('/4242/uploads'))
        self.assertEqual(post.call_args.kwargs['headers']['file_offset'], '0')
        self.assertEqual(req.call_args_list[1].kwargs['json']['profile_picture_handle'], 'HANDLE')

    @override_settings(WHATSAPP_APP_ID='')
    def test_the_photo_needs_the_app_id_and_an_image(self):
        self.assertIn('app ID', whatsapp.upload_profile_photo(b'x', 'image/png')['error'])
        self.assertIn('JPG or PNG', whatsapp.upload_profile_photo(b'x', 'image/gif')['error'])


class AllOddsTests(_Base):
    """Every match and every playable price can be reached from chat, and only playable ones are shown."""

    def _many(self, n, league=None):
        soon = timezone.now() + timedelta(days=1)
        return [Event.objects.create(name=f'Team {i} vs Club {i}', starts_at=soon + timedelta(minutes=i), status='NS',
                                     odds=D('2.00'), odds_draw=D('3.00'), odds_away=D('4.00'), league=league)
                for i in range(n)]

    def test_games_pages_through_every_match(self):
        self._many(18)                                   # 20 with the two from setUp
        first = self.say('GAMES')[0]
        self.assertIn('1–8 of 20', first['text'])
        self.assertIn(['NEXT', 'Next ▶'], first['buttons'])
        self.assertNotIn(['PREV', '◀ Previous'], first['buttons'])
        seen = set()
        for reply in (first, self.say('NEXT')[0], self.say('NEXT')[0]):
            seen.update(int(x) for x in __import__('re').findall(r'^\*(\d+)\* ·', reply['text'], flags=__import__('re').M))
        self.assertEqual(len(seen), 20)                  # three pages, nothing missed or repeated
        last = self.say('NEXT')[0]                       # past the end stays on the last page
        self.assertIn('17–20 of 20', last['text'])
        self.assertNotIn(['NEXT', 'Next ▶'], last['buttons'])
        self.assertIn('9–16 of 20', self.say('PREV')[0]['text'])

    def test_leagues_narrow_the_list(self):
        from apps.sportsbook.models import LeagueSetting
        epl = LeagueSetting.objects.create(league_id=39, name='Premier League')
        self._many(3, league=epl)
        [reply] = self.say('LEAGUES')
        row = next(r for r in reply['list']['rows'] if r[1] == 'Premier League')
        self.assertEqual((row[0], row[2]), (f'LEAGUE {epl.id}', '3 matches'))
        out = self.say(row[0])[0]['text']
        self.assertIn('⚽ *Premier League* · 1–3 of 3', out)
        self.assertNotIn('Dynamos', out)

    def test_every_market_is_reachable_and_tappable(self):
        cs = Market.objects.create(event=self.e1, key='correct_score:ft', name='Correct score', kind='correct_score', group='score')
        for h in range(5):
            for a in range(5):
                MarketOutcome.objects.create(market=cs, key=f'{h}:{a}', label=f'{h}-{a}', odds=D('9.00') + h + a)
        [match] = self.say(str(self.e1.id))
        groups = {r[0]: r for r in match['list']['sections'][1]['rows']}
        self.assertIn(f'{self.e1.id} G score', groups)
        [market] = self.say(f'{self.e1.id} G score')      # a group with one market opens it straight away
        self.assertIn('📊 *Correct score*', market['text'])
        self.assertIn('• 4-4 *17.00*', market['text'])   # every price is in the text…
        rows = market['list']['rows']
        self.assertEqual(len(rows), 10)                  # …and the taps page: 9 options + More
        self.assertEqual(rows[-1][1], 'More ▶')
        page2 = self.say(rows[-1][0])[0]['list']['rows']
        self.assertTrue(page2[0][1].endswith('1-4'))
        page3 = self.say('NEXT')[0]['list']['rows']       # NEXT also pages a market: the last 7 options, then Back
        self.assertEqual((len(page3), page3[0][1].endswith('3-3'), page3[-2][1].endswith('4-4'), page3[-1][0]),
                         (8, True, True, 'BACK'))
        [added] = self.say(page2[0][0])                  # tap → on the slip, confirmed
        self.assertIn('Correct score: *1-4*', added['text'])
        self.assertNotIn('(#', added['text'])            # no internal code shown

    def test_closed_settled_and_decided_prices_are_hidden_and_refused(self):
        dnb = Market.objects.create(event=self.e1, key='dnb:ft', name='Draw no bet', kind='draw_no_bet')
        home = MarketOutcome.objects.create(market=dnb, key='home', label='Dynamos', odds=D('1.50'))
        shut = MarketOutcome.objects.create(market=dnb, key='away', label='Highlanders', odds=D('2.60'), is_open=False)
        gone = Market.objects.create(event=self.e1, key='oe:ft', name='Odd/even', kind='odd_even', settled=True)
        MarketOutcome.objects.create(market=gone, key='odd', label='Odd', odds=D('1.90'))
        text_ = self.say(f'{self.e1.id} G main')[0]['text']
        self.assertIn('Dynamos *1.50*', text_)
        self.assertNotIn('Highlanders *2.60*', text_)
        self.assertNotIn('Odd/even', text_)
        self.assertIn('suspended', text(self.say(f'PICK {shut.id}')))       # a stale tap is refused
        self.assertIn('Draw no bet: *Dynamos*', text(self.say(f'PICK {home.id}')))
        self.assertIn('no longer exists', text(self.say('PICK 99999999')))

    def test_tapping_the_same_price_twice_keeps_one_leg(self):
        btts_yes = MarketOutcome.objects.get(market__event=self.e2, key='yes')
        self.say(f'{self.e2.id} GG')                     # typed…
        out = self.say(f'PICK {btts_yes.id}')[0]['text']   # …then tapped: the same outcome
        self.assertIn('Your ticket: 1 match ·', out)
        slip = text(self.say('SLIP'))
        self.assertIn('1) ', slip)
        self.assertNotIn('2) ', slip)

    def test_long_text_is_split_instead_of_cut(self):
        from apps.chatbot import whatsapp
        long = '\n'.join(f'line {i} ' + 'x' * 60 for i in range(100))       # ~7,000 characters
        parts = whatsapp.fit([{'text': long, 'prompt': 'Tap 👇', 'list': {'button': 'Choose', 'rows': [['a', 'A']]}}])
        self.assertEqual(''.join(p['text'] + '\n' for p in parts[:-1]).rstrip('\n'), long)   # every character arrives
        self.assertTrue(all(len(p['text']) <= whatsapp.MAX_TEXT for p in parts))
        self.assertEqual((parts[-1]['text'], parts[-1]['list']['button']), ('Tap 👇', 'Choose'))
        short = {'text': 'hi', 'buttons': ['MENU']}
        self.assertEqual(whatsapp.fit([short]), [short])

    def test_a_list_never_sends_more_than_ten_rows(self):
        from apps.chatbot import whatsapp
        reply = {'text': 'x', 'list': {'button': 'Go', 'sections': [
            {'title': 'A', 'rows': [[f'a{i}', f'A{i}'] for i in range(6)]},
            {'title': 'B', 'rows': [[f'b{i}', f'B{i}'] for i in range(6)]}]}}
        sections = whatsapp.payload_for(NUMBER, reply)['interactive']['action']['sections']
        self.assertEqual([len(s['rows']) for s in sections], [6, 4])


class MenuTests(_Base):
    """Two-level, tappable menu: every item answers, nothing clashes with match IDs."""

    def test_the_menu_is_a_short_tap_list_of_sections(self):
        from apps.chatbot import whatsapp
        [reply] = self.say('MENU')
        body = whatsapp.payload_for(NUMBER, reply)
        rows = body['interactive']['action']['sections'][0]['rows']
        self.assertEqual(len(rows), 8)
        self.assertLessEqual(len(body['interactive']['body']['text']), 1024)
        self.assertIn('send *LOGIN*', reply['text'])                     # not logged in yet: says how
        [money] = self.say('MENU MONEY')
        cmds = [r[0] for r in money['list']['rows']]
        self.assertEqual(cmds[:3], ['BALANCE', 'DEPOSIT', 'WITHDRAW'])
        self.assertEqual(cmds[-1], 'MENU')                                # back to the main menu
        self.assertIn(f'#{self.e1.id}', text(self.say(str(self.e1.id))))  # a number is still a match

    def test_every_menu_item_answers(self):
        from apps.chatbot.menus import ITEMS, SECTIONS
        self.linked()
        for cmd, _, _ in SECTIONS:
            self.assertIn('list', self.say(cmd)[0], cmd)
        for _, rows in ITEMS.values():
            for cmd, _, _ in rows:
                if cmd in ('STOP',):
                    continue
                out = text(self.say(cmd))
                self.assertNotIn("didn't get that", out, cmd)
                self.assertTrue(out.strip(), cmd)

    def test_today_and_tomorrow(self):
        tz = services.local_tz()
        start = timezone.localtime(timezone.now(), tz).replace(hour=0, minute=0, second=0, microsecond=0)
        late_today = start + timedelta(hours=23, minutes=30)
        tomorrow = start + timedelta(days=1, hours=15)
        Event.objects.all().delete()
        Event.objects.create(name='Late vs Night', starts_at=late_today, status='NS', odds=D('2'), odds_draw=D('3'), odds_away=D('4'))
        Event.objects.create(name='Morrow vs Next', starts_at=tomorrow, status='NS', odds=D('2'), odds_draw=D('3'), odds_away=D('4'))
        today, tmr = text(self.say('TODAY')), text(self.say('TOMORROW'))
        if late_today > timezone.now():
            self.assertIn('Late v Night', today)
        self.assertNotIn('Morrow', today)
        self.assertIn("Tomorrow's matches", tmr)
        self.assertIn('Morrow v Next', tmr)
        self.assertNotIn('Late', tmr)


@override_settings(FRONTEND_URL='https://betblits.test')
class ChatWithdrawalTests(_Base):
    """WITHDRAW: off until enabled, PIN always, only to a number deposits came from, capped, not right after linking."""

    def setUp(self):
        super().setUp()
        from apps.wallet.models import PaymentTransaction
        self.player.kyc_status = self.player.Kyc.VERIFIED
        self.player.save(update_fields=['kyc_status'])
        wallet.credit(player_id=self.player.id, amount=D('80'), kind='adjustment', bucket='winnings', idempotency_key='chat:win')
        PaymentTransaction.objects.create(reference='dep-1', player_id=self.player.id, method='ecocash', phone='0771234567',
                                          amount=D('20'), status=PaymentTransaction.Status.PAID)
        self.link = self.linked()
        ChatLink.objects.filter(pk=self.link.pk).update(linked_at=timezone.now() - timedelta(days=3))
        services.set_pin(ChatLink.objects.get(pk=self.link.pk), '4321')
        cfg = ChatbotSettings.load()
        cfg.allow_withdrawals = True
        cfg.save()

    def requests(self):
        from apps.wallet.models import WithdrawalRequest
        return WithdrawalRequest.objects.filter(player_id=self.player.id)

    def test_off_by_default(self):
        cfg = ChatbotSettings.load()
        cfg.allow_withdrawals = False
        cfg.save()
        self.assertIn('switched off', text(self.say('WITHDRAW 10')))
        self.assertEqual(self.requests().count(), 0)

    def test_a_withdrawal_with_the_pin_goes_to_the_deposit_number(self):
        info = text(self.say('WITHDRAW'))
        self.assertIn('$80.00', info)
        self.assertIn('EcoCash ••4567', info)
        quote = text(self.say('WITHDRAW 20'))
        self.assertIn('You receive: *$19.00*', quote)                    # 5% fee
        self.assertIn('Wrong or missing PIN', text(self.say('CONFIRM')))
        self.assertEqual(self.requests().count(), 0)
        done = text(self.say('CONFIRM 4321'))
        self.assertIn('Withdrawal requested: *$20.00*', done)
        req = self.requests().get()
        self.assertEqual((req.amount, req.method, req.account_number, req.wallet), (D('20.00'), 'ecocash', '0771234567', 'winnings'))

    def test_three_wrong_pins_cancel_it(self):
        self.say('WITHDRAW 10')
        self.say('CONFIRM 0000')
        self.say('CONFIRM 1111')
        self.assertIn('cancelled', text(self.say('CONFIRM 2222')))
        self.assertIn('There is no ticket waiting', text(self.say('CONFIRM 4321')))   # the right PIN now does nothing
        self.assertEqual(self.requests().count(), 0)

    def test_no_pin_no_withdrawal(self):
        services.clear_pin(ChatLink.objects.get(pk=self.link.pk))
        self.assertIn('need your chat PIN', text(self.say('WITHDRAW 10')))

    def test_a_newly_linked_number_waits(self):
        ChatLink.objects.filter(pk=self.link.pk).update(linked_at=timezone.now() - timedelta(hours=2))
        self.assertIn('newly linked number', text(self.say('WITHDRAW 10')))

    def test_only_to_numbers_deposits_came_from(self):
        from apps.wallet.models import PaymentTransaction
        PaymentTransaction.objects.all().delete()
        self.assertIn('none yet', text(self.say('WITHDRAW 10')))
        PaymentTransaction.objects.create(reference='dep-2', player_id=self.player.id, method='ecocash', phone='0771234567',
                                          amount=D('5'), status=PaymentTransaction.Status.PAID)
        PaymentTransaction.objects.create(reference='dep-3', player_id=self.player.id, method='onemoney', phone='0711112222',
                                          amount=D('5'), status=PaymentTransaction.Status.PAID)
        PaymentTransaction.objects.create(reference='dep-4', player_id=self.player.id, method='ecocash', phone='0779999999',
                                          amount=D('5'), status=PaymentTransaction.Status.FAILED)      # never paid: not offered
        [choose] = self.say('WITHDRAW 10')
        labels = [r[1] for r in choose['list']['rows']]
        self.assertEqual(sorted(labels), ['EcoCash ••4567', 'OneMoney ••2222'])
        onemoney = next(r[0] for r in choose['list']['rows'] if 'OneMoney' in r[1])
        self.say(onemoney)
        self.say('CONFIRM 4321')
        self.assertEqual(self.requests().get().account_number, '0711112222')

    def test_the_daily_chat_limit(self):
        cfg = ChatbotSettings.load()
        cfg.withdraw_daily_cap = D('30')
        cfg.save()
        self.say('WITHDRAW 20')
        self.say('CONFIRM 4321')
        self.assertIn('up to $30.00 a day ($10.00 left today)', text(self.say('WITHDRAW 15')))

    def test_only_a_superuser_changes_withdrawal_settings(self):
        from django.contrib.auth.models import User
        clerk, boss = APIClient(), APIClient()
        clerk.force_authenticate(User.objects.create_user('clerk', 'c@example.com', 'x', is_staff=True))
        boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))
        cfg = ChatbotSettings.load()
        same = {'max_stake': '40', 'allow_withdrawals': True, 'withdraw_daily_cap': str(cfg.withdraw_daily_cap),
                'withdraw_cooldown_hours': cfg.withdraw_cooldown_hours}
        self.assertEqual(clerk.put('/api/admin/chatbot/', same, format='json').status_code, 200)   # unchanged: fine
        self.assertEqual(clerk.put('/api/admin/chatbot/', {**same, 'allow_withdrawals': False}, format='json').status_code, 403)
        self.assertTrue(ChatbotSettings.load().allow_withdrawals)
        out = boss.put('/api/admin/chatbot/', {**same, 'withdraw_cooldown_hours': 72}, format='json').json()
        self.assertEqual((out['withdraw_cooldown_hours'], out['can_edit_withdrawals']), (72, True))


class CashoutChatTests(_Base):
    def test_cash_out_from_chat(self):
        from apps.sportsbook import cashout
        from apps.sportsbook.models import Bet
        link = self.linked()
        bet = Bet.objects.create(player_id=link.player_id, event='Dynamos vs Highlanders', stake=D('5'), odds=D('2'),
                                 status='open', event_ref=self.e1, wallet='deposit')
        offer = cashout.Offer(available=True, value=D('6.40'))
        with patch.object(cashout, 'bet_offer', return_value=offer), patch.object(cashout, 'slip_offer', return_value=offer):
            [lst] = self.say('CASHOUT')
            row = lst['list']['rows'][0]
            self.assertEqual((row[0], row[1][:5]), (f'CASHOUT B {bet.id}', '$6.40'))
            self.assertIn('You get *$6.40*', text(self.say(row[0])))
            with patch.object(cashout, 'cash_out', return_value=(bet, None)) as take:
                self.assertIn('Cashed out *$6.40*', text(self.say('CONFIRM')))
        self.assertEqual(take.call_args.kwargs, {'kind': 'bet', 'ticket_id': bet.id, 'player_id': link.player_id,
                                                 'expected': D('6.40')})


class SearchTests(_Base):
    """League and country search, forgiving of spelling mistakes."""

    def setUp(self):
        super().setUp()
        from apps.sportsbook.models import LeagueSetting, Team
        self.epl = LeagueSetting.objects.create(league_id=39, name='Premier League', country='England')
        self.champ = LeagueSetting.objects.create(league_id=40, name='Championship', country='England')
        self.psl = LeagueSetting.objects.create(league_id=400, name='Premier Soccer League', country='Zimbabwe')
        soon = timezone.now() + timedelta(days=1)
        ars, che = Team.objects.create(name='Arsenal'), Team.objects.create(name='Chelsea')
        Event.objects.create(name='Arsenal vs Chelsea', home_team=ars, away_team=che, starts_at=soon, status='NS',
                             league=self.epl, odds=D('2'), odds_draw=D('3'), odds_away=D('4'))
        Event.objects.create(name='Leeds vs Burnley', starts_at=soon, status='NS', league=self.champ,
                             odds=D('2'), odds_draw=D('3'), odds_away=D('4'))
        Event.objects.filter(pk__in=[self.e1.pk, self.e2.pk]).update(league=self.psl)

    def test_scoring(self):
        from apps.chatbot import search
        self.assertEqual(search.best('arsnal', ['Arsenal', 'Chelsea', 'Arsenal Tula']), ['Arsenal', 'Arsenal Tula'])
        self.assertEqual(search.best('premeir leage', ['Premier League', 'Premier Soccer League', 'La Liga'])[0], 'Premier League')
        self.assertEqual(search.best('zimbabwae', ['Zimbabwe', 'Zambia']), ['Zimbabwe'])
        self.assertEqual(search.best('atletico', ['Atlético Madrid']), ['Atlético Madrid'])      # accents don't matter
        self.assertEqual(search.best('xyzzy', ['Arsenal', 'Chelsea']), [])

    def test_a_misspelt_team_still_finds_its_match(self):
        out = text(self.say('GAMES arsnal'))
        self.assertIn('Showing results for “Arsenal” (you typed “arsnal”)', out)
        self.assertIn('Arsenal v Chelsea', out)

    def test_league_by_name_even_misspelt(self):
        out = text(self.say('LEAGUE premeir leage'))
        self.assertIn('Premier League', out)
        [many] = self.say('LEAGUE premier')                              # two leagues contain "premier": pick one
        self.assertEqual({r[1] for r in many['list']['rows']}, {'Premier League', 'Premier Soccer League'})
        self.assertIn('Leeds v Burnley', text(self.say('LEAGUE champinship')))

    def test_country(self):
        [eng] = self.say('COUNTRY england')                              # two leagues there: choose
        self.assertEqual({r[1] for r in eng['list']['rows']}, {'Premier League', 'Championship'})
        out = text(self.say('COUNTRY zimbabwae'))                       # one league there: straight to its matches
        self.assertIn('Showing Zimbabwe (you typed “zimbabwae”)', out)
        self.assertIn('Dynamos v Highlanders', out)
        [countries] = self.say('COUNTRIES')
        self.assertEqual([r[0] for r in countries['list']['rows']], ['COUNTRY England', 'COUNTRY Zimbabwe'])
        self.assertIn('No country matching', text(self.say('COUNTRY atlantis')))

    def test_searching_a_country_name_in_games(self):
        self.assertIn('Leeds v Burnley', text(self.say('GAMES england')))


class LoginTests(_Base):
    """LOGIN with the website's username and password; logged out after 5 idle minutes."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()

    def log_in(self, now=None):
        engine.handle(NUMBER, 'LOGIN', now=now)
        engine.handle(NUMBER, 'rudo', now=now)
        return text(engine.handle(NUMBER, 'Pass-word-123', now=now))

    def at(self, minutes):
        return timezone.now() + timedelta(minutes=minutes)

    def say_at(self, msg, minutes):
        return engine.handle(NUMBER, msg, now=self.at(minutes))

    def test_log_in_with_the_website_details(self):
        self.assertIn('send *LOGIN*', text(self.say('BALANCE')))
        self.assertIn('username', text(self.say('LOGIN')))
        self.assertIn('password', text(self.say('rudo')))
        out = text(self.say('Pass-word-123'))
        self.assertIn('Logged in as *rudo*', out)
        self.assertIn('delete your password message', out)
        self.assertEqual(ChatLink.objects.get(address=NUMBER).player_id, self.player.id)   # the number is now theirs
        self.assertIn('Deposit', text(self.say('BALANCE')))
        from apps.notifications.models import Notification
        self.assertTrue(Notification.objects.filter(player_id=self.player.id, title='WhatsApp login').exists())

    def test_one_message_and_email_work_too(self):
        self.assertIn('Logged in as *rudo*', text(self.say('LOGIN rudo Pass-word-123')))
        self.say('LOGOUT')
        self.assertIn('Logged in as *rudo*', text(self.say('LOGIN rudo@example.com Pass-word-123')))

    def test_wrong_details_and_guessing_limits(self):
        self.assertIn('Wrong username or password', text(self.say('LOGIN rudo wrong-pass')))
        self.assertIn('Wrong username or password', text(self.say('LOGIN nobody whatever')))
        for _ in range(3):
            self.say('LOGIN rudo wrong-pass')
        self.assertIn('Too many wrong tries', text(self.say('LOGIN rudo Pass-word-123')))   # even the right one now
        self.assertNotIn('auth', ChatSession.objects.get(address=NUMBER).state)

    def test_one_username_cant_be_guessed_from_many_numbers(self):
        for i in range(10):
            engine.handle(f'26377000{i:04d}', 'LOGIN rudo wrong-pass')
        self.assertIn('Too many wrong tries', text(self.say('LOGIN rudo Pass-word-123')))

    def test_a_suspended_account_cant_log_in(self):
        Player.objects.filter(pk=self.player.pk).update(is_suspended=True)
        self.assertIn('suspended', text(self.say('LOGIN rudo Pass-word-123')))

    def test_idle_for_five_minutes_logs_out(self):
        self.assertIn('Logged in', self.log_in(self.at(0)))
        self.assertIn('Deposit', text(self.say_at('BALANCE', 4)))          # activity keeps it alive
        self.assertIn('Deposit', text(self.say_at('BALANCE', 8)))
        out = text(self.say_at('BALANCE', 14))                             # 6 minutes idle
        self.assertIn('logged out after 5 minutes without activity', out)
        self.assertNotIn('Deposit', out)
        self.assertIn('Dynamos', text(self.say_at('GAMES', 15)))           # browsing needs no login

    def test_logout_drops_anything_waiting_for_confirm(self):
        self.log_in()
        self.say(f'{self.e1.id} 1')
        self.say('BET 2')
        self.assertIn('Logged out', text(self.say('LOGOUT')))
        self.assertIn('send *LOGIN*', text(self.say('CONFIRM')))
        self.log_in()
        self.assertIn('no ticket waiting', text(self.say('CONFIRM')))
        self.assertIn('Your ticket', text(self.say('SLIP')))                # the slip itself is kept

    def test_cancel_leaves_the_login(self):
        self.say('LOGIN')
        self.assertIn('Cancelled', text(self.say('CANCEL')))
        self.assertIn('Dynamos', text(self.say('GAMES')))                  # not taken as a username

    def test_login_can_be_switched_off_for_a_linked_number(self):
        self.linked()
        self.say('LOGOUT')
        cfg = ChatbotSettings.load()
        cfg.require_login = False
        cfg.save()
        self.assertIn('Deposit', text(self.say('BALANCE')))

    def test_my_account_is_first_and_shows_log_in_or_out(self):
        [menu] = self.say('MENU')
        self.assertEqual(menu['list']['rows'][0][0], 'MENU ACCOUNT')
        self.assertEqual([r[0] for r in self.say('MENU ACCOUNT')[0]['list']['rows'][:2]], ['LOGIN', 'REGISTER'])
        self.log_in()
        self.assertIn('Logged in', self.say('MENU')[0]['text'])
        self.assertEqual(self.say('MENU ACCOUNT')[0]['list']['rows'][0][0], 'LOGOUT')

    def test_passwords_never_reach_the_inbox(self):
        import hashlib
        import hmac
        import json as _json
        from apps.chatbot.models import InboundMessage
        secret = 'chat-secret'

        def send(body, i):
            raw = _json.dumps({'entry': [{'changes': [{'value': {'messages': [
                {'from': NUMBER, 'id': f'wamid.p{i}', 'type': 'text', 'text': {'body': body}}]}}]}]}).encode()
            sig = 'sha256=' + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            with patch('requests.post'):
                APIClient().generic('POST', '/api/chatbot/whatsapp/webhook/', raw, content_type='application/json',
                                    HTTP_X_HUB_SIGNATURE_256=sig)
        with override_settings(WHATSAPP_APP_SECRET=secret):
            for i, body in enumerate(('LOGIN', 'rudo', 'Pass-word-123', 'LOGOUT', 'LOGIN rudo Pass-word-123', 'CONFIRM 2468')):
                send(body, i)
        stored = list(InboundMessage.objects.order_by('id').values_list('text', flat=True))
        self.assertEqual(stored, ['LOGIN', 'rudo', services.HIDDEN, 'LOGOUT', f'LOGIN rudo {services.HIDDEN}', 'CONFIRM ••••'])
        self.assertFalse(any('Pass-word-123' in t for t in stored))


@pytest.mark.agent_code
class RegisterTests(_Base):
    """REGISTER in chat: agent code (mandatory), username, 18+ and terms, password: same account as the website."""

    def setUp(self):
        super().setUp()
        from apps.affiliates import services as affiliates
        from apps.affiliates.models import Affiliate
        agent = accounts.register_player(username='agentx', email='agent@example.com', password='Pass-word-123')
        aff = affiliates.apply(player_id=agent.id, code='AGENT7')
        Affiliate.objects.filter(pk=aff.pk).update(status=Affiliate.Status.ACTIVE)
        self.num = '263779990000'

    def chat(self, msg):
        return text(engine.handle(self.num, msg))

    def test_signing_up_in_chat(self):
        from apps.affiliates.models import Referral
        from django.contrib.auth import authenticate
        self.assertIn('agent code', self.chat('REGISTER'))
        self.assertIn('isn’t valid', self.chat('NOPE99'))
        self.assertIn('Agent code accepted', self.chat('agent7'))
        self.assertIn('taken', self.chat('rudo'))
        self.assertIn('18 or older', self.chat('Tendai_99'))
        self.assertIn('password', self.chat('YES'))
        self.assertIn('8 to 128', self.chat('short'))
        out = self.chat('My-Secret-pass1')
        self.assertIn('Welcome to', out)
        p = Player.objects.get(username='tendai_99')
        self.assertTrue(Referral.objects.filter(player_id=p.id, affiliate__code='AGENT7').exists())
        self.assertIsNotNone(authenticate(username='tendai_99', password='My-Secret-pass1'))   # works on the website
        self.assertEqual(ChatLink.objects.get(address=self.num).player_id, p.id)
        self.assertIn('Deposit', self.chat('BALANCE'))                                        # and logged in here
        self.assertNotIn('My-Secret-pass1', str(ChatSession.objects.get(address=self.num).state))

    def test_no_agent_code_no_account(self):
        self.chat('REGISTER')
        self.assertIn('required', self.chat('SKIP'))
        self.assertIn('Cancelled', self.chat('CANCEL'))
        self.assertFalse(Player.objects.filter(username='skip').exists())

    def test_the_website_also_needs_a_valid_agent_code(self):
        body = {'username': 'webby', 'email': 'w@example.com', 'password': 'Pass-word-123', 'accept_terms': True}
        self.assertEqual(APIClient().get('/api/auth/register/').json(), {'agent_code_required': True})
        res = APIClient().post('/api/auth/register/', body, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('agent_code', res.json())
        self.assertEqual(APIClient().post('/api/auth/register/', {**body, 'agent_code': 'BAD1'}, format='json').status_code, 400)
        ok = APIClient().post('/api/auth/register/', {**body, 'agent_code': 'agent7'}, format='json')
        self.assertEqual(ok.status_code, 201, ok.content)

    def test_switched_off_codes_are_optional(self):
        from apps.affiliates.models import AffiliateProgramme
        AffiliateProgramme.objects.filter(pk=1).update(require_agent_code=False)
        self.chat('REGISTER')
        self.assertIn('Step 2', self.chat('SKIP'))


class NavigationTests(_Base):
    """BACK goes up a level; a message the bot doesn't understand shows where the player was."""

    def test_back_climbs_the_levels(self):
        self.say('MENU')
        self.say('MENU BET')
        self.say('TODAY')
        self.say(str(self.e1.id))
        self.say(f'{self.e1.id} G main')
        self.assertIn(f'*#{self.e1.id} Dynamos v Highlanders*', text(self.say('BACK')))   # the match
        self.assertIn('⚽ *', text(self.say('BACK')))                                       # today's list
        back = self.say('BACK')[0]                                                          # the Bet section
        self.assertEqual(back['list']['rows'][0][0], 'TODAY')
        self.assertEqual(self.say('BACK')[0]['list']['rows'][0][0], 'MENU ACCOUNT')         # the main menu
        self.assertEqual(self.say('BACK')[0]['list']['rows'][0][0], 'MENU ACCOUNT')         # and it stays there

    def test_a_mistake_shows_where_they_were(self):
        self.say('GAMES')
        self.say(str(self.e1.id))
        [reply] = self.say('blah blah')
        self.assertIn("Sorry, I didn't get that. Here is where you were", reply['text'])
        self.assertIn(f'*#{self.e1.id} Dynamos v Highlanders*', reply['text'])
        self.assertIn('list', reply)                                                         # its taps are there too
        self.assertIn('Upcoming', text(self.say('BACK')))                                    # the mistake isn't a level

    def test_lost_on_the_menu_or_with_nothing_open(self):
        [reply] = self.say('qwerty')
        self.assertIn("Sorry, I didn't get that", reply['text'])
        self.assertEqual(reply['list']['rows'][0][0], 'MENU ACCOUNT')

    def test_errors_offer_a_way_back(self):
        self.say('GAMES')
        out = self.say(f'{self.e1.id} ZZ')[0]
        self.assertIn('not a pick', out['text'])
        self.assertIn(['RETURN', '⬅️ Back'], out['buttons'])
        self.assertIn('Upcoming', text(self.say('RETURN')))                                  # back to where they were

    def test_prev_still_turns_pages(self):
        soon = timezone.now() + timedelta(days=2)
        for i in range(10):
            Event.objects.create(name=f'T{i} vs C{i}', starts_at=soon + timedelta(minutes=i), status='NS',
                                 odds=D('2'), odds_draw=D('3'), odds_away=D('4'))
        self.say('GAMES')
        self.assertIn('9–12 of 12', text(self.say('NEXT')))
        self.assertIn('1–8 of 12', text(self.say('PREV')))


class SameMatchChatTests(_Base):
    def test_picks_from_one_match_show_as_one_entry_at_one_price(self):
        from apps.sportsbook import services as sb
        self.say(f'{self.e1.id} 1, {self.e1.id} O2.5, {self.e2.id} GG')
        slip = text(self.say('SLIP'))
        self.assertIn('🔗 Same match: *Dynamos Win & Over 2.5 Goals*', slip)
        self.assertEqual(slip.count(f'#{self.e1.id} '), 1)                 # the match appears once
        priced = sb.check_accumulator([
            {'event_id': self.e1.id, 'selection': 'home', 'odds': '2.00'},
            {'outcome_id': MarketOutcome.objects.get(market__event=self.e1, key='over').id, 'odds': '2.10'},
            {'outcome_id': MarketOutcome.objects.get(market__event=self.e2, key='yes').id, 'odds': '1.80'}])
        self.assertIn(f'Total odds {priced["combined_odds"]}', slip)        # the price it will be placed at
        self.linked()
        self.assertIn('2 matches (3 picks)', text(self.say('STAKE')))       # a ticket counts matches, not picks
