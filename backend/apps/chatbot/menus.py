"""The WhatsApp main menu and everything it opens that isn't browsing odds or
building a slip: my bets and cash-out, money (history, withdrawals), bonuses,
referrals, Aviator, help and the account.

Two levels, all tappable: MENU is one list of sections; each section is a list
of up to ten items. Every row's id is a command, so a tap reads like typing it
and every item also works typed (TODAY, OPEN, WITHDRAW 20 …). A bare number is
never a menu item: numbers are match IDs.

Each item calls the same service the website uses, so chat follows the same
rules (KYC, risk holds, fees, limits, cash-out offers) and never copies them.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.conf import settings
from django.utils import timezone

from . import services

ACTION_FOR = timedelta(minutes=2)       # how long a cash-out or withdrawal waits for CONFIRM

# (command, title, description) for the main menu, in order.
SECTIONS = (
    ('MENU BET', '⚽ Bet', 'Today, tomorrow, live, leagues, search'),
    ('MENU BETS', '🎟️ My bets', 'Open and settled tickets, cash out'),
    ('MENU MONEY', '💰 Money', 'Balance, deposit, withdraw, history'),
    ('MENU BONUS', '🎁 Bonuses & promos', 'Your bonus, offers, promo codes'),
    ('MENU REFER', '🤝 Refer & earn', 'Your referral link, agent dashboard'),
    ('MENU AVIATOR', '🎮 Aviator', 'Play on the website, latest results'),
    ('MENU HELP', '🛟 Help', 'Support, FAQ, rules, play safe'),
    ('MENU ACCOUNT', '👤 Account', 'Your details, notifications, unlink'),
)

ITEMS = {
    'BET': ('⚽ Bet', (
        ('TODAY', "📅 Today's matches", 'Every match still to play today'),
        ('TOMORROW', "📆 Tomorrow's matches", 'Every match tomorrow'),
        ('LIVE', '🔴 Live now', 'Matches trading in play'),
        ('TOP', '⭐ Top events', 'The leagues we feature'),
        ('LEAGUES', '🌍 Leagues', 'Pick a league'),
        ('GAMES', '⚽ All upcoming', 'Every upcoming match, page by page'),
        ('SEARCH', '🔎 Search', 'Find a team or league'),
        ('SLIP', '🧾 My slip', 'The ticket you are building'),
    )),
    'BETS': ('🎟️ My bets', (
        ('OPEN', '📋 Open tickets', 'Tickets still running'),
        ('SETTLED', '🏁 Settled tickets', 'Won, lost and void'),
        ('CASHOUT', '💸 Cash out', 'Take a ticket’s cash-out offer'),
        ('TICKETS', '🎟️ Latest tickets', 'Your five most recent'),
        ('BOOK', '📌 Booking code', 'Save your slip as a code'),
        ('CODE', '📥 Load a code', 'Load a booking code'),
    )),
    'MONEY': ('💰 Money', (
        ('BALANCE', '💰 Balance', 'Deposit, winnings and bonus'),
        ('DEPOSIT', '💳 Deposit', 'EcoCash, OneMoney, InnBucks'),
        ('WITHDRAW', '💵 Withdraw', 'To your mobile money, with your PIN'),
        ('WITHDRAWALS', '📤 My withdrawals', 'Requests and their status'),
        ('HISTORY', '📊 Transactions', 'Your last 10 money movements'),
    )),
    'BONUS': ('🎁 Bonuses & promos', (
        ('BONUSES', '🎁 My bonus', 'Locked bonus and wagering left'),
        ('OFFERS', '💯 Offers', 'Deposit bonuses and promotions'),
        ('PROMO', '🎟️ Promo code', 'Check a promo code'),
    )),
    'REFER': ('🤝 Refer & earn', (
        ('REFER', '👥 Refer a friend', 'Your link and referrals'),
        ('AGENT', '🏢 Agent dashboard', 'Earnings and payouts'),
    )),
    'AVIATOR': ('🎮 Aviator', (
        ('AVIATOR', '🎮 Play Aviator', 'Open it on the website'),
        ('CRASHES', '📈 Latest results', 'The last 10 rounds'),
    )),
    'HELP': ('🛟 Help', (
        ('SUPPORT', '💬 Talk to us', 'A person replies here'),
        ('FAQ', '❓ FAQ', 'Common questions'),
        ('RULES', '📜 Betting rules', 'Limits, odds and settlement'),
        ('SAFE', '🛡️ Play safe', 'Limits and taking a break'),
        ('WEBSITE', '🌐 Website', 'Open the website'),
    )),
    'ACCOUNT': ('👤 Account', (
        ('ACCOUNT', '👤 My account', 'Details and verification'),
        ('NOTIFICATIONS', '🔔 Notifications', 'Your latest messages'),
        ('STOP', '🔓 Unlink this number', 'Stop betting from WhatsApp'),
    )),
}


def site_url(path: str = '') -> str:
    return f'{str(getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")}{path}'


class MenuMixin:
    """Mixed into engine.Conversation (self.link, self.state, self.now, self.cfg)."""

    # -- the menu --------------------------------------------------------------------
    def menu(self) -> list[dict]:
        from . import engine
        site = engine._site()
        head = f'👋 *Welcome to {site}*\nBet on football from WhatsApp.'
        if not self.link:
            head += (f'\n\nTo bet, link your account: on the website open {engine.SITE_PATH}, '
                     'get a code and send *LINK 123456* here.')
        head += '\n\nTap *Menu* below, or type a match ID (e.g. *1234*) or a word like *TODAY* or *BALANCE*.'
        return [{'text': head, 'list': {'button': 'Menu', 'title': site[:24],
                                        'rows': [list(r) for r in SECTIONS]}}]

    def section(self, key: str) -> list[dict]:
        if key not in ITEMS:
            return self.menu()
        title, rows = ITEMS[key]
        return [{'text': f'*{title}*\n\nChoose below 👇', 'list': {
            'button': 'Choose', 'title': title.split(' ', 1)[-1][:24],
            'rows': [list(r) for r in rows] + [['MENU', '🏠 Main menu', '']]}}]

    # -- bet: today / tomorrow / top / search -------------------------------------------
    def search_prompt(self) -> list[dict]:
        from . import engine
        return [engine._reply('🔎 Send *GAMES* and a team or league, e.g. *GAMES dynamos* or *GAMES premier*.',
                              'TODAY', 'LEAGUES')]

    # -- my bets ---------------------------------------------------------------------------
    def _my_tickets(self, statuses, limit: int = 10) -> list:
        from apps.sportsbook.models import Bet, BetSlip
        pid = self.link.player_id
        rows = ([('bet', b) for b in Bet.objects.filter(player_id=pid, status__in=statuses).order_by('-placed_at')[:limit]]
                + [('slip', s) for s in BetSlip.objects.filter(player_id=pid, status__in=statuses).order_by('-placed_at')[:limit]])
        rows.sort(key=lambda r: r[1].placed_at, reverse=True)
        return rows[:limit]

    def _ticket_block(self, kind: str, t, extra: str = '') -> str:
        from . import engine
        odds = getattr(t, 'odds', None) or getattr(t, 'combined_odds', None)
        events = engine._ticket_events(t)
        n = len(events)
        what = 'Single' if kind == 'bet' else f'Multiple · {n} selections'
        first = events[0] if events else None
        match = f'#{first.id} {first.name}' if first else 'Match removed'
        more = f' + {n - 1} more' if n > 1 else ''
        return (f'*{t.code or t.id}* · {what}\n{match}{more}\n'
                f'{engine._money(t.stake)} @ {engine._odds(odds)} · {t.get_status_display()}{extra}')

    def open_tickets(self) -> list[dict]:
        from . import engine
        if r := self._need_link():
            return r
        rows = self._my_tickets(('open', 'accepting', 'pending'))
        if not rows:
            return [engine._reply('No open tickets. Send *TODAY* to find a match.', 'TODAY', 'MENU')]
        blocks = []
        for kind, t in rows:
            offer = self._offer(kind, t)
            cash = f'\n💸 Cash out now: *{engine._money(offer.value)}*' if offer and offer.available else ''
            blocks.append(self._ticket_block(kind, t, cash))
        return [engine._reply('📋 *Open tickets*\n\n' + '\n\n'.join(blocks), ['CASHOUT', '💸 Cash out'], 'SETTLED', 'MENU')]

    def settled_tickets(self) -> list[dict]:
        from . import engine
        if r := self._need_link():
            return r
        rows = self._my_tickets(('won', 'lost', 'void'))
        if not rows:
            return [engine._reply('No settled tickets yet.', 'OPEN', 'MENU')]
        icon = {'won': '🏆', 'lost': '❌', 'void': '↩️'}
        blocks = [f'{icon.get(t.status, "")} ' + self._ticket_block(
            kind, t, f'\nPaid {engine._money(t.payout)}' if t.status == 'won' and getattr(t, 'payout', None) else '')
            for kind, t in rows]
        won = sum(1 for _, t in rows if t.status == 'won')
        return [engine._reply(f'🏁 *Settled tickets* · {won} won of the last {len(rows)}\n\n' + '\n\n'.join(blocks),
                              'OPEN', 'MENU')]

    @staticmethod
    def _offer(kind: str, t):
        from apps.sportsbook import cashout
        try:
            return cashout.bet_offer(t) if kind == 'bet' else cashout.slip_offer(t)
        except Exception:  # noqa: BLE001 — an offer we can't price is simply not shown
            return None

    def cashout_list(self) -> list[dict]:
        from . import engine
        if (r := self._need_link()) or (r := self._blocked()):
            return r
        rows = []
        for kind, t in self._my_tickets(('open',), limit=30):
            offer = self._offer(kind, t)
            if offer and offer.available:
                rows.append([f'CASHOUT {kind[0].upper()} {t.id}', f'{engine._money(offer.value)} · {t.code or t.id}',
                             f'Staked {engine._money(t.stake)}'])
        if not rows:
            return [engine._reply('None of your open tickets can be cashed out right now.', 'OPEN', 'MENU')]
        return [{'text': f'💸 *Cash out*\n\n{len(rows)} ticket{"" if len(rows) == 1 else "s"} can be cashed out. '
                         'Tap one to see its offer.',
                 'list': {'button': 'Choose a ticket', 'title': 'Cash-out offers', 'rows': rows[:10]}}]

    def cashout_offer(self, kind_letter: str, ticket_id: int) -> list[dict]:
        from apps.sportsbook.models import Bet, BetSlip
        from . import engine
        if (r := self._need_link()) or (r := self._blocked()):
            return r
        kind = {'B': 'bet', 'S': 'slip'}.get(kind_letter)
        model = Bet if kind == 'bet' else BetSlip
        t = model.objects.filter(pk=ticket_id, player_id=self.link.player_id).first() if kind else None
        if t is None:
            return [engine._reply('That ticket is not yours or does not exist.', 'CASHOUT')]
        offer = self._offer(kind, t)
        if not offer or not offer.available:
            return [engine._reply(f'⚠️ {getattr(offer, "reason", "") or "No cash-out offer on this ticket right now."}', 'OPEN')]
        self._set_action({'type': 'cashout', 'kind': kind, 'id': t.id, 'value': str(offer.value)})
        return [engine._reply(f'💸 *Cash out {t.code or t.id}?*\n\n{self._ticket_block(kind, t)}\n\n'
                              f'You get *{engine._money(offer.value)}* into your Winnings now and the ticket closes.\n'
                              'Press Confirm within 2 minutes.', engine.CONFIRM, engine.CANCEL)]

    def _do_cashout(self, action: dict) -> list[dict]:
        from apps.sportsbook import cashout
        from . import engine
        try:
            cashout.cash_out(kind=action['kind'], ticket_id=action['id'], player_id=self.link.player_id,
                             expected=Decimal(action['value']))
        except cashout.CashoutChanged as exc:
            self._set_action({**action, 'value': str(exc.value)})
            return [engine._reply(f'⚠️ The offer changed to *{engine._money(exc.value)}*. Press Confirm to take it.',
                                  engine.CONFIRM, engine.CANCEL)]
        except (cashout.CashoutUnavailable, ValueError) as exc:
            return [engine._reply(f'⚠️ {exc}', 'OPEN')]
        from apps.accounts import services as accounts
        accounts.audit(self.link.player_id, 'chat_cashout', None, kind=action['kind'], ticket=action['id'], value=action['value'])
        return [engine._reply(f'✅ Cashed out *{engine._money(action["value"])}*. It is in your Winnings.', 'BALANCE', 'OPEN')]

    # -- confirmations for cash-out and withdrawals --------------------------------------------
    def _set_action(self, action: dict) -> None:
        self.state.pop('pending', None)                      # one thing waits for CONFIRM at a time
        self.state['action'] = {**action, 'expires': (self.now + ACTION_FOR).isoformat(), 'tries': 0}

    def confirm_action(self, pin: str) -> list[dict]:
        from . import engine
        action = self.state.get('action') or {}
        if timezone.datetime.fromisoformat(action['expires']) < self.now:
            self.state.pop('action', None)
            return [engine._reply('That confirmation expired. Start again from the menu.', 'MENU')]
        if action['type'] == 'withdraw':
            if not services.pin_ok(self.link, pin):
                action['tries'] = action.get('tries', 0) + 1
                if action['tries'] >= engine.PIN_TRIES:
                    self.state.pop('action', None)
                    from apps.accounts import services as accounts
                    accounts.audit(self.link.player_id, 'chat_withdraw_pin_failed', None)
                    return [engine._reply('Wrong PIN too many times. The withdrawal was cancelled.')]
                return [engine._reply('Wrong or missing PIN. Type *CONFIRM* and your PIN, e.g. CONFIRM 1234.', engine.CANCEL)]
            self.state.pop('action', None)
            return self._do_withdraw(action)
        self.state.pop('action', None)
        return self._do_cashout(action)

    # -- money ----------------------------------------------------------------------------------
    def history(self) -> list[dict]:
        from apps.wallet import services as wallet
        from . import engine
        if r := self._need_link():
            return r
        entries = wallet.list_entries(self.link.player_id, limit=10)
        if not entries:
            return [engine._reply('No transactions yet.', 'DEPOSIT', 'MENU')]
        tz = services.local_tz()
        lines = ['📊 *Your last transactions*', '']
        for e in entries:
            sign = '+' if e.amount > 0 else '−'
            what = e.kind.replace('_', ' ').capitalize()
            lines.append(f'{timezone.localtime(e.created_at, tz):%d %b %H:%M} · {what} · *{sign}{engine._money(abs(e.amount))}*'
                         + (f' ({e.bucket})' if e.bucket else ''))
        return [engine._reply('\n'.join(lines), 'BALANCE', 'MENU')]

    def withdrawals_list(self) -> list[dict]:
        from apps.wallet.models import WithdrawalRequest
        from . import engine
        if r := self._need_link():
            return r
        rows = WithdrawalRequest.objects.filter(player_id=self.link.player_id).order_by('-created_at')[:5]
        if not rows:
            return [engine._reply('No withdrawals yet.', 'WITHDRAW', 'MENU')]
        tz = services.local_tz()
        lines = ['📤 *Your withdrawals*', '']
        for w in rows:
            lines.append(f'{timezone.localtime(w.created_at, tz):%d %b %H:%M} · *{engine._money(w.amount)}* to '
                         f'{w.get_method_display()} ••{w.account_number[-4:]} · {w.get_status_display()}')
        return [engine._reply('\n'.join(lines), 'BALANCE', 'MENU')]

    def _withdraw_gate(self) -> Optional[str]:
        """Why this number can't withdraw from chat right now, or None."""
        if not self.cfg.allow_withdrawals:
            return f'Withdrawals through WhatsApp are switched off. Withdraw on the website: {site_url("/account/wallet")}'
        if not self.link.pin_hash:
            return ('Withdrawals from WhatsApp need your chat PIN. Set it on the website '
                    f'({site_url("/account/whatsapp")}), then try again.')
        ready = self.link.linked_at + timedelta(hours=self.cfg.withdraw_cooldown_hours)
        if ready > self.now:
            left = int((ready - self.now).total_seconds() // 3600) + 1
            return (f'For your safety, a newly linked number can withdraw after {self.cfg.withdraw_cooldown_hours} hours '
                    f'(about {left} hour{"" if left == 1 else "s"} from now). You can withdraw on the website meanwhile.')
        return None

    def withdraw(self, args: list[str]) -> list[dict]:
        from apps.wallet import withdrawals
        from apps.wallet.models import WithdrawalSettings
        from . import engine
        if r := self._need_link():
            return r
        if (why := self._withdraw_gate()):
            return [engine._reply(why, 'BALANCE', 'MENU')]
        pid = self.link.player_id
        cfg = WithdrawalSettings.load()
        destinations = services.withdraw_destinations(pid)
        available = withdrawals.withdrawable(pid, 'winnings')
        cap_left = max(self.cfg.withdraw_daily_cap - withdrawals.requested_today(pid, self.now), Decimal('0'))
        if not destinations:
            return [engine._reply('We can only send chat withdrawals to a mobile-money number you have deposited from, '
                                  f'and there is none yet. Withdraw on the website: {site_url("/account/wallet")}', 'MENU')]
        if not args:
            nums = '\n'.join(f'• {label} ••{phone[-4:]}' for _, phone, label in destinations)
            return [engine._reply(
                f'💵 *Withdraw*\n\nWinnings you can withdraw: *{engine._money(available)}*\n'
                f'From chat today: up to *{engine._money(cap_left)}* · fee {cfg.fee_percent:.0f}%\n'
                f'Minimum {engine._money(cfg.min_amount)}\n\nWe send it to a number you deposited from:\n{nums}\n\n'
                'Send *WITHDRAW* and the amount, e.g. *WITHDRAW 20*.', 'BALANCE', 'WITHDRAWALS')]
        try:
            amount = Decimal(args[0].lstrip('$')).quantize(Decimal('0.01'))
            if amount <= 0:
                raise InvalidOperation
        except InvalidOperation:
            return [engine._reply('Send WITHDRAW and the amount, e.g. WITHDRAW 20.')]
        if amount > cap_left:
            return [engine._reply(f'From WhatsApp you can withdraw up to {engine._money(self.cfg.withdraw_daily_cap)} a day '
                                  f'({engine._money(cap_left)} left today). For more, use the website.', 'MENU')]
        choice = None
        if len(args) >= 3 and args[1] == 'TO' and args[2].isdigit():
            n = int(args[2])
            choice = destinations[n - 1] if 1 <= n <= len(destinations) else None
        elif len(destinations) == 1:
            choice = destinations[0]
        if choice is None:
            rows = [[f'WITHDRAW {amount} TO {i}', f'{label} ••{phone[-4:]}', f'Send {engine._money(amount)} here']
                    for i, (_, phone, label) in enumerate(destinations, 1)]
            return [{'text': f'Where should we send *{engine._money(amount)}*?',
                     'list': {'button': 'Choose a number', 'title': 'Your numbers', 'rows': rows[:10]}}]
        try:
            q = withdrawals.quote(amount, 'winnings', cfg)
        except withdrawals.WithdrawalError as exc:
            return [engine._reply(f'⚠️ {exc}')]
        method, phone, label = choice
        self._set_action({'type': 'withdraw', 'amount': str(amount), 'method': method, 'phone': phone})
        return [engine._reply(
            f'💵 *Confirm your withdrawal*\n\nFrom: Winnings\nAmount: {engine._money(amount)}\n'
            f'Fee ({q["fee_percent"][:-3]}%): {engine._money(q["fee"])}\nYou receive: *{engine._money(q["payout_amount"])}*\n'
            f'To: {label} ••{phone[-4:]}\n\nType *CONFIRM* and your chat PIN, e.g. CONFIRM 1234, within 2 minutes.',
            engine.CANCEL)]

    def _do_withdraw(self, action: dict) -> list[dict]:
        from apps.wallet import withdrawals
        from . import engine
        if (why := self._withdraw_gate()):
            return [engine._reply(why)]
        amount = Decimal(action['amount'])
        pid = self.link.player_id
        # Re-check what may have changed in the two minutes: the destination and the daily cap.
        if (action['method'], action['phone']) not in {(m, p) for m, p, _ in services.withdraw_destinations(pid)}:
            return [engine._reply('That number can no longer receive withdrawals. Start again with WITHDRAW.')]
        if withdrawals.requested_today(pid, self.now) + amount > self.cfg.withdraw_daily_cap:
            return [engine._reply('That would pass today’s WhatsApp withdrawal limit. Use the website for more.')]
        player = self._player()
        try:
            req = withdrawals.request(player=player, amount=amount, method=action['method'],
                                      account_number=action['phone'], wallet='winnings', now=self.now)
        except withdrawals.WithdrawalError as exc:
            return [engine._reply(f'⚠️ {exc}', 'BALANCE')]
        from apps.accounts import services as accounts
        accounts.audit(pid, 'chat_withdrawal', None, withdrawal=req.id, amount=str(amount), to=f'…{action["phone"][-4:]}')
        held = ' It is being checked first; we will message you when it is sent.' if req.risk_hold else ''
        return [engine._reply(f'✅ Withdrawal requested: *{engine._money(amount)}* to ••{action["phone"][-4:]} '
                              f'(you receive {engine._money(req.payout_amount)}).{held}\n\n'
                              'You will be notified when it is paid. Not you? Reply SUPPORT now.',
                              'WITHDRAWALS', 'BALANCE')]

    # -- bonuses ----------------------------------------------------------------------------------
    def my_bonus(self) -> list[dict]:
        from apps.promotions import services as promos
        from apps.wallet import services as wallet
        from . import engine
        if r := self._need_link():
            return r
        st = promos.bonus_status(self.link.player_id)
        bal = wallet.get_balances(self.link.player_id).get('bonus', Decimal('0'))
        lines = ['🎁 *Your bonus*', '', f'Bonus wallet: *{engine._money(bal)}*']
        if st['locked'] > 0:
            lines.append(f'Locked by wagering: {engine._money(st["locked"])} · bet {engine._money(st["wagering_remaining"])} '
                         'more to unlock it')
        else:
            lines.append('Nothing locked by wagering.')
        return [engine._reply('\n'.join(lines), 'OFFERS', 'MENU')]

    def offers(self) -> list[dict]:
        from apps.promotions import services as promos
        from apps.promotions.models import Promotion
        from . import engine
        tiers = promos.live_deposit_bonuses()
        promos_ = list(Promotion.objects.filter(active=True).order_by('-id')[:5])
        if not tiers and not promos_:
            return [engine._reply('No offers are running right now. Check back soon!', 'MENU')]
        lines = ['💯 *Offers*']
        if tiers:
            lines += ['', '*Deposit bonuses*']
            for t in tiers:
                cap = f', up to {engine._money(t.max_bonus)}' if t.max_bonus else ''
                lines.append(f'• {t.name}: {t.percent:.0f}% on deposits from {engine._money(t.min_deposit)}{cap}')
        if promos_:
            lines += ['', '*Promotions*'] + [f'• {p.name}' for p in promos_]
        lines += ['', f'Details: {site_url("/promotions")}']
        return [engine._reply('\n'.join(lines), 'DEPOSIT', 'MENU')]

    def promo(self, args: list[str]) -> list[dict]:
        from apps.promotions import promo_codes
        from . import engine
        if not args:
            return [engine._reply('Send *PROMO* and the code, e.g. *PROMO WELCOME10*, to check it.')]
        if r := self._need_link():
            return r
        try:
            info = promo_codes.preview(args[0], player_id=self.link.player_id)
        except ValueError as exc:
            return [engine._reply(f'⚠️ {exc}', 'OFFERS')]
        desc = info.get('description') or info.get('summary') or ''
        return [engine._reply(f'✅ Code *{args[0].upper()}* is valid.{(" " + desc) if desc else ""}\n\n'
                              'Enter it with your deposit on the website to get the bonus.', 'DEPOSIT', 'MENU')]

    # -- refer & earn ------------------------------------------------------------------------------
    def refer(self) -> list[dict]:
        from apps.affiliates.models import Affiliate
        from . import engine
        if r := self._need_link():
            return r
        aff = Affiliate.objects.filter(player_id=self.link.player_id).first()
        if aff is None:
            return [engine._reply(f'👥 *Refer a friend*\n\nJoin our affiliate programme on the website to get your '
                                  f'own link and earn from players you bring: {site_url("/account/affiliate")}', 'MENU')]
        link = site_url(f'/?ref={aff.code}')
        return [engine._reply(f'👥 *Your referral link*\n\n{link}\n\nShare it: players who sign up with it are yours. '
                              f'Your earnings: {site_url("/account/affiliate")}', 'AGENT', 'MENU')]

    def agent(self) -> list[dict]:
        from . import engine
        return [engine._reply(f'🏢 *Agent dashboard*\n\nEarnings, locked balance, competitions and payouts are on the '
                              f'website: {site_url("/account/affiliate")}', 'REFER', 'MENU')]

    # -- Aviator ------------------------------------------------------------------------------------
    def aviator(self) -> list[dict]:
        from . import engine
        return [engine._reply(f'🎮 *Aviator* plays live, so it runs on the website:\n{site_url("/aviator")}',
                              ['CRASHES', '📈 Latest results'], 'MENU')]

    def crashes(self) -> list[dict]:
        from apps.jet.models import JetRound
        from . import engine
        points = list(JetRound.objects.filter(status=JetRound.Status.CRASHED).order_by('-id')
                      .values_list('crash_point', flat=True)[:10])
        if not points:
            return [engine._reply('No Aviator rounds yet.', 'AVIATOR')]
        return [engine._reply('📈 *Aviator: last 10 rounds* (newest first)\n\n' + '  '.join(f'*{p:.2f}x*' for p in points),
                              'AVIATOR', 'MENU')]

    # -- help ------------------------------------------------------------------------------------------
    def support(self, words: list[str]) -> list[dict]:
        from . import engine
        if words:
            return [engine._reply('💬 Thanks, your message is with our team. A person will reply here, '
                                  'usually within a few minutes in working hours.', 'MENU')]
        return [engine._reply('💬 *Talk to us*\n\nWrite *SUPPORT* followed by your question, e.g. '
                              '*SUPPORT my deposit has not arrived*. A person from our team replies here.', 'FAQ', 'MENU')]

    def faq(self) -> list[dict]:
        from . import engine
        qa = (
            ('How do I bet?', 'Send TODAY, open a match by its ID, tap a pick, then Place bet and Confirm.'),
            ('How do I link my account?', f'On the website open {engine.SITE_PATH}, get a code, send LINK and the code here.'),
            ('Is my money safe?', 'Bets, deposits and withdrawals follow the same rules as the website. Withdrawals need your PIN.'),
            ('Where are my winnings?', 'In your Winnings wallet as soon as a ticket is settled. Send BALANCE.'),
            ('A match is missing odds?', 'Prices close while a market is suspended; they come back when it reopens.'),
            ('Deposit not arrived?', 'Most arrive in a minute. If not, send SUPPORT with the amount and time.'),
        )
        return [engine._reply('❓ *FAQ*\n\n' + '\n\n'.join(f'*{q}*\n{a}' for q, a in qa), ['SUPPORT', '💬 Talk to us'], 'MENU')]

    def rules(self) -> list[dict]:
        from apps.wallet import services as wallet
        from . import engine
        limits = wallet.betting_limits()
        lines = ['📜 *Betting rules*', '',
                 f'• Most per ticket from WhatsApp: {engine._money(self.cfg.max_stake)}',
                 f'• WhatsApp limit per day: {engine._money(self.cfg.daily_cap)}',
                 f'• Up to {engine.MAX_LEGS} selections per ticket']
        for k, label in (('min_stake', 'Minimum stake'), ('max_stake', 'Maximum stake on the website')):
            if limits.get(k):
                lines.append(f'• {label}: {engine._money(limits[k])}')
        lines += ['• A price can change before you confirm: we always show the new one first',
                  '• In play, bets are accepted after a few seconds’ check', '',
                  f'Full terms: {site_url("/legal/terms")}']
        return [engine._reply('\n'.join(lines), 'SAFE', 'MENU')]

    def safe(self) -> list[dict]:
        from . import engine
        return [engine._reply(
            '🛡️ *Play safe*\n\n• Only bet what you can afford to lose.\n• Set a lower daily WhatsApp limit, a deposit '
            f'limit or take a break on the website: {site_url("/account/settings")}\n'
            f'• More help: {site_url("/legal/responsible-gambling")}\n\nBetting is for adults (18+) only.', 'MENU')]

    def website(self) -> list[dict]:
        from . import engine
        return [engine._reply(f'🌐 {site_url("/")}', 'MENU')]

    # -- account ----------------------------------------------------------------------------------------
    def account(self) -> list[dict]:
        from . import engine
        if r := self._need_link():
            return r
        p = self._player()
        if p is None:
            return [engine._reply('Your account could not be found. Send SUPPORT.')]
        kyc = {'verified': '✅ Verified'}.get(str(p.kyc_status), f'Not verified yet: {site_url("/account/verification")}')
        lines = ['👤 *My account*', '', f'Username: *{p.username}*', f'Identity: {kyc}',
                 f'WhatsApp: ••{self.link.address[-4:]} (linked {timezone.localtime(self.link.linked_at, services.local_tz()):%d %b %Y})',
                 f'Chat PIN: {"set ✅" if self.link.pin_hash else "not set"}',
                 f'Daily WhatsApp limit: {engine._money(services.daily_cap(self.link))}',
                 '', f'Change details on the website: {site_url("/account/profile")}']
        return [engine._reply('\n'.join(lines), 'NOTIFICATIONS', 'MENU')]

    def notifications(self) -> list[dict]:
        from apps.notifications.models import Notification
        from apps.notifications import services as notes
        from . import engine
        if r := self._need_link():
            return r
        rows = list(Notification.objects.filter(player_id=self.link.player_id).order_by('-created_at')[:5])
        if not rows:
            return [engine._reply('🔔 No notifications.', 'MENU')]
        tz = services.local_tz()
        blocks = [f'{"🆕 " if not n.read else ""}*{n.title}* · {timezone.localtime(n.created_at, tz):%d %b %H:%M}'
                  + (f'\n{n.body[:300]}' if n.body else '') for n in rows]
        notes.mark_all_read(self.link.player_id)
        return [engine._reply('🔔 *Notifications*\n\n' + '\n\n'.join(blocks), 'MENU')]
