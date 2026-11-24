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
PAGE_SIZE = 8          # matches per GAMES / LIVE page
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
BACK = ['BACK', '⬅️ Back']
RETURN = ['RETURN', '⬅️ Back']        # after a mistake: where they were, not a level up
NAV_DEPTH = 12
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


def kickoff(e) -> str:
    """Kick-off date and time, always shown with a match on a ticket, e.g.
    '🕒 Sat 22 Nov 2026, 18:00' (plus the live clock once it's under way)."""
    from apps.sportsbook import services as sb
    if e is None:
        return '🕒 Kick-off time not known'
    when = (timezone.localtime(e.starts_at, services.local_tz()).strftime('%a %d %b %Y, %H:%M') if e.starts_at
            else 'time to be confirmed')
    live = (f' · LIVE {e.elapsed or 0}\' {e.score_home or 0}-{e.score_away or 0}'
            if e.status in sb.IN_PLAY_STATUSES else '')
    return f'🕒 {when}{live}'


def _ticket_events(t) -> list:
    """The matches on a placed ticket (single or multiple), in leg order."""
    if hasattr(t, 'legs'):
        legs = t.legs.select_related('event_ref', 'outcome_ref__market__event').order_by('id')
        return [leg.event_ref or (leg.outcome_ref.market.event if leg.outcome_ref else None) for leg in legs]
    return [t.event_ref or (t.outcome_ref.market.event if t.outcome_ref else None)]


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


# Commands that open a screen (worth coming back to). Actions (a pick, BET, CONFIRM,
# LOGIN…) are not screens: BACK and a mistake return to the screen they were sent from.
SCREENS = {
    'MENU', 'HI', 'HELLO', 'HELP', 'START', 'GAMES', 'TODAY', 'TOMORROW', 'MATCHES', 'FOOTBALL', 'TOP', 'LIVE',
    'LEAGUES', 'LEAGUE', 'COUNTRIES', 'COUNTRY', 'SEARCH', 'FIND', 'SLIP', 'OPEN', 'SETTLED', 'TICKETS', 'MYBETS', 'BETS',
    'BALANCE', 'BAL', 'HISTORY', 'TRANSACTIONS', 'WITHDRAWALS', 'BONUS', 'BONUSES', 'OFFERS', 'PROMOTIONS', 'REFER',
    'AGENT', 'AVIATOR', 'CRASHES', 'FAQ', 'RULES', 'SAFE', 'WEBSITE', 'ACCOUNT', 'NOTIFICATIONS', 'ALERTS',
}


def _is_screen(words: list[str]) -> bool:
    if not words:
        return False
    head, rest = words[0], words[1:]
    if head == 'CASHOUT':
        return not rest                                  # the list, not "CASHOUT B 12"
    if head.isdigit():                                   # a match, its markets, a group or a market
        return not rest or rest[0] in ('M', 'MARKETS', 'ODDS', 'ALL', 'G', 'K')
    return head in SCREENS


def _count(legs: list) -> str:
    """'3 matches', or '2 matches (3 picks)': a slip counts matches, not picks."""
    m, p = len({leg['match'] for leg in legs}), len(legs)
    return f'{m} match{"" if m == 1 else "es"}' + (f' ({p} picks)' if p > m else '')


def _with_back(rows: list, room: int = 10) -> list:
    """A list's rows plus a Back row, when WhatsApp's ten-row limit leaves room."""
    return rows + [['BACK', '⬅️ Back', 'Up one level']] if len(rows) < room else rows


def _looks_like_error(reply: dict) -> bool:
    t = reply.get('text') or ''
    return t.startswith(('⚠️', '“')) or any(p in t for p in (
        'is not a pick', 'There is no match', 'does not exist', 'not available', 'Send WITHDRAW and', 'Send BET and',
        'No league matching', 'No country matching', 'No upcoming matches for'))

from .menus import MenuMixin  # noqa: E402
from .signin import SignInMixin  # noqa: E402  (menus reads this module's helpers at call time)

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


class Conversation(MenuMixin, SignInMixin):
    def __init__(self, channel, address, link: Optional[ChatLink], session: ChatSession, now, cfg):
        self.channel, self.address, self.link, self.session, self.now, self.cfg = channel, address, link, session, now, cfg
        self.state = session.state if isinstance(session.state, dict) else {}
        session.state = self.state
        self.state.setdefault('legs', [])
        self.idle_logout = False
        self._session_tick()

    # -- logged in or not ------------------------------------------------------------
    def _session_tick(self) -> None:
        """Every message: log out after `session_minutes` without one, else keep the session alive."""
        auth = self.state.get('auth')
        if not auth:
            return
        if not self.link or auth.get('player') != self.link.player_id:
            self._logout()
            return
        seen = timezone.datetime.fromisoformat(auth['seen'])
        if self.now - seen > timedelta(minutes=self.cfg.session_minutes):
            self._logout()
            self.idle_logout = True
            return
        auth['seen'] = self.now.isoformat()

    def _logout(self) -> None:
        self.state.pop('auth', None)
        self.state.pop('pending', None)                  # nothing half-confirmed survives a logout
        self.state.pop('action', None)

    @property
    def logged_in(self) -> bool:
        return bool(self.link and self.state.get('auth'))

    def _start_session(self) -> None:
        now = self.now.isoformat()
        self.state['auth'] = {'player': self.link.player_id, 'at': now, 'seen': now}

    def logout(self) -> list[dict]:
        if not self.logged_in:
            return [_reply('You are not logged in.', 'MENU')]
        self._logout()
        return [_reply('🔒 Logged out. Send *LOGIN* and your PIN to log in again.', 'MENU')]

    # -- routing --------------------------------------------------------------------
    # -- where the player is: BACK, and getting lost ------------------------------------
    def dispatch(self, text: str) -> list[dict]:
        """Answer one message, remembering the screens the player opened so BACK goes up a
        level and a message the bot doesn't understand shows where they were instead of a dead end."""
        self._lost = False
        answered = self.in_flow(text)                           # a log-in or sign-up question is waiting
        if answered is not None:
            return answered
        words = text.upper().split()
        if words in (['BACK'], ['UP']):
            return self.back()
        if words == ['RETURN']:                                 # after a mistake: the screen they were on
            nav = self.state.get('nav') or []
            return self._route(nav[-1]) if nav else self.menu()
        replies = self._route(text)
        if self._lost:
            return self._where_you_were()
        if _is_screen(words):
            self._remember(' '.join(text.split()))
        elif replies and _looks_like_error(replies[-1]) and len(replies[-1].get('buttons') or []) < 3:
            replies[-1] = {**replies[-1], 'buttons': list(replies[-1].get('buttons') or []) + [RETURN]}
        return replies

    def _remember(self, cmd: str) -> None:
        nav = self.state.setdefault('nav', [])
        key = cmd.upper()
        if key in ('MENU', 'HI', 'HELLO', 'HELP', 'START'):
            nav[:] = ['MENU']                                   # the main menu is the top: start again from it
            return
        if nav and nav[-1].upper() == key:
            return
        if key in (n.upper() for n in nav):                     # going back to a screen already in the trail
            while nav and nav[-1].upper() != key:
                nav.pop()
            return
        nav.append(cmd)
        del nav[:-NAV_DEPTH]

    def back(self) -> list[dict]:
        nav = self.state.setdefault('nav', [])
        if nav:
            nav.pop()                                           # leave the screen they are on
        if not nav:
            return self.menu()
        return self._route(nav[-1])

    def _where_you_were(self) -> list[dict]:
        nav = self.state.get('nav') or []
        note = "🤔 Sorry, I didn't get that."
        if not nav or nav[-1].upper() == 'MENU':
            replies = self.menu()
            note += ' Tap *Menu* below, or type a match ID or a word like *TODAY*.'
        else:
            replies = self._route(nav[-1])
            note += ' Here is where you were. Send *BACK* to go up a level or *MENU* for the main menu.'
        first = replies[0]
        return [{**first, 'text': f'{note}\n\n{first["text"]}'}] + replies[1:]

    def _route(self, text: str) -> list[dict]:
        words = text.upper().replace(',', ' , ').split()
        if not words:
            return self.menu()
        head, rest = words[0], [w for w in words[1:] if w != ',']
        simple = {
            'HI': self.menu, 'HELLO': self.menu, 'MENU': self.menu, 'HELP': self.menu, 'START': self.menu,
            'LIVE': self.live, 'SLIP': self.slip, 'LOGOUT': self.logout, 'SIGNOUT': self.logout, 'CLEAR': self.clear, 'NO': self.cancel, 'CANCEL': self.cancel,
            'BALANCE': self.balance, 'BAL': self.balance, 'TICKETS': self.tickets, 'MYBETS': self.tickets,
            'BETS': self.tickets, 'BOOK': self.book, 'STOP': self.stop, 'UNLINK': self.stop,
            'STAKE': self.stake_prompt, 'PLACE': self.stake_prompt, 'BET': self.stake_prompt,
            'TODAY': lambda: self.games('', day=0), 'TOMORROW': lambda: self.games('', day=1),
            'TOP': lambda: self.games('', top=True), 'SEARCH': self.search_prompt, 'FIND': self.search_prompt,
            'OPEN': self.open_tickets, 'SETTLED': self.settled_tickets, 'CASHOUT': self.cashout_list,
            'HISTORY': self.history, 'TRANSACTIONS': self.history, 'WITHDRAWALS': self.withdrawals_list,
            'BONUS': self.my_bonus, 'BONUSES': self.my_bonus, 'OFFERS': self.offers, 'PROMOTIONS': self.offers,
            'REFER': self.refer, 'AGENT': self.agent, 'AVIATOR': self.aviator, 'CRASHES': self.crashes,
            'FAQ': self.faq, 'RULES': self.rules, 'SAFE': self.safe, 'WEBSITE': self.website,
            'ACCOUNT': self.account, 'NOTIFICATIONS': self.notifications, 'ALERTS': self.notifications,
            'CODE': lambda: [_reply('Send *CODE* and the booking code, e.g. *CODE AB12CD*.')],
        }
        if head in simple and not rest:
            return simple[head]()
        if head in ('LOGIN', 'SIGNIN'):
            return self.login(text.split()[1:])                 # as typed: passwords are case-sensitive
        if head in ('REGISTER', 'SIGNUP', 'JOIN') and not rest:
            return self.register()
        if head == 'MENU' and rest:
            return self.section(rest[0])
        if head == 'CASHOUT' and len(rest) >= 2 and rest[1].isdigit():
            return self.cashout_offer(rest[0], int(rest[1]))
        if head == 'WITHDRAW':
            return self.withdraw(rest)
        if head == 'PROMO':
            return self.promo(rest)
        if head == 'SUPPORT':
            return self.support(rest)
        if head in ('NEXT', 'MORE') and not rest:
            return self.turn_page(1)
        if head in ('PREV', 'PREVIOUS') and not rest:
            return self.turn_page(-1)
        if head == 'LEAGUES':
            return self.leagues(int(rest[0]) - 1 if rest and rest[0].isdigit() else 0)
        if head == 'LEAGUE' and rest and rest[0].isdigit() and len(rest) == 1:
            return self.games('', league=int(rest[0]))
        if head == 'LEAGUE':
            return self.find_league(' '.join(text.split()[1:]))
        if head == 'COUNTRY':
            return self.find_country(' '.join(text.split()[1:]))
        if head == 'COUNTRIES':
            return self.countries(int(rest[0]) - 1 if rest and rest[0].isdigit() else 0)
        if head == 'PICK' and rest and rest[0].isdigit():
            return self.pick_outcome(int(rest[0]))
        if head == 'LIVE' and rest and rest[0].isdigit():
            return self.live(page=int(rest[0]) - 1)
        if head.isdigit() and rest and rest[0] in ('M', 'MARKETS', 'ODDS', 'ALL'):
            return self.all_markets(int(head), int(rest[1]) - 1 if len(rest) > 1 and rest[1].isdigit() else 0)
        if head.isdigit() and len(rest) >= 2 and rest[0] == 'G':
            return self.group(int(head), rest[1].lower(), int(rest[2]) - 1 if len(rest) > 2 and rest[2].isdigit() else 0)
        if head.isdigit() and len(rest) >= 2 and rest[0] == 'K' and rest[1].isdigit():
            return self.market(int(head), int(rest[1]), int(rest[2]) - 1 if len(rest) > 2 and rest[2].isdigit() else 0)
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
        self._lost = True
        return []

    # -- help / linking -------------------------------------------------------------
    def link_account(self, code: str) -> list[dict]:
        if not code.isdigit():
            return [_reply(f'Send LINK and the 6-digit code from the website ({SITE_PATH}), e.g. LINK 123456.')]
        try:
            self.link = services.link(self.address, code, channel=self.channel)
        except services.ChatError as exc:
            return [_reply(str(exc))]
        from apps.accounts.models import Player
        name = Player.objects.filter(pk=self.link.player_id).values_list('username', flat=True).first() or ''
        self._start_session()
        return [_reply(f'✅ Linked to {name}. You can now bet from WhatsApp. Send GAMES to start.', *MENU_BUTTONS)]

    def stop(self) -> list[dict]:
        if not self.link:
            return [_reply('This number is not linked to an account.')]
        services.unlink(self.link.player_id, channel=self.channel, by='chat')
        self.state.clear()
        self.state['legs'] = []
        return [_reply('This number is unlinked. Nothing more can be placed from it until you link it again.')]

    def _need_link(self) -> Optional[list[dict]]:
        """Anything private (balance, bets, money, account) needs a linked number
        and, when the operator requires it, a logged-in session."""
        if self.link and (not self.cfg.require_login or self.logged_in):
            return None
        why = (f'🔒 You were logged out after {self.cfg.session_minutes} minutes without activity.\n\n'
               if self.idle_logout else '🔒 ')
        return [_reply(f'{why}Log in with your {_site()} website username and password: send *LOGIN*.\n'
                       'New here? Send *REGISTER* to create an account.', ['LOGIN', '🔓 Log in'], ['REGISTER', '📝 Register'])]

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
    # Every match and every playable price is reachable: lists come in pages
    # (NEXT / PREV), LEAGUES narrows them, and a match opens onto all its markets
    # by group. What's shown as playable is exactly what placement accepts
    # (sportsbook.services.outcome_unavailable).

    def _price_row(self, e) -> str:
        """`1 2.10 · X 3.20 · 2 3.40`: the main prices, when they're open."""
        prices = [f'{c} {_odds(v)}' for c, v in self._main(e)]
        return f'`{" · ".join(prices)}`' if prices else ''

    def _main(self, e) -> list[tuple[str, Decimal]]:
        """The playable 1X2 prices (the event's own main market)."""
        from apps.sportsbook import services as sb
        state = sb.trading_state(e)
        if not state['main_open']:
            return []
        blocked = set(state.get('main_blocked') or [])
        return [(code, price) for code, sel, price in (('1', 'home', e.odds), ('X', 'draw', e.odds_draw), ('2', 'away', e.odds_away))
                if price is not None and price > 1 and sel not in blocked]

    def _entry(self, e, *, live: bool = False) -> str:
        home, away = _teams(e)
        if live:
            head = f'*{e.id}* · 🔴 {e.elapsed or 0}\' · {home} *{e.score_home or 0}-{e.score_away or 0}* {away}'
        else:
            when = timezone.localtime(e.starts_at, services.local_tz()).strftime('%H:%M') if e.starts_at else 'TBC'
            head = f'*{e.id}* · {when} · {home} v {away}'
        row = self._price_row(e)
        more = getattr(e, 'open_markets', 0) or 0
        tail = ' · '.join(x for x in (row, f'+{more} market{"" if more == 1 else "s"}' if more else '') if x)
        return head + (f'\n{tail}' if tail else '')

    def _upcoming(self, *, query: str = '', league: Optional[int] = None, day: Optional[int] = None, top: bool = False):
        from django.db.models import Count, F, Q
        from apps.sportsbook.models import Event
        qs = Event.objects.filter(is_open=True, has_odds=True).filter(Q(starts_at__gt=self.now) | Q(starts_at__isnull=True))
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(league__name__icontains=query) | Q(league__country__icontains=query)
                           | Q(home_team__name__icontains=query) | Q(away_team__name__icontains=query))
        if league:
            qs = qs.filter(league_id=league)
        if top:
            qs = qs.filter(league__top_events=True)
        if day is not None:
            tz = services.local_tz()
            start = timezone.localtime(self.now, tz).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=day)
            qs = qs.filter(starts_at__gte=start, starts_at__lt=start + timedelta(days=1))
        return (qs.select_related('league', 'home_team', 'away_team')
                .annotate(open_markets=Count('markets', filter=Q(markets__is_open=True, markets__settled=False), distinct=True))
                .order_by(F('starts_at').asc(nulls_last=True), 'name', 'id'))

    def _live_events(self) -> list:
        from django.db.models import Count, Q
        from apps.sportsbook import services as sb
        from apps.sportsbook.models import Event
        qs = (Event.objects.filter(status__in=sb.IN_PLAY_STATUSES, is_open=True)
              .select_related('league', 'home_team', 'away_team')
              .annotate(open_markets=Count('markets', filter=Q(markets__is_open=True, markets__settled=False), distinct=True))
              .order_by('starts_at', 'id'))
        return [e for e in qs[:300] if sb.in_play_bettable(e, now=self.now)]

    def _page_buttons(self, page: int, pages: int, extra) -> list:
        nav = ([['PREV', '◀ Previous']] if page > 0 else []) + ([['NEXT', 'Next ▶']] if page + 1 < pages else [])
        return (nav + [b for b in extra if b])[:3]

    def _names(self) -> tuple[set, set, set]:
        """(team, league, country) names that have upcoming matches: what a search can mean."""
        rows = self._upcoming().order_by().values_list('home_team__name', 'away_team__name', 'league__name', 'league__country')
        teams, leagues, countries = set(), set(), set()
        for home, away, league, country in rows:
            teams.update(x for x in (home, away) if x)
            if league:
                leagues.add(league)
            if country:
                countries.add(country)
        return teams, leagues, countries

    def games(self, query: str, *, page: int = 0, league: Optional[int] = None, day: Optional[int] = None,
              top: bool = False, note: str = '') -> list[dict]:
        q = query.strip()
        qs = self._upcoming(query=q, league=league, day=day, top=top)
        total = qs.count()
        if not total and q and not note:
            # Nothing has that spelling: try what they probably meant ("arsnal" → "Arsenal").
            from . import search
            teams, leagues, countries = self._names()
            guess = search.best(q, teams | leagues | countries, limit=1)
            if guess:
                return self.games(guess[0], page=page, league=league, day=day, top=top,
                                  note=f'🔎 Showing results for “{guess[0]}” (you typed “{q}”)')
        if not total:
            what = (f' for “{q}”' if q else ' today' if day == 0 else ' tomorrow' if day == 1
                    else ' in the top events' if top else '')
            return [_reply(f'No upcoming matches{what} right now.', 'GAMES' if (day is not None or top) else 'LIVE',
                           'LEAGUES', 'MENU')]
        pages = -(-total // PAGE_SIZE)
        page = max(0, min(page, pages - 1))
        events = list(qs[page * PAGE_SIZE:(page + 1) * PAGE_SIZE])
        self.state['browse'] = {'kind': 'games', 'q': q, 'league': league, 'day': day, 'top': top, 'page': page}
        title = ((events[0].league.name if league and events[0].league_id else q)
                 or {0: "Today's matches", 1: "Tomorrow's matches"}.get(day) or ('Top events' if top else 'Upcoming matches'))
        lines = ([note, ''] if note else []) + [f'⚽ *{title}* · {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + len(events)} of {total}']
        day = group = None
        tz = services.local_tz()
        for e in events:
            d = timezone.localtime(e.starts_at, tz).strftime('%a %d %b') if e.starts_at else 'Date to be confirmed'
            if d != day:
                lines += ['', f'📅 *{d}*']
                day, group = d, None
            lg = e.league.name if e.league_id else ''
            if lg and lg != group and not league:
                lines.append(f'🏆 _{lg}_')
                group = lg
            lines.append(self._entry(e))
        lines += ['', f'Send a match ID for all its odds, e.g. *{events[0].id}*.']
        return [_reply('\n'.join(lines), *self._page_buttons(page, pages, ['LEAGUES', VIEW_SLIP]))]

    def live(self, *, page: int = 0) -> list[dict]:
        events = self._live_events()
        if not events:
            return [_reply('No matches are trading in play right now.', 'GAMES', 'MENU')]
        pages = -(-len(events) // PAGE_SIZE)
        page = max(0, min(page, pages - 1))
        chunk = events[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
        self.state['browse'] = {'kind': 'live', 'page': page}
        lines = [f'🔴 *In play now* · {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + len(chunk)} of {len(events)}', '']
        group = None
        for e in chunk:
            lg = e.league.name if e.league_id else ''
            if lg and lg != group:
                lines.append(f'🏆 _{lg}_')
                group = lg
            lines.append(self._entry(e, live=True))
        lines += ['', 'Send a match ID for its live odds.']
        return [_reply('\n'.join(lines), *self._page_buttons(page, pages, ['GAMES', VIEW_SLIP]))]

    def turn_page(self, step: int) -> list[dict]:
        b = self.state.get('browse') or {}
        page = int(b.get('page') or 0) + step
        if b.get('kind') == 'live':
            return self.live(page=page)
        if b.get('kind') == 'games':
            return self.games(b.get('q') or '', page=page, league=b.get('league'), day=b.get('day'), top=bool(b.get('top')))
        if b.get('kind') == 'leagues':
            return self.leagues(page, country=b.get('country'))
        if b.get('kind') == 'countries':
            return self.countries(page)
        if b.get('kind') == 'market':
            return self.market(b['match'], b['market'], page)
        return self.games('', page=max(page, 0))

    def _league_rows(self, country: Optional[str] = None) -> list[dict]:
        from django.db.models import Count
        qs = self._upcoming().order_by()
        if country is not None:
            qs = qs.filter(league__country=country)
        return list(qs.values('league_id', 'league__name', 'league__country', 'league__top_events', 'league__sort_order')
                    .annotate(n=Count('id', distinct=True)).filter(league_id__isnull=False)
                    .order_by('-league__top_events', 'league__sort_order', 'league__name'))

    def leagues(self, page: int = 0, *, country: Optional[str] = None, note: str = '') -> list[dict]:
        rows = self._league_rows(country)
        if not rows:
            return [_reply('No upcoming matches right now.', 'LIVE', 'MENU')]
        if country is not None and len(rows) == 1:          # one league in that country: straight to its matches
            return self.games('', league=rows[0]['league_id'], note=note)
        per = LIST_SIZE - 1
        pages = -(-len(rows) // per)
        page = max(0, min(page, pages - 1))
        chunk = rows[page * per:(page + 1) * per]
        self.state['browse'] = {'kind': 'leagues', 'page': page, 'country': country}
        options = [[f'LEAGUE {r["league_id"]}', r['league__name'],
                    f'{r["n"]} match{"" if r["n"] == 1 else "es"}' + (f' · {r["league__country"]}' if r['league__country'] and not country else '')]
                   for r in chunk]
        if page + 1 < pages:
            options.append([f'COUNTRY {country} {page + 2}' if country else f'LEAGUES {page + 2}', 'More leagues ▶',
                            f'Page {page + 2} of {pages}'])
        total = sum(r['n'] for r in rows)
        where = f' in {country}' if country else ''
        return [{'text': (f'{note}\n\n' if note else '') + f'🏆 *Leagues{where}* · {len(rows)} with {total} upcoming matches'
                         '\n\nTap a league to see its matches.',
                 'list': {'button': 'Choose a league', 'title': f'Leagues {page + 1}/{pages}', 'rows': options}}]

    def countries(self, page: int = 0) -> list[dict]:
        from django.db.models import Count
        rows = list(self._upcoming().order_by().exclude(league__country='').filter(league__isnull=False)
                    .values('league__country').annotate(n=Count('id', distinct=True)).order_by('league__country'))
        if not rows:
            return [_reply('No upcoming matches right now.', 'LIVE', 'MENU')]
        per = LIST_SIZE - 1
        pages = -(-len(rows) // per)
        page = max(0, min(page, pages - 1))
        self.state['browse'] = {'kind': 'countries', 'page': page}
        options = [[f'COUNTRY {r["league__country"]}', r['league__country'], f'{r["n"]} match{"" if r["n"] == 1 else "es"}']
                   for r in rows[page * per:(page + 1) * per]]
        if page + 1 < pages:
            options.append([f'COUNTRIES {page + 2}', 'More countries ▶', f'Page {page + 2} of {pages}'])
        return [{'text': f'🗺️ *Countries* · {len(rows)} with upcoming matches\n\nTap a country, or type e.g. *COUNTRY spain*.',
                 'list': {'button': 'Choose a country', 'title': f'Countries {page + 1}/{pages}', 'rows': options}}]

    def find_country(self, text: str) -> list[dict]:
        from . import search
        words = text.split()
        page = 0
        if len(words) > 1 and words[-1].isdigit():
            page, text = int(words[-1]) - 1, ' '.join(words[:-1])
        if not text.strip():
            return self.countries()
        _, _, names = self._names()
        exact = [c for c in names if search.norm(c) == search.norm(text)]
        found = exact or search.best(text, names, limit=1)
        if not found:
            return [_reply(f'No country matching “{text}” has upcoming matches. Tap below to see them all.', 'COUNTRIES', 'MENU')]
        note = '' if exact else f'🔎 Showing {found[0]} (you typed “{text}”)'
        return self.leagues(page, country=found[0], note=note)

    def find_league(self, text: str) -> list[dict]:
        from . import search
        rows = self._league_rows()
        if not text.strip():
            return self.leagues()
        names = {r['league__name'] for r in rows if r['league__name']}
        q = search.norm(text)
        hits = [n for n in names if q and q in search.norm(n)]
        note = ''
        if not hits:
            hits = search.best(text, names, limit=9)
            note = f'🔎 Showing leagues like “{text}”' if hits else ''
        if not hits:
            return [_reply(f'No league matching “{text}” has upcoming matches.', 'LEAGUES', 'COUNTRIES')]
        chosen = [r for r in rows if r['league__name'] in hits]
        if len(chosen) == 1:
            return self.games('', league=chosen[0]['league_id'], note=note.replace('leagues like', 'results for') if note else '')
        rank = {n: i for i, n in enumerate(hits)}
        chosen.sort(key=lambda r: rank.get(r['league__name'], 99))
        options = [[f'LEAGUE {r["league_id"]}', r['league__name'],
                    f'{r["n"]} match{"" if r["n"] == 1 else "es"}' + (f' · {r["league__country"]}' if r['league__country'] else '')]
                   for r in chosen[:LIST_SIZE]]
        return [{'text': (f'{note}\n\n' if note else '') + f'🏆 {len(chosen)} leagues match “{text}”. Tap one.',
                 'list': {'button': 'Choose a league', 'title': 'Leagues', 'rows': options}}]

    # -- one match: quick picks, then every market by group ---------------------------

    def _event(self, event_id: int):
        from apps.sportsbook.models import Event
        return Event.objects.select_related('league', 'home_team', 'away_team').filter(pk=event_id).first()

    def _playable(self, e) -> list[tuple]:
        """[(market, [outcomes])] that can be backed right now, in the website's
        order (by group, then the market's own order)."""
        from apps.sportsbook import services as sb
        from apps.sportsbook.models import Market
        in_play = sb._started(e)
        event_ok = sb.in_play_bettable(e, now=self.now) if in_play else e.is_open
        if not event_ok:
            return []
        rank = {g: i for i, g in enumerate(Market.Group.values)}
        out = []
        for m in Market.objects.filter(event=e, is_open=True, settled=False).prefetch_related('outcomes'):
            outs = [o for o in m.outcomes.all()
                    if sb.outcome_unavailable(e, m, o, in_play=in_play, event_ok=event_ok) is None]
            if outs:
                out.append((m, outs))
        out.sort(key=lambda mo: (rank.get(mo[0].group, len(rank)), mo[0].sort_order,
                                 mo[0].line if mo[0].line is not None else Decimal('0'), mo[0].id))
        return out

    def _quick(self, e, playable=None) -> list[tuple[str, Decimal]]:
        """(pick code, price) for every typeable shortcut open on the match."""
        out = list(self._main(e))
        for m, outs in (self._playable(e) if playable is None else playable):
            if m.period != 'ft' or m.metric != 'goals':
                continue
            for o in outs:
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

    def _head(self, e) -> str:
        home, away = _teams(e)
        league = f'🏆 {e.league.name}\n' if e.league_id else ''
        return f'*#{e.id} {home} v {away}*\n{league}{kickoff(e)}'

    def _closed(self, e, event_id: int) -> Optional[list[dict]]:
        from apps.sportsbook import services as sb
        if e is None:
            return [_reply(f'There is no match #{event_id}. Send GAMES for the list.', 'GAMES')]
        if not sb.trading_state(e)['bettable']:
            return [_reply(f'#{e.id} {e.name} is not taking bets right now.', 'GAMES', 'LIVE')]
        return None

    def _groups(self, playable) -> list[tuple[str, str, int]]:
        """[(group key, label, playable markets)] in display order."""
        from apps.sportsbook.models import Market
        labels = dict(Market.Group.choices)
        counts: dict[str, int] = {}
        for m, _ in playable:
            counts[m.group] = counts.get(m.group, 0) + 1
        return [(g, labels.get(g, g.title()), n) for g, n in counts.items()]

    def match(self, event_id: int) -> list[dict]:
        e = self._event(event_id)
        if (r := self._closed(e, event_id)):
            return r
        playable = self._playable(e)
        main = self._main(e)
        if not main and not playable:
            return [_reply(f'#{e.id} {e.name}: no odds are open right now. Try again shortly.', 'GAMES')]
        home, away = _teams(e)
        lines = [self._head(e)]
        if main:
            lines += ['', '*Match result*'] + [f'{c} · {describe(e, c)[1]} — *{_odds(p)}*' for c, p in main]
        quick = [(c, p) for c, p in self._quick(e, playable) if c not in ('1', 'X', '2')]
        sections = (('Double chance', ('1X', '12', 'X2')), ('Both teams to score', ('GG', 'NG')))
        have = dict(quick)
        for title, codes in sections:
            got = [(c, have[c]) for c in codes if c in have]
            if got:
                lines += ['', f'*{title}*'] + [f'{c} · {describe(e, c)[1]} — *{_odds(p)}*' for c, p in got]
        totals = sorted({c[1:] for c, _ in quick if c[0] in 'OU'}, key=Decimal)
        if totals:
            lines += ['', '*Total goals*']
            for line in totals:
                o, u = have.get(f'O{line}'), have.get(f'U{line}')
                lines.append(' · '.join(x for x in (o and f'O{line} *{_odds(o)}*', u and f'U{line} *{_odds(u)}*') if x))
        groups = self._groups(playable)
        n_markets = len(playable)
        lines += ['', f'📊 *{n_markets} market{"" if n_markets == 1 else "s"}* open: tap “All odds” for every price.' if n_markets else '',
                  f'Type a pick to add it, e.g. *{e.id} {(main or quick or [("1", 0)])[0][0]}*.']
        rows = [[f'{e.id} {c}', f'{c} · {_odds(p)}', f'Match result: {describe(e, c)[1]}'] for c, p in main]
        group_rows = [[f'{e.id} G {g}', label, f'{n} market{"" if n == 1 else "s"}'] for g, label, n in groups]
        room = LIST_SIZE - len(rows)
        if len(group_rows) > room:
            group_rows = group_rows[:room - 1] + [[f'{e.id} M', 'More markets ▶', f'{len(groups)} groups in all']]
        return [{'text': '\n'.join(x for x in lines if x is not None).replace('\n\n\n', '\n\n'),
                 'prompt': f'#{e.id} {home} v {away}: tap “All odds” 👇',
                 'list': {'button': 'All odds', 'sections': [
                     {'title': 'Match result', 'rows': rows},
                     {'title': 'Markets', 'rows': _with_back(group_rows, room=LIST_SIZE - len(rows))}]}}]

    def all_markets(self, event_id: int, page: int = 0) -> list[dict]:
        e = self._event(event_id)
        if (r := self._closed(e, event_id)):
            return r
        groups = self._groups(self._playable(e))
        if not groups:
            return [_reply(f'#{e.id}: no markets are open right now.', f'{e.id}', 'GAMES')]
        per = LIST_SIZE - 1
        pages = -(-len(groups) // per)
        page = max(0, min(page, pages - 1))
        rows = [[f'{e.id} G {g}', label, f'{n} market{"" if n == 1 else "s"}'] for g, label, n in groups[page * per:(page + 1) * per]]
        if page + 1 < pages:
            rows.append([f'{e.id} M {page + 2}', 'More ▶', f'Page {page + 2} of {pages}'])
        return [{'text': f'{self._head(e)}\n\nChoose a group of markets.',
                 'list': {'button': 'Choose', 'title': 'Market groups', 'rows': _with_back(rows)}}]

    @staticmethod
    def _outcome_line(o) -> str:
        return f'{o.label} *{_odds(o.odds)}*'

    def group(self, event_id: int, group: str, page: int = 0) -> list[dict]:
        from apps.sportsbook.models import Market
        e = self._event(event_id)
        if (r := self._closed(e, event_id)):
            return r
        markets = [(m, outs) for m, outs in self._playable(e) if m.group == group]
        label = dict(Market.Group.choices).get(group, group.title())
        if not markets:
            return [_reply(f'#{e.id}: no {label.lower()} markets are open right now.', f'{e.id}', 'GAMES')]
        if len(markets) == 1:
            return self.market(e.id, markets[0][0].id)
        lines = [self._head(e), '', f'📊 *{label}*']
        for m, outs in markets:
            lines += ['', f'*{m.name}*', ' · '.join(self._outcome_line(o) for o in outs)]
        n_out = sum(len(outs) for _, outs in markets)
        per = LIST_SIZE - 1
        if n_out <= LIST_SIZE:
            rows = [[f'PICK {o.id}', f'{_odds(o.odds)} · {o.label}', m.name] for m, outs in markets for o in outs]
        else:
            pages = -(-len(markets) // per)
            page = max(0, min(page, pages - 1))
            rows = [[f'{e.id} K {m.id}', m.name, f'{len(outs)} options'] for m, outs in markets[page * per:(page + 1) * per]]
            if page + 1 < pages:
                rows.append([f'{e.id} G {group} {page + 2}', 'More ▶', f'Page {page + 2} of {pages}'])
        return [{'text': '\n'.join(lines), 'prompt': f'#{e.id} · {label}: tap to choose 👇',
                 'list': {'button': 'Choose', 'title': label, 'rows': _with_back(rows)}}]

    def market(self, event_id: int, market_id: int, page: int = 0) -> list[dict]:
        e = self._event(event_id)
        if (r := self._closed(e, event_id)):
            return r
        found = next(((m, outs) for m, outs in self._playable(e) if m.id == market_id), None)
        if found is None:
            return [_reply(f'That market on #{e.id} is not open right now.', f'{e.id}', 'GAMES')]
        m, outs = found
        per = LIST_SIZE - 1
        pages = -(-len(outs) // per) if len(outs) > LIST_SIZE else 1
        page = max(0, min(page, pages - 1))
        self.state['browse'] = {'kind': 'market', 'match': e.id, 'market': m.id, 'page': page}
        lines = [self._head(e), '', f'📊 *{m.name}*'] + [f'• {self._outcome_line(o)}' for o in outs]
        chunk = outs if pages == 1 else outs[page * per:(page + 1) * per]
        rows = [[f'PICK {o.id}', f'{_odds(o.odds)} · {o.label}', m.name] for o in chunk]
        if page + 1 < pages:
            rows.append([f'{e.id} K {m.id} {page + 2}', 'More ▶', f'Page {page + 2} of {pages}'])
        return [{'text': '\n'.join(lines), 'prompt': f'#{e.id} · {m.name}: tap to choose 👇',
                 'list': {'button': 'Choose', 'title': m.name, 'rows': _with_back(rows)}}]

    def pick_outcome(self, outcome_id: int) -> list[dict]:
        """Add any market's outcome (what a tap on an odds list sends)."""
        from apps.sportsbook import services as sb
        from apps.sportsbook.models import MarketOutcome
        o = MarketOutcome.objects.select_related('market__event').filter(pk=outcome_id).first()
        if o is None:
            return [_reply('That selection no longer exists. Send GAMES for the list.', 'GAMES')]
        m, e = o.market, o.market.event
        reason = sb.outcome_unavailable(e, m, o)
        if reason:
            return [_reply(f'⚠️ {reason}', f'{e.id}', VIEW_SLIP)]
        code = self._code_for(m, o) if (m.period == 'ft' and m.metric == 'goals') else ''
        leg = {'match': e.id, 'pick': code or f'#{o.id}', 'event_id': None, 'selection': None, 'outcome_id': o.id,
               'event': e.name, 'market': m.name, 'pick_text': o.label, 'kickoff': kickoff(e),
               'label': f'{e.name} – {m.name}: {o.label}', 'odds': str(o.odds)}
        return self._add_legs([leg], [])

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
            o = m.outcomes.filter(key=key).first()
            if o is not None and sb.outcome_unavailable(e, m, o) is None:
                return self._leg(e, code, o.odds, outcome_id=o.id)
        raise services.ChatError(f'#{e.id} {code} is not available right now.')

    def _leg(self, e, code: str, price, *, event_id=None, selection=None, outcome_id=None) -> dict:
        market, pick = describe(e, code)
        return {'match': e.id, 'pick': code, 'event_id': event_id, 'selection': selection, 'outcome_id': outcome_id,
                'event': e.name, 'market': market, 'pick_text': pick,
                'kickoff': kickoff(e),
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
        found, problems = [], []
        for event_id, code in pairs:
            e = Event.objects.filter(pk=event_id).first()
            if e is None:
                problems.append(f'#{event_id} does not exist')
                continue
            try:
                found.append(self._resolve(e, code))
            except services.ChatError as exc:
                problems.append(str(exc))
        return self._add_legs(found, problems)

    def _add_legs(self, found: list[dict], problems: list[str]) -> list[dict]:
        """Put legs on the slip (replacing the same pick) and confirm each one."""
        added = []
        legs = self.state['legs']
        for leg in found:
            legs[:] = [x for x in legs if not ((x['match'] == leg['match'] and x['pick'] == leg['pick'])
                                               or (leg['outcome_id'] and x.get('outcome_id') == leg['outcome_id']))]
            if leg['match'] not in {x['match'] for x in legs} and len({x['match'] for x in legs}) >= MAX_LEGS:
                problems.append(f'a slip holds at most {MAX_LEGS} picks')
                break
            legs.append(leg)
            added.append(leg)
        self.state.pop('pending', None)
        out = []
        for leg in added:
            code = '' if leg['pick'].startswith('#') else f' ({leg["pick"]})'
            out.append(f'✅ *Selection added*\n#{leg["match"]} {leg["event"]}\n{leg["kickoff"]}'
                       f'\n{leg["market"]}: *{leg["pick_text"]}*{code}\nOdds *{_odds(leg["odds"])}*')
        if problems:
            out.append('⚠️ ' + '; '.join(problems))
        if legs:
            out.append(f'🧾 Your ticket: {_count(legs)} · total odds *{_odds(self._total())}*')
        return [_reply('\n\n'.join(out), ADD_MORE, VIEW_SLIP, PLACE_BET if legs else None)]

    def _priced(self, legs: Optional[list] = None) -> dict:
        """The slip as the sportsbook prices it: one price per match (picks from one
        match priced together, correlation-aware), each pick's short name, the total."""
        from apps.sportsbook import services as sb
        legs = self.state['legs'] if legs is None else legs
        if len({leg['match'] for leg in legs}) == len(legs):         # one pick per match: plain product
            total = Decimal('1')
            for leg in legs:
                total *= Decimal(leg['odds'])
            return {'total': total.quantize(Decimal('0.01')), 'match_odds': {}, 'names': []}
        payload = [{'outcome_id': leg['outcome_id'], 'odds': leg['odds']} if leg.get('outcome_id')
                   else {'event_id': leg['event_id'], 'selection': leg['selection'], 'odds': leg['odds']} for leg in legs]
        checked = sb.check_accumulator(payload)
        return {'total': Decimal(checked['combined_odds']),
                'match_odds': {m['event_id']: Decimal(m['odds']) for m in checked.get('matches', []) if m['event_id']},
                'names': checked.get('names') or []}

    def _total(self) -> Decimal:
        return self._priced()['total']

    def _slip_text(self) -> str:
        legs = self.state['legs']
        if not legs:
            return 'Your ticket is empty. Send GAMES, open a match and tap a pick (or type e.g. 1234 1).'
        return ('🧾 Your ticket:\n' + self._selections() + f'\nTotal odds {_odds(self._total())}'
                + '\n\nPress Place bet (or type BET 5). REMOVE 1234 takes a match off, CLEAR empties it.')

    def _selections(self, legs: Optional[list] = None) -> str:
        """One entry per match, with its kick-off date and time: its pick and price, or
        several picks from it joined ("Liverpool Win & BTTS YES") at their one price."""
        from apps.sportsbook.models import Event
        legs = self.state['legs'] if legs is None else legs
        events = Event.objects.in_bulk({leg['match'] for leg in legs})
        priced = self._priced(legs)
        groups: dict = {}
        for i, leg in enumerate(legs):
            groups.setdefault(leg['match'], []).append(i)
        out = []
        for n, (match, idxs) in enumerate(groups.items(), 1):
            first = legs[idxs[0]]
            head = f'{n}) #{match} {first.get("event") or first["label"]}\n    {kickoff(events.get(match))}\n'
            if len(idxs) == 1:
                out.append(head + f'    {first.get("market", "Pick")}: {first.get("pick_text") or first["pick"]} @ {_odds(first["odds"])}')
                continue
            names = [(priced['names'][i] if i < len(priced['names']) and priced['names'][i] else legs[i].get('pick_text') or legs[i]['pick'])
                     for i in idxs]
            price = priced['match_odds'].get(match)
            out.append(head + f'    🔗 Same match: *{" & ".join(names)}* @ {_odds(price) if price else "—"}')
        return '\n'.join(out)

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
        return [_reply(f'🧾 {_count(legs)} · total odds {_odds(self._total())}\n\n'
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
        self.state.pop('action', None)
        self.state['pending'] = {'stake': str(stake), 'wallet': wallet, 'odds': [leg['odds'] for leg in legs],
                                 'expires': (self.now + CONFIRM_FOR).isoformat(), 'pin_tries': 0}
        pin = services.needs_pin(self.link, stake)
        kind = 'Single' if len(legs) == 1 else f'Multiple · {_count(legs)}'
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
        if self.state.pop('action', None):
            return [_reply('Cancelled.', 'MENU')]
        had = self.state.pop('pending', None)
        return [_reply('Cancelled. Your selections are kept.' if had else 'Nothing to cancel.', VIEW_SLIP)]

    def confirm(self, pin: str) -> list[dict]:
        if (r := self._need_link()) or (r := self._blocked()):
            return r
        if self.state.get('action'):
            return self.confirm_action(pin)
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
        selections = self._selections(legs)
        self.state['legs'] = []
        self.state.pop('pending', None)
        live = ' · 🔴 *LIVE BET*' if getattr(ticket, 'in_play', False) else ''
        text = (f'🎟️ Ticket {ticket.code or ticket.id} placed{live}\n\n{selections}\n\n'
                f'Stake {_money(stake)} · total odds {_odds(odds)} · possible win {_money(stake * odds)}')
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
        blocks = []
        for kind, t in rows[:5]:
            odds = getattr(t, 'odds', None) or getattr(t, 'combined_odds', None)
            matches = '\n'.join(f'   • {f"#{e.id} {e.name}" if e else "Match removed"}\n     {kickoff(e)}'
                                for e in _ticket_events(t))
            live = ' · 🔴 LIVE BET' if getattr(t, 'in_play', False) else ''
            blocks.append(f'{t.code or t.id} · {kind}{live} · {_money(t.stake)} @ {_odds(odds)} · {t.get_status_display()}\n{matches}')
        return [_reply('🎟️ Your latest tickets:\n\n' + '\n\n'.join(blocks), 'GAMES', 'BALANCE')]

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
