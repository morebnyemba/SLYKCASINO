"""The chat conversation: plain-text commands in, replies out.

Browsing needs no account; anything with money needs the chat number linked
from the player's logged-in account (LINK 123456). Every bet goes through the
same placement services as the website (prices, wallet rules, ticket limits,
the near-win guard, the in-play delay), behind a BET → YES confirmation, the
chat stake limits and the chat PIN.

    MENU                      what the bot can do
    GAMES [team/league]       upcoming matches with their IDs and 1X2 prices
    LIVE                      matches trading in play now
    1234                      one match: every quick pick and its code
    1234 1   ·  1234 O2.5, 5678 GG
                              add picks to the slip (1 X 2 1X 12 X2 GG NG O2.5 U2.5…)
    SLIP · REMOVE 1234 · CLEAR
    BET 5 [DEP|WIN|BONUS]     stake the slip (asks for YES)
    YES [PIN] · NO
    BALANCE · TICKETS
    BOOK · CODE ABC123        save the slip as a booking code / load one
    DEPOSIT 10 [ECOCASH|ONEMONEY|INNBUCKS] [0771234567]
    LINK 123456 · STOP
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction
from django.utils import timezone

from . import services
from .models import WHATSAPP, ChatbotSettings, ChatLink, ChatSession, ChatTicket

logger = logging.getLogger(__name__)

MAX_LEGS = 15
LIST_SIZE = 10
CONFIRM_FOR = timedelta(minutes=2)
PIN_TRIES = 3
SITE_PATH = 'Account → WhatsApp betting'
PICK = re.compile(r'^(1X|12|X2|1|X|2|GG|NG|[OU]\d+(?:\.\d+)?)$')
WALLETS = {'DEP': 'deposit', 'DEPOSIT': 'deposit', 'WIN': 'winnings', 'WINNINGS': 'winnings', 'BONUS': 'bonus'}
METHODS = {'ECOCASH': 'ecocash', 'ONEMONEY': 'onemoney', 'INNBUCKS': 'innbucks'}
MENU_BUTTONS = ['GAMES', 'LIVE', 'SLIP']
# Buttons as [command, label]: the label is what the player sees, the command is what a tap sends.
ADD_MORE = ['GAMES', '➕ Add more']
VIEW_SLIP = ['SLIP', '🧾 View slip']
PLACE_BET = ['STAKE', '✅ Place bet']
CONFIRM = ['CONFIRM', '✅ Confirm']
CANCEL = ['NO', '✖ Cancel']
QUICK_STAKES = (Decimal('1'), Decimal('2'), Decimal('5'), Decimal('10'), Decimal('20'), Decimal('50'))
# The order picks are offered in a match's tap list (WhatsApp shows at most ten).
PICK_ORDER = ('1', 'X', '2', 'GG', 'NG', 'O2.5', 'U2.5', '1X', '12', 'X2', 'O1.5', 'U1.5', 'O3.5', 'U3.5')


def _money(v) -> str:
    return f'${Decimal(str(v)):.2f}'


def _odds(v) -> str:
    return f'{Decimal(str(v)):.2f}'


def _site() -> str:
    try:
        from apps.branding.models import SiteIdentity
        return SiteIdentity.load().site_name or 'BetBlits'
    except Exception:  # noqa: BLE001
        return 'BetBlits'


def _reply(text: str, *buttons) -> dict:
    """A text reply with up to three buttons (a command, or [command, label])."""
    return {'text': text, 'buttons': [b for b in buttons if b]}


def _teams(e) -> tuple[str, str]:
    home = e.home_team.name if getattr(e, 'home_team_id', None) else ''
    away = e.away_team.name if getattr(e, 'away_team_id', None) else ''
    if not (home and away):
        parts = re.split(r'\s+vs?\.?\s+', e.name, maxsplit=1, flags=re.IGNORECASE)
        home, away = (parts + [''])[:2] if len(parts) == 2 else (e.name, '')
    return home or 'Home', away or 'Away'


def describe(e, code: str) -> tuple[str, str]:
    """(market, pick) in words for a pick code, e.g. ('Match result', 'Dynamos')."""
    home, away = _teams(e)
    words = {
        '1': ('Match result', home), 'X': ('Match result', 'Draw'), '2': ('Match result', away),
        '1X': ('Double chance', f'{home} or draw'), '12': ('Double chance', f'{home} or {away}'),
        'X2': ('Double chance', f'Draw or {away}'),
        'GG': ('Both teams to score', 'Yes'), 'NG': ('Both teams to score', 'No'),
    }
    if code in words:
        return words[code]
    return 'Total goals', f'{"Over" if code.startswith("O") else "Under"} {code[1:]}'


# -- entry point -------------------------------------------------------------------

def handle(address: str, text: str, *, channel: str = WHATSAPP, now=None) -> list[dict]:
    """Answer one inbound message. Never raises: an unexpected error rolls back
    this message's changes and says so."""
    now = now or timezone.now()
    try:
        with transaction.atomic():
            return _handle(channel, address, (text or '').strip(), now)
    except Exception:  # noqa: BLE001
        logger.exception('chatbot failed on a message from …%s', address[-4:])
        return [_reply('Sorry, something went wrong. Please try again in a moment.')]


def _handle(channel: str, address: str, text: str, now) -> list[dict]:
    cfg = ChatbotSettings.load()
    if not cfg.enabled:
        return [_reply(f'Betting through WhatsApp is paused right now. Please use the {_site()} website.')]
    from config.middleware import BLOCKED_DIAL_CODES
    if address.startswith(BLOCKED_DIAL_CODES):
        return [_reply(f'Sorry, {_site()} is not available in your country.')]
    session, _ = ChatSession.objects.select_for_update().get_or_create(channel=channel, address=address)
    link = services.link_for(address, channel=channel)
    if link:
        ChatLink.objects.filter(pk=link.pk).update(last_seen_at=now)
    convo = Conversation(channel, address, link, session, now, cfg)
    replies = convo.dispatch(text)
    session.save(update_fields=['state', 'updated_at'])
    return replies


class Conversation:
    def __init__(self, channel, address, link: Optional[ChatLink], session: ChatSession, now, cfg):
        self.channel, self.address, self.link, self.session, self.now, self.cfg = channel, address, link, session, now, cfg
        self.state = session.state if isinstance(session.state, dict) else {}
        session.state = self.state
        self.state.setdefault('legs', [])

    # -- routing --------------------------------------------------------------------
    def dispatch(self, text: str) -> list[dict]:
        words = text.upper().replace(',', ' , ').split()
        if not words:
            return self.menu()
        head, rest = words[0], [w for w in words[1:] if w != ',']
        simple = {
            'HI': self.menu, 'HELLO': self.menu, 'MENU': self.menu, 'HELP': self.menu, 'START': self.menu,
            'LIVE': self.live, 'SLIP': self.slip, 'CLEAR': self.clear, 'NO': self.cancel, 'CANCEL': self.cancel,
            'BALANCE': self.balance, 'BAL': self.balance, 'TICKETS': self.tickets, 'MYBETS': self.tickets,
            'BETS': self.tickets, 'BOOK': self.book, 'STOP': self.stop, 'UNLINK': self.stop,
            'STAKE': self.stake_prompt, 'PLACE': self.stake_prompt, 'BET': self.stake_prompt,
        }
        if head in simple and not rest:
            return simple[head]()
        if head in ('GAMES', 'TODAY', 'MATCHES', 'FOOTBALL'):
            return self.games(' '.join(text.split()[1:]))
        if head == 'LINK':
            return self.link_account(rest[0] if rest else '')
        if head == 'REMOVE' and rest:
            return self.remove(rest[0])
        if head == 'BET':
            return self.bet(rest)
        if head in ('YES', 'CONFIRM', 'Y'):
            return self.confirm(rest[0] if rest else '')
        if head in ('CODE', 'LOAD') and rest:
            return self.load_code(rest[0])
        if head == 'DEPOSIT':
            return self.deposit(rest)
        if head.isdigit():
            if not rest:
                return self.match(int(head))
            return self.add_picks(words)
        return [_reply("Sorry, I didn't get that. Send MENU to see what you can do.", *MENU_BUTTONS)]

    # -- help / linking -------------------------------------------------------------
    def menu(self) -> list[dict]:
        site = _site()
        lines = [f'👋 Welcome to {site} on WhatsApp.', '',
                 'GAMES – upcoming matches with their IDs', 'LIVE – matches in play now',
                 '1234 – open a match and tap a pick', '1234 1 – or type the match ID and pick (X 2 1X 12 X2 GG NG O2.5 U2.5)',
                 'SLIP – your ticket · then Place bet and Confirm', 'BALANCE · TICKETS · DEPOSIT 10']
        if not self.link:
            lines += ['', f'To bet, link your account: on the {site} website open {SITE_PATH}, get a code and send LINK 123456 here.']
        else:
            lines += ['', 'STOP – unlink this number']
        return [_reply('\n'.join(lines), *MENU_BUTTONS)]

    def link_account(self, code: str) -> list[dict]:
        if not code.isdigit():
            return [_reply(f'Send LINK and the 6-digit code from the website ({SITE_PATH}), e.g. LINK 123456.')]
        try:
            self.link = services.link(self.address, code, channel=self.channel)
        except services.ChatError as exc:
            return [_reply(str(exc))]
        from apps.accounts.models import Player
        name = Player.objects.filter(pk=self.link.player_id).values_list('username', flat=True).first() or ''
        return [_reply(f'✅ Linked to {name}. You can now bet from WhatsApp. Send GAMES to start.', *MENU_BUTTONS)]

    def stop(self) -> list[dict]:
        if not self.link:
            return [_reply('This number is not linked to an account.')]
        services.unlink(self.link.player_id, channel=self.channel, by='chat')
        self.state.clear()
        self.state['legs'] = []
        return [_reply('This number is unlinked. Nothing more can be placed from it until you link it again.')]

    def _need_link(self) -> Optional[list[dict]]:
        if self.link:
            return None
        return [_reply(f'Link your account first: on the {_site()} website open {SITE_PATH}, '
                       'get a code and send LINK 123456 here.')]

    def _player(self):
        from apps.accounts.models import Player
        return Player.objects.filter(pk=self.link.player_id).first()

    def _blocked(self) -> Optional[list[dict]]:
        """Suspended or self-excluded accounts can't bet or deposit from chat either."""
        from apps.accounts import services as accounts
        player = self._player()
        if player is None:
            return [_reply('Your account could not be found. Please contact support.')]
        try:
            accounts.check_responsible_gambling(player)
        except ValueError as exc:
            return [_reply(f'{exc}.')]
        return None

    # -- browsing -------------------------------------------------------------------
    def _line(self, e) -> str:
        from apps.sportsbook import services as sb
        when = (f'LIVE {e.elapsed or 0}\' {e.score_home or 0}-{e.score_away or 0}' if e.status in sb.IN_PLAY_STATUSES
                else timezone.localtime(e.starts_at).strftime('%a %d %b %H:%M') if e.starts_at else '')
        prices = ' '.join(f'{c} {_odds(v)}' for c, v in (('1', e.odds), ('X', e.odds_draw), ('2', e.odds_away))
                          if v is not None and v > 1)
        return f'#{e.id} {e.name}\n   {when} · {prices}'

    def games(self, query: str) -> list[dict]:
        from apps.sportsbook.models import Event
        qs = Event.objects.filter(is_open=True, has_odds=True, starts_at__gt=self.now).order_by('starts_at')
        q = query.strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(name__icontains=q) | Q(league__name__icontains=q))
        events = list(qs.select_related('league')[:LIST_SIZE])
        if not events:
            return [_reply(f'No upcoming matches{f" for “{q}”" if q else ""} right now.', 'LIVE', 'MENU')]
        head = f'⚽ Upcoming{f" · {q}" if q else ""}:'
        body = '\n'.join(self._line(e) for e in events)
        return [_reply(f'{head}\n{body}\n\nSend a match ID (e.g. {events[0].id}) to see its picks, '
                       f'or add one straight away: {events[0].id} 1', 'LIVE', 'SLIP')]

    def live(self) -> list[dict]:
        from apps.sportsbook import services as sb
        from apps.sportsbook.models import Event
        events = [e for e in Event.objects.filter(status__in=sb.IN_PLAY_STATUSES, is_open=True).order_by('starts_at')[:60]
                  if sb.in_play_bettable(e, now=self.now)][:LIST_SIZE]
        if not events:
            return [_reply('No matches are trading in play right now.', 'GAMES', 'MENU')]
        body = '\n'.join(self._line(e) for e in events)
        return [_reply(f'🔴 In play now:\n{body}\n\nSend a match ID to see its live picks.', 'GAMES', 'SLIP')]

    def _quick(self, e) -> list[tuple[str, Decimal]]:
        """(pick code, price) for every quick pick open on the match."""
        from apps.sportsbook import services as sb
        from apps.sportsbook.models import Market
        out: list[tuple[str, Decimal]] = []
        if sb.trading_state(e)['main_open']:
            blocked = set(sb.trading_state(e).get('main_blocked') or [])
            for code, sel, price in (('1', 'home', e.odds), ('X', 'draw', e.odds_draw), ('2', 'away', e.odds_away)):
                if price is not None and price > 1 and sel not in blocked:
                    out.append((code, price))
        markets = (Market.objects.filter(event=e, period='ft', metric='goals', is_open=True, settled=False,
                                         kind__in=('double_chance', 'btts', 'over_under'))
                   .prefetch_related('outcomes').order_by('kind', 'line'))
        for m in markets:
            for o in m.outcomes.all():
                if not o.is_open or o.odds <= 1 or o.result != 'pending':
                    continue
                code = self._code_for(m, o)
                if code:
                    out.append((code, o.odds))
        return out

    @staticmethod
    def _code_for(m, o) -> str:
        if m.kind == 'double_chance':
            return {'1x': '1X', '12': '12', 'x2': 'X2'}.get(o.key, '')
        if m.kind == 'btts':
            return {'yes': 'GG', 'no': 'NG'}.get(o.key, '')
        if m.kind == 'over_under' and m.line is not None and o.key in ('over', 'under'):
            return f'{o.key[0].upper()}{format(m.line.normalize(), "f")}'
        return ''

    def match(self, event_id: int) -> list[dict]:
        from apps.sportsbook import services as sb
        from apps.sportsbook.models import Event
        e = Event.objects.filter(pk=event_id).first()
        if e is None:
            return [_reply(f'There is no match #{event_id}. Send GAMES for the list.', 'GAMES')]
        if not sb.trading_state(e)['bettable']:
            return [_reply(f'#{e.id} {e.name} is not taking bets right now.', 'GAMES', 'LIVE')]
        picks = self._quick(e)
        if not picks:
            return [_reply(f'#{e.id} {e.name}: no picks are open right now. Try again shortly.', 'GAMES')]
        rank = {c: i for i, c in enumerate(PICK_ORDER)}
        picks.sort(key=lambda p: rank.get(p[0], len(PICK_ORDER)))
        rows, lines = [], []
        for code, price in picks:
            market, pick = describe(e, code)
            lines.append(f'{code} · {market}: {pick} @ {_odds(price)}')
            rows.append([f'{e.id} {code}', f'{code} @ {_odds(price)}', f'{market}: {pick}'])
        return [{'text': f'{self._line(e)}\n\n' + '\n'.join(lines)
                         + f'\n\nTap “Choose a pick”, or type {e.id} and a pick, e.g. {e.id} {picks[0][0]}.',
                 'list': {'button': 'Choose a pick', 'title': f'#{e.id}', 'rows': rows[:10]}}]

    # -- the slip ---------------------------------------------------------------------
    def _resolve(self, e, code: str) -> dict:
        """One pick on a match as a slip leg, or ChatError."""
        from apps.sportsbook import services as sb
        from apps.sportsbook.models import Market
        if not sb.trading_state(e)['bettable']:
            raise services.ChatError(f'#{e.id} is not taking bets right now.')
        if code in ('1', 'X', '2'):
            sel = {'1': 'home', 'X': 'draw', '2': 'away'}[code]
            price = {'home': e.odds, 'draw': e.odds_draw, 'away': e.odds_away}[sel]
            if not sb.trading_state(e)['main_open'] or price is None or price <= 1:
                raise services.ChatError(f'#{e.id} {code} is not available right now.')
            return self._leg(e, code, price, event_id=e.id, selection=sel)
        if code in ('1X', '12', 'X2'):
            kind, key, line = 'double_chance', code.lower(), None
        elif code in ('GG', 'NG'):
            kind, key, line = 'btts', 'yes' if code == 'GG' else 'no', None
        else:
            try:
                line = Decimal(code[1:])
            except InvalidOperation as exc:
                raise services.ChatError(f'“{code}” is not a pick.') from exc
            kind, key = 'over_under', 'over' if code[0] == 'O' else 'under'
        qs = Market.objects.filter(event=e, kind=kind, period='ft', metric='goals', is_open=True, settled=False)
        if line is not None:
            qs = qs.filter(line=line)
        for m in qs:
            o = m.outcomes.filter(key=key, is_open=True, result='pending', odds__gt=1).first()
            if o is not None:
                return self._leg(e, code, o.odds, outcome_id=o.id)
        raise services.ChatError(f'#{e.id} {code} is not available right now.')

    def _leg(self, e, code: str, price, *, event_id=None, selection=None, outcome_id=None) -> dict:
        market, pick = describe(e, code)
        return {'match': e.id, 'pick': code, 'event_id': event_id, 'selection': selection, 'outcome_id': outcome_id,
                'event': e.name, 'market': market, 'pick_text': pick,
                'kickoff': timezone.localtime(e.starts_at).strftime('%a %d %b %H:%M') if e.starts_at else '',
                'label': f'{e.name} – {market}: {pick}', 'odds': str(price)}

    def add_picks(self, words: list[str]) -> list[dict]:
        from apps.sportsbook.models import Event
        # "1234 1 , 5678 GG" → [(1234, '1'), (5678, 'GG')]
        pairs, current = [], None
        for w in words:
            if w == ',':
                continue
            if w.isdigit() and current is None:          # position decides: an ID, then its pick
                current = int(w)
            elif current is not None and PICK.match(w):
                pairs.append((current, w))
                current = None
            else:
                return [_reply(f'“{w}” is not a pick. Use 1 X 2 1X 12 X2 GG NG O2.5 U2.5, e.g. 1234 1.')]
        if current is not None:
            return self.match(current)
        added, problems = [], []
        legs = self.state['legs']
        for event_id, code in pairs:
            e = Event.objects.filter(pk=event_id).first()
            if e is None:
                problems.append(f'#{event_id} does not exist')
                continue
            try:
                leg = self._resolve(e, code)
            except services.ChatError as exc:
                problems.append(str(exc))
                continue
            legs[:] = [x for x in legs if not (x['match'] == leg['match'] and x['pick'] == leg['pick'])]
            if len(legs) >= MAX_LEGS:
                problems.append(f'a slip holds at most {MAX_LEGS} picks')
                break
            legs.append(leg)
            added.append(leg)
        self.state.pop('pending', None)
        out = []
        for leg in added:
            out.append(f'✅ Selection confirmed\n#{leg["match"]} {leg["event"]}'
                       + (f'\n🕒 {leg["kickoff"]}' if leg.get('kickoff') else '')
                       + f'\n{leg["market"]}: {leg["pick_text"]} ({leg["pick"]})\nOdds {_odds(leg["odds"])}')
        if problems:
            out.append('⚠️ ' + '; '.join(problems))
        if legs:
            n = len(legs)
            out.append(f'🧾 Your ticket: {n} selection{"" if n == 1 else "s"} · total odds {_odds(self._total())}')
        return [_reply('\n\n'.join(out), ADD_MORE, VIEW_SLIP, PLACE_BET if legs else None)]

    def _total(self) -> Decimal:
        total = Decimal('1')
        for leg in self.state['legs']:
            total *= Decimal(leg['odds'])
        return total.quantize(Decimal('0.01'))

    def _slip_text(self) -> str:
        legs = self.state['legs']
        if not legs:
            return 'Your ticket is empty. Send GAMES, open a match and tap a pick (or type e.g. 1234 1).'
        return ('🧾 Your ticket:\n' + self._selections() + f'\nTotal odds {_odds(self._total())}'
                + '\n\nPress Place bet (or type BET 5). REMOVE 1234 takes a match off, CLEAR empties it.')

    def _selections(self) -> str:
        return '\n'.join(f'{i}) #{leg["match"]} {leg.get("event") or leg["label"]}\n    '
                         f'{leg.get("market", "Pick")}: {leg.get("pick_text") or leg["pick"]} @ {_odds(leg["odds"])}'
                         for i, leg in enumerate(self.state['legs'], 1))

    def slip(self) -> list[dict]:
        if not self.state['legs']:
            return [_reply(self._slip_text(), 'GAMES')]
        return [_reply(self._slip_text(), PLACE_BET, ADD_MORE, ['CLEAR', '🗑 Clear'])]

    def stake_prompt(self) -> list[dict]:
        """Place bet: ask how much, with quick stake buttons."""
        if (r := self._need_link()) or (r := self._blocked()):
            return r
        legs = self.state['legs']
        if not legs:
            return [_reply('Your ticket is empty. Add a selection first, e.g. 1234 1.', 'GAMES')]
        cap = self.cfg.max_stake
        quick = [q for q in QUICK_STAKES if q <= cap][:3] or [cap]
        n = len(legs)
        return [_reply(f'🧾 {n} selection{"" if n == 1 else "s"} · total odds {_odds(self._total())}\n\n'
                       f'How much do you want to stake? Tap an amount, or type BET and any amount up to {_money(cap)}, e.g. BET 3.',
                       *[[f'BET {q.normalize():f}', _money(q)] for q in quick])]

    def clear(self) -> list[dict]:
        self.state['legs'] = []
        self.state.pop('pending', None)
        return [_reply('Your ticket is empty.', 'GAMES')]

    def remove(self, ref: str) -> list[dict]:
        if not ref.isdigit():
            return [_reply('Send REMOVE and the match ID, e.g. REMOVE 1234.')]
        before = len(self.state['legs'])
        self.state['legs'] = [x for x in self.state['legs'] if x['match'] != int(ref)]
        self.state.pop('pending', None)
        if len(self.state['legs']) == before:
            return [_reply(f'#{ref} is not on your slip.\n\n{self._slip_text()}')]
        return [_reply(f'Removed #{ref}.\n\n{self._slip_text()}', 'SLIP')]

    # -- betting -----------------------------------------------------------------------
    def bet(self, args: list[str]) -> list[dict]:
        if (r := self._need_link()) or (r := self._blocked()):
            return r
        if not self.cfg.allow_betting:
            return [_reply('Betting through WhatsApp is paused. Please bet on the website.')]
        legs = self.state['legs']
        if not legs:
            return [_reply('Your ticket is empty. Add a selection first, e.g. 1234 1.', 'GAMES')]
        try:
            stake = Decimal(args[0].lstrip('$')).quantize(Decimal('0.01'))
            if stake <= 0:
                raise InvalidOperation
        except (IndexError, InvalidOperation):
            return [_reply('Send BET and your stake, e.g. BET 5.')]
        wallet_word = args[1] if len(args) > 1 else ''
        if wallet_word and wallet_word not in WALLETS:
            return [_reply('Pay from DEP (deposit), WIN (winnings) or BONUS, e.g. BET 5 WIN.')]
        try:
            services.check_stake(self.link, stake)
        except services.ChatError as exc:
            return [_reply(str(exc))]
        wallet = WALLETS.get(wallet_word) or self._auto_wallet(stake)
        total = self._total()
        self.state['pending'] = {'stake': str(stake), 'wallet': wallet, 'odds': [leg['odds'] for leg in legs],
                                 'expires': (self.now + CONFIRM_FOR).isoformat(), 'pin_tries': 0}
        pin = services.needs_pin(self.link, stake)
        kind = 'Single' if len(legs) == 1 else f'Multiple · {len(legs)} selections'
        text = (f'🎟️ Confirm your ticket ({kind})\n\n{self._selections()}\n\n'
                f'Stake {_money(stake)} from your {wallet} wallet\n'
                f'Total odds {_odds(total)} · possible win {_money(stake * total)}\n\n'
                + ('Type CONFIRM and your PIN, e.g. CONFIRM 1234, within 2 minutes.' if pin
                   else 'Press Confirm within 2 minutes to place it.'))
        if pin and not self.link.pin_hash:
            text = (f'Stakes above {_money(self.cfg.pin_above)} need a chat PIN. '
                    f'Set one on the website ({SITE_PATH}), then press Place bet again.')
            self.state.pop('pending', None)
            return [_reply(text)]
        return [_reply(text, *((CANCEL,) if pin else (CONFIRM, CANCEL)))]

    def _auto_wallet(self, stake: Decimal) -> str:
        from apps.wallet import services as wallet_services
        b = wallet_services.get_balances(self.link.player_id)
        if b.get('deposit', 0) >= stake:
            return 'deposit'
        if b.get('winnings', 0) >= stake:
            return 'winnings'
        return 'deposit'

    def cancel(self) -> list[dict]:
        had = self.state.pop('pending', None)
        return [_reply('Cancelled. Your selections are kept.' if had else 'Nothing to cancel.', VIEW_SLIP)]

    def confirm(self, pin: str) -> list[dict]:
        if (r := self._need_link()) or (r := self._blocked()):
            return r
        pending = self.state.get('pending')
        if not pending:
            return [_reply('There is no ticket waiting. Press Place bet first.', PLACE_BET)]
        if timezone.datetime.fromisoformat(pending['expires']) < self.now:
            self.state.pop('pending', None)
            return [_reply('That confirmation expired. Press Place bet again.', PLACE_BET)]
        legs = self.state['legs']
        if [leg['odds'] for leg in legs] != pending['odds']:
            self.state.pop('pending', None)
            return [_reply('Your ticket changed. Press Place bet again.', PLACE_BET)]
        stake = Decimal(pending['stake'])
        if services.needs_pin(self.link, stake) and not services.pin_ok(self.link, pin):
            pending['pin_tries'] = pending.get('pin_tries', 0) + 1
            if pending['pin_tries'] >= PIN_TRIES:
                self.state.pop('pending', None)
                return [_reply('Wrong PIN too many times. The bet was cancelled.')]
            return [_reply('Wrong or missing PIN. Type CONFIRM and your PIN, e.g. CONFIRM 1234.')]
        try:
            services.check_stake(self.link, stake)
        except services.ChatError as exc:
            self.state.pop('pending', None)
            return [_reply(str(exc))]
        return self._place(stake, pending['wallet'])

    def _place(self, stake: Decimal, wallet: str) -> list[dict]:
        from apps.sportsbook import services as sb
        from apps.wallet.services import InsufficientFunds
        legs = self.state['legs']
        player_id = self.link.player_id
        try:
            if len(legs) == 1:
                leg = legs[0]
                ticket = sb.place_bet(event=leg['label'], stake=stake, odds=Decimal(leg['odds']), player_id=player_id,
                                      event_id=leg['event_id'], selection=leg['selection'] or 'home',
                                      outcome_id=leg['outcome_id'], wallet=wallet)
                kind, odds = ChatTicket.Kind.BET, Decimal(leg['odds'])
            else:
                ticket = sb.place_accumulator(stake=stake, player_id=player_id, wallet=wallet, legs=[
                    {'event': leg['label'], 'odds': leg['odds'],
                     **({'outcome_id': leg['outcome_id']} if leg['outcome_id']
                        else {'event_id': leg['event_id'], 'selection': leg['selection']})}
                    for leg in legs])
                kind, odds = ChatTicket.Kind.SLIP, ticket.combined_odds
        except sb.OddsChanged as exc:
            for leg in legs:
                if ((exc.outcome_id and leg['outcome_id'] == exc.outcome_id)
                        or (exc.event_id and leg['event_id'] == exc.event_id and leg['selection'] == exc.selection)):
                    leg['odds'] = str(exc.current)
            self.state.pop('pending', None)
            return [_reply(f'⚠️ {exc} Nothing was placed: check the new price below.\n\n{self._slip_text()}', PLACE_BET, VIEW_SLIP)]
        except sb.SelectionUnavailable as exc:
            self.state.pop('pending', None)
            return [_reply(f'⚠️ {exc} Nothing was placed. REMOVE that match and press Place bet again.\n\n{self._slip_text()}', VIEW_SLIP)]
        except InsufficientFunds:
            self.state.pop('pending', None)
            return [_reply(f'Not enough money in your {wallet} wallet. Send BALANCE, or DEPOSIT 10 to top up.', 'BALANCE')]
        except ValueError as exc:
            self.state.pop('pending', None)
            return [_reply(f'⚠️ {exc}')]
        ChatTicket.objects.create(channel=self.channel, player_id=player_id, kind=kind, object_id=ticket.id, stake=stake)
        from apps.accounts import services as accounts
        accounts.audit(player_id, 'chat_bet', None, channel=self.channel, kind=kind, ticket=ticket.id, stake=str(stake))
        self.state['legs'] = []
        self.state.pop('pending', None)
        text = (f'🎟️ Ticket {ticket.code or ticket.id} placed: {_money(stake)} at odds {_odds(odds)}, '
                f'returns up to {_money(stake * odds)}.')
        if ticket.status == 'accepting':
            text += '\nIn play: we confirm it in a few seconds and will message you.'
            self._report_later(kind, ticket.id)
        return [_reply(text, 'TICKETS', 'GAMES')]

    def _report_later(self, kind: str, ticket_id: int) -> None:
        from django.conf import settings
        delay = int(getattr(settings, 'SPORTSBOOK_LIVE_BET_DELAY', 6)) + 4
        channel, address = self.channel, self.address

        def run():
            try:
                from .tasks import report_ticket
                report_ticket.apply_async(args=(channel, address, kind, ticket_id), countdown=delay, retry=False)
            except Exception:  # noqa: BLE001 — broker down: the player sees it under TICKETS
                logger.warning('could not schedule chat ticket report', exc_info=True)
        transaction.on_commit(run)

    # -- account ------------------------------------------------------------------------
    def balance(self) -> list[dict]:
        if r := self._need_link():
            return r
        from apps.wallet import services as wallet_services
        b = wallet_services.get_balances(self.link.player_id)
        return [_reply(f'💰 Deposit {_money(b.get("deposit", 0))}\n🏆 Winnings {_money(b.get("winnings", 0))}\n'
                       f'🎁 Bonus {_money(b.get("bonus", 0))}', 'GAMES', 'TICKETS')]

    def tickets(self) -> list[dict]:
        if r := self._need_link():
            return r
        from apps.sportsbook.models import Bet, BetSlip
        pid = self.link.player_id
        rows = ([('Single', b) for b in Bet.objects.filter(player_id=pid).order_by('-placed_at')[:5]]
                + [('Multiple', s) for s in BetSlip.objects.filter(player_id=pid).order_by('-placed_at')[:5]])
        rows.sort(key=lambda r: r[1].placed_at, reverse=True)
        if not rows:
            return [_reply('No tickets yet. Send GAMES to find a match.', 'GAMES')]
        lines = []
        for kind, t in rows[:5]:
            odds = getattr(t, 'odds', None) or getattr(t, 'combined_odds', None)
            lines.append(f'{t.code or t.id} · {kind} · {_money(t.stake)} @ {_odds(odds)} · {t.get_status_display()}')
        return [_reply('🎟️ Your latest tickets:\n' + '\n'.join(lines), 'GAMES', 'BALANCE')]

    def book(self) -> list[dict]:
        from apps.sportsbook import booking
        legs = self.state['legs']
        if not legs:
            return [_reply('Your ticket is empty.', 'GAMES')]
        picks = [{'outcome_id': leg['outcome_id']} if leg['outcome_id']
                 else {'event_id': leg['event_id'], 'selection': leg['selection']} for leg in legs]
        try:
            code = booking.create_booking(picks, player_id=self.link.player_id if self.link else None)
        except ValueError as exc:
            return [_reply(f'⚠️ {exc}')]
        return [_reply(f'📌 Booking code {code.code}. Load it on the website, at a shop, or here with CODE {code.code}.')]

    def load_code(self, code: str) -> list[dict]:
        from apps.sportsbook import booking
        payload = booking.load_booking(code)
        if payload is None:
            return [_reply(f'No booking code {code}.')]
        legs, skipped = [], 0
        for leg in payload['legs']:
            if not leg['available'] or not leg['odds']:
                skipped += 1
                continue
            pick = (leg['selection'] and {'home': '1', 'draw': 'X', 'away': '2'}[leg['selection']]) if not leg['outcome_id'] else 'pick'
            legs.append({'match': leg['event_id'], 'pick': pick, 'event_id': None if leg['outcome_id'] else leg['event_id'],
                         'selection': None if leg['outcome_id'] else leg['selection'], 'outcome_id': leg['outcome_id'],
                         'label': f'{leg["event_name"]} – {leg["market_name"] + ": " + leg["outcome_label"] if leg["outcome_id"] else pick}',
                         'odds': leg['odds']})
        self.state['legs'] = legs[:MAX_LEGS]
        self.state.pop('pending', None)
        note = f'\n({skipped} pick{"" if skipped == 1 else "s"} no longer available)' if skipped else ''
        return [_reply(f'Loaded {code.upper()}.{note}\n\n{self._slip_text()}', 'SLIP')]

    def deposit(self, args: list[str]) -> list[dict]:
        if (r := self._need_link()) or (r := self._blocked()):
            return r
        if not self.cfg.allow_deposits:
            return [_reply('Deposits through WhatsApp are paused. Please deposit on the website.')]
        from apps.wallet import payments, paynow
        try:
            amount = Decimal(args[0].lstrip('$')).quantize(Decimal('0.01'))
            if amount <= 0:
                raise InvalidOperation
        except (IndexError, InvalidOperation):
            return [_reply('Send DEPOSIT and the amount, e.g. DEPOSIT 10 (EcoCash to this number), '
                           'or DEPOSIT 10 ONEMONEY 0712345678.')]
        method, phone = 'ecocash', self.address
        for w in args[1:]:
            if w in METHODS:
                method = METHODS[w]
            elif w.isdigit():
                phone = w
        if not payments.gateway_enabled():
            return [_reply('Deposits through WhatsApp need our mobile money gateway, which is off right now. '
                           'Please deposit on the website.')]
        player = self._player()
        if player.deposit_limit_daily is not None and amount > player.deposit_limit_daily:
            return [_reply(f'That is over your daily deposit limit of {_money(player.deposit_limit_daily)}.')]
        try:
            payments.check_deposit(method, amount)
            from apps.wallet import services as wallet_services
            txn = payments.start_deposit(player_id=player.id, amount=amount, method=method, phone=phone,
                                         currency=wallet_services.get_balance_dto(player.id).currency)
        except ValueError as exc:
            return [_reply(f'⚠️ {exc}')]
        except paynow.PaynowError as exc:
            return [_reply(f'⚠️ The payment could not be started: {exc}')]
        channel, address, ref = self.channel, self.address, txn.reference

        def run():
            try:
                from .tasks import report_deposit
                report_deposit.apply_async(args=(channel, address, ref), countdown=45, retry=False)
            except Exception:  # noqa: BLE001
                logger.warning('could not schedule chat deposit report', exc_info=True)
        transaction.on_commit(run)
        how = txn.instructions or f'Check your phone for the {method.title()} prompt and enter your PIN to approve.'
        return [_reply(f'📲 Deposit of {_money(amount)} started (ref {txn.reference}).\n{how}\n'
                       'We will message you when it is in your wallet.')]
