"""The Aviator screens of the WhatsApp bot (mixed into engine.Conversation).

    AVIATOR              the game: last results, balance, free spins, pick a stake
    AV 1                 $1: pick where it cashes out
    AV 1 2               $1 cashing out at 2.00x: confirm (CONFIRM, with the PIN when one is needed)
    AV 1 2 10            the same for 10 rounds (autoplay, at most aviator.MAX_ROUNDS)
    AV FREE [2] [5]      free spins: claim them, then play at 2.00x (for 5 rounds)
    AV AGAIN             the last bet again
    CASH                 cash out now, at the multiplier the server sees as the message arrives
    AV STOP              stop autoplay (a bet still waiting for take-off is refunded)
    AV BETS / AV HELP    recent Aviator bets / how it works
"""
from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from . import aviator, services
from .models import AviatorOrder


class AviatorChatMixin:
    """Needs engine.Conversation's link, state, cfg, now, _need_link and _blocked."""

    def _game(self):
        from apps.jet.models import JetSettings
        return JetSettings.load()

    def aviator(self) -> list[dict]:
        return self.av([])

    def av(self, args: list[str]) -> list[dict]:
        from . import engine
        word = args[0] if args else ''
        if word in ('HELP', 'HOW', 'RULES'):
            return self._av_help()
        if word in ('RESULTS', 'CRASHES', 'HISTORY'):
            return self.crashes()
        if word == 'STOP':
            return self.av_stop()
        if (r := self._need_link()) or (r := self._blocked()):
            return r
        if not self.cfg.allow_aviator:
            return [engine._reply('✈️ Aviator on WhatsApp is paused right now.', 'MENU')]
        if not self._game().enabled:
            return [engine._reply('✈️ Aviator is paused right now. Try again soon.', 'MENU')]
        if word == 'BETS':
            return self._av_bets()
        if word == 'AGAIN':
            last = self.state.get('aviator_last')
            if not last:
                return self._av_home()
            return self._av_confirm(Decimal(last['stake']), Decimal(last['x']), last['rounds'], last['free'])
        free = word == 'FREE'
        nums = args[1:] if free else args
        if free:
            from apps.jet import free_spins
            free_spins.claim(self.link.player_id)
            if not aviator.free_spins(self.link.player_id, self.now):
                return [engine._reply('You have no free spins right now. Watch *OFFERS* for the next ones.', 'AVIATOR', 'MENU')]
        if not nums:
            return self._av_targets(None) if free else self._av_home()
        values = [aviator.parse_amount(n) for n in nums[:3]]
        if any(v is None for v in values):
            return [engine._reply('Send it like *AV 1 2*: stake $1, cash out at 2.00x. Add a number of rounds for '
                                  'autoplay: *AV 1 2 10*.', 'AVIATOR')]
        if free:
            x, rounds = values[0], int(values[1]) if len(values) > 1 else 1
            return self._av_confirm(Decimal('0'), x, rounds, True)
        if len(values) == 1:
            return self._av_targets(values[0])
        stake, x = values[0], values[1]
        rounds = int(values[2]) if len(values) > 2 else 1
        return self._av_confirm(stake, x, rounds, False)

    # -- screens --------------------------------------------------------------------------------
    def _av_home(self) -> list[dict]:
        from apps.jet.models import JetRound
        from . import engine
        game = self._game()
        points = list(JetRound.objects.filter(status=JetRound.Status.CRASHED).order_by('-id')
                      .values_list('crash_point', flat=True)[:8])
        spins = aviator.free_spins(self.link.player_id, self.now)
        from apps.jet import free_spins
        offered = sum(o['count'] for o in free_spins.offers_for(self.link.player_id))
        playing = AviatorOrder.objects.filter(status=AviatorOrder.Status.ACTIVE, player_id=self.link.player_id,
                                              address=self.address).first()
        lines = [f'✈️ *{game.display_name}*', '',
                 'Pick a stake and where it cashes out. The plane climbs; if it gets there before it flies away, '
                 'you win stake × that number. Results come here after each round, no data needed.', '']
        if points:
            lines.append('Last rounds: ' + '  '.join(f'*{p:.2f}x*' for p in points))
        lines.append(f'Balance: *{engine._money(aviator._balance(self.link.player_id))}*'
                     + (f' · 🎁 {spins + offered} free spin{"" if spins + offered == 1 else "s"}' if spins + offered else ''))
        if playing:
            lines.append(f'Playing: {engine._money(playing.stake)} at {aviator._x(playing.auto_cashout)}, round '
                         f'{playing.settled + 1} of {playing.rounds}. Send *AV STOP* to stop.')
        rows = [[f'AV {s}', f'Bet ${Decimal(s):.2f}', f'{engine._money(s)} per round'] for s in aviator.STAKES
                if game.min_bet <= Decimal(s) <= min(game.max_bet, self.cfg.max_stake)]
        if spins + offered:
            rows.insert(0, ['AV FREE', '🎁 Use a free spin', f'{spins + offered} waiting'])
        if self.state.get('aviator_last'):
            last = self.state['aviator_last']
            rows.insert(0, ['AV AGAIN', '🔁 Same again', (f'Free spin at {aviator._x(last["x"])}' if last['free'] else
                                                         f'${Decimal(last["stake"]):.2f} at {aviator._x(last["x"])}')
                            + (f' × {last["rounds"]} rounds' if last['rounds'] > 1 else '')])
        rows += [['AV BETS', '📋 My Aviator bets', 'Recent results'], ['AV HELP', '❓ How it works', 'Cash-out, autoplay, CASH']]
        lines += ['', f'Or type it: *AV 1 2* = {engine._money(1)} cashing out at 2.00x; *AV 1 2 10* = 10 rounds.']
        return [{'text': '\n'.join(lines), 'list': {'button': 'Play', 'title': 'Aviator', 'rows': rows[:10]}}]

    def _av_targets(self, stake) -> list[dict]:
        from . import engine
        free = stake is None
        rows = []
        for t in aviator.TARGETS:
            x = Decimal(t)
            win = '' if free else f' → wins {engine._money(stake * x)}'
            rows.append([f'AV FREE {t}' if free else f'AV {stake} {t}', f'Cash out at {x:.2f}x',
                         ('Free spin' if free else f'{engine._money(stake)}') + win])
        what = 'your free spin' if free else engine._money(stake)
        example = 'AV FREE 2.5' if free else f'AV {stake} 2.5'
        return [{'text': f'✈️ Where should {what} cash out?\n\nThe higher, the bigger the win and the less likely the '
                         f'plane gets there. Or type your own, e.g. *{example}*.',
                 'list': {'button': 'Cash out at', 'title': 'Auto cash-out', 'rows': rows}}]

    def _av_confirm(self, stake: Decimal, x: Decimal, rounds: int, free: bool) -> list[dict]:
        from . import engine
        game = self._game()
        if not Decimal('1.01') <= x <= game.max_multiplier:
            return [engine._reply(f'Cash out somewhere between 1.01x and {game.max_multiplier:.0f}x.', 'AVIATOR')]
        if not 1 <= rounds <= aviator.MAX_ROUNDS:
            return [engine._reply(f'Autoplay runs 1 to {aviator.MAX_ROUNDS} rounds.', 'AVIATOR')]
        if not free:
            if not game.min_bet <= stake <= game.max_bet:
                return [engine._reply(f'Aviator bets are {engine._money(game.min_bet)} to {engine._money(game.max_bet)}.', 'AVIATOR')]
            try:
                services.check_stake(self.link, stake)
                left = services.daily_cap(self.link) - services.staked_today(self.link.player_id, channel=self.channel)
                if stake * rounds > left:
                    raise services.ChatError(f'{rounds} rounds of {engine._money(stake)} would pass your daily chat limit: '
                                             f'you can still stake {engine._money(max(left, Decimal("0")))} today.')
            except services.ChatError as exc:
                return [engine._reply(str(exc), 'AVIATOR')]
            if aviator._balance(self.link.player_id) < stake:
                return [engine._reply('Not enough balance for that bet.', ['DEPOSIT', '💳 Deposit'], 'AVIATOR')]
        elif aviator.free_spins(self.link.player_id, self.now) < 1:
            return [engine._reply('You have no free spins right now.', 'AVIATOR')]
        from .menus import ACTION_FOR
        self.state['action'] = {'type': 'aviator', 'stake': str(stake), 'x': str(x), 'rounds': rounds, 'free': free,
                                'expires': (self.now + ACTION_FOR).isoformat(), 'tries': 0}
        pin = not free and services.needs_pin(self.link, stake * rounds)
        what = 'a free spin' if free else engine._money(stake)
        lines = [f'✈️ *Aviator*: {what} cashing out at *{aviator._x(x)}*'
                 + (f', *{rounds} rounds*' if rounds > 1 else ''),
                 'Wins ' + ('stake × ' if free else '') + (f'{engine._money(stake * x)}' if not free else f'{aviator._x(x)} (paid as bonus)')
                 + (' each round it gets there' if rounds > 1 else ' if the plane gets there') + '.']
        if not free:
            lines.append(f'Paid from Deposit, then Winnings. Total {engine._money(stake * rounds)}.' if rounds > 1
                         else 'Paid from Deposit, then Winnings.')
        lines.append('It joins the round taking bets now, or the next one.')
        lines.append('Type *CONFIRM* and your PIN, e.g. CONFIRM 1234.' if pin else 'Tap *Confirm* to fly.')
        return [engine._reply('\n'.join(lines), ['CONFIRM', '✅ Confirm'], engine.CANCEL)]

    def _do_aviator(self, action: dict, pin: str) -> list[dict]:
        """CONFIRM on an Aviator bet."""
        from . import engine
        stake, x, rounds, free = Decimal(action['stake']), Decimal(action['x']), int(action['rounds']), bool(action['free'])
        if not free and services.needs_pin(self.link, stake * rounds) and not services.pin_ok(self.link, pin):
            action['tries'] = action.get('tries', 0) + 1
            if action['tries'] >= engine.PIN_TRIES:
                self.state.pop('action', None)
                return [engine._reply('Wrong PIN too many times. The bet was cancelled.')]
            return [engine._reply('Wrong or missing PIN. Type *CONFIRM* and your PIN, e.g. CONFIRM 1234.', engine.CANCEL)]
        self.state.pop('action', None)
        if AviatorOrder.objects.filter(status=AviatorOrder.Status.ACTIVE, player_id=self.link.player_id,
                                       address=self.address).exists():
            return [engine._reply('You already have Aviator playing. Send *AV STOP* first to change it.', ['AV STOP', '⏹ Stop'])]
        order = AviatorOrder.objects.create(channel=self.channel, address=self.address, player_id=self.link.player_id,
                                            stake=stake, auto_cashout=x, free=free, rounds=rounds)
        self.state['aviator_last'] = {'stake': str(stake), 'x': str(x), 'rounds': rounds, 'free': free}
        try:
            bet = aviator.start(order, now=self.now)
        except aviator.StopOrder as exc:
            order.status, order.note = AviatorOrder.Status.STOPPED, str(exc)[:200]
            order.save(update_fields=['status', 'note', 'updated_at'])
            return [engine._reply(f'⚠️ {exc}', ['DEPOSIT', '💳 Deposit'], 'AVIATOR')]
        what = 'Free spin' if free else engine._money(stake)
        if bet is not None:
            secs = max(0, int((bet.round.betting_ends_at - timezone.now()).total_seconds()))
            head = f'✅ *You’re in round {bet.round_id}!* Take-off in about {secs}s.'
        else:
            head = '✅ *Bet booked:* it joins the next round in a few seconds.'
        auto = f'\nAutoplay: {rounds} rounds. Send *AV STOP* to stop.' if rounds > 1 else ''
        return [engine._reply(f'{head}\n{what} cashes out at *{aviator._x(x)}*. The result comes here.\n'
                              f'Send *CASH* while it flies to cash out early.{auto}', ['CASH', '💰 CASH OUT'], 'AVIATOR')]

    def cash(self) -> list[dict]:
        from . import engine
        if r := self._need_link():
            return r
        out = aviator.cash_now(self.link.player_id, self.address, self.channel)
        if not out:
            return [engine._reply('You have no Aviator bet in the air right now.', 'AVIATOR')]
        return [engine._reply('\n'.join(out), ['AV AGAIN', '🔁 Play again'], 'AVIATOR')]

    def av_stop(self) -> list[dict]:
        from . import engine
        if not self.link:
            return [engine._reply('Nothing to stop.', 'AVIATOR')]
        stopped, refunded = aviator.stop(self.link.player_id, self.address, self.channel)
        if not stopped:
            return [engine._reply('No Aviator autoplay is running.', 'AVIATOR', 'MENU')]
        extra = ' Your bet waiting for take-off was refunded.' if refunded else ' A bet already in the air still finishes.'
        return [engine._reply(f'⏹ Aviator stopped.{extra}', 'AVIATOR', 'MENU')]

    def _av_bets(self) -> list[dict]:
        from apps.jet.models import JetBet
        from . import engine
        bets = list(JetBet.objects.filter(player_id=self.link.player_id).select_related('round').order_by('-id')[:10])
        if not bets:
            return [engine._reply('No Aviator bets yet. Send *AVIATOR* to play.', 'AVIATOR')]
        lines = ['📋 *Your last Aviator bets*', '']
        for b in bets:
            what = 'Free' if b.is_free else engine._money(b.stake)
            if b.status == JetBet.Status.CASHED:
                res = f'✅ {aviator._x(b.cashout_multiplier)} → *{engine._money(b.payout)}*'
            elif b.status == JetBet.Status.LOST:
                res = f'💥 lost (flew at {aviator._x(b.round.crash_point)})'
            elif b.status == JetBet.Status.REFUNDED:
                res = '↩️ refunded'
            else:
                res = '✈️ in play'
            lines.append(f'#{b.round_id} · {what}' + (f' @ {aviator._x(b.auto_cashout)}' if b.auto_cashout else '') + f' · {res}')
        return [engine._reply('\n'.join(lines), 'AVIATOR', 'MENU')]

    def _av_help(self) -> list[dict]:
        from . import engine
        return [engine._reply(
            '❓ *Aviator on WhatsApp*\n\n'
            '1. Pick a stake and a cash-out (e.g. 2.00x). Confirm.\n'
            '2. Your bet joins the next round. The plane climbs: 1.00x, 1.50x, 2.00x…\n'
            '3. If it reaches your cash-out before it flies away, you win stake × cash-out. If not, the stake is lost.\n'
            '4. The result comes here after each round.\n\n'
            '*CASH* while it flies: cashes out at the multiplier when your message reaches us.\n'
            '*AV 1 2 10*: autoplay, the same bet for 10 rounds. *AV STOP* stops it.\n'
            '*AV FREE*: play your free spins. *AV BETS*: your results.\n\n'
            'The server decides every round fairly from its own clock, the same as on the website.',
            'AVIATOR', 'MENU')]
