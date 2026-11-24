"""The WhatsApp AI assistant: answers what the menu can't, with Google Gemini.

What it knows comes from the live settings (knowledge()), read fresh for every
answer: stakes, wallets and fees, bonus rules, promotions, cashback, refunds,
payment methods, Aviator, responsible gambling, plus staff's own notes
(ChatbotSettings.ai_knowledge). Change a rule in admin and the assistant knows.

What it may do: explain and guide. It never places bets or moves money (the
menu commands do, with their own checks), never asks for or repeats a password
or PIN, gives no betting tips, and talks only about BetBlits. It answers as
JSON {"reply", "handoff", "reason"}: handoff=true (money missing, account
changes, complaints, anything it isn't sure of) opens a SupportRequest so a
person replies in the inbox.

A logged-in player's own account summary (balances, recent deposits,
withdrawals and tickets) is included so it can answer "where is my deposit?";
never their phone number, password or PIN. Calls run on a background thread
(services.deliver), so WhatsApp gets its 200 at once; each number may ask
ai_daily_limit questions a day.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.core.cache import cache
from django.utils import timezone

from . import config, services
from .models import ChatbotSettings, InboundMessage, OutboundMessage, SupportRequest

logger = logging.getLogger(__name__)
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
HISTORY = 10
UNAVAILABLE = ('Sorry, I can’t answer right now. I’ve passed your message to our team and a person will reply here. '
               'Meanwhile, send *MENU* to bet, check your balance or deposit.')


def enabled(cfg: Optional[ChatbotSettings] = None) -> bool:
    cfg = cfg or ChatbotSettings.load()
    return bool(cfg.ai_enabled and config.value('gemini_api_key', cfg))


def _m(v) -> str:
    return f'${Decimal(v):.2f}'


def knowledge() -> str:
    """What the assistant knows about the site, from the settings in force right now."""
    from apps.branding.models import SiteIdentity
    from apps.promotions.models import CashbackSettings, CashbackTier, LossRefundSettings, Promotion
    from apps.promotions import services as promos
    from apps.wallet.models import PaymentMethod, WalletRules, WithdrawalSettings
    from .menus import site_url
    site = SiteIdentity.load()
    rules, wd = WalletRules.load(), WithdrawalSettings.load()
    chat = ChatbotSettings.load()
    lines = [
        f'SITE: {site.site_name} ({site_url("/") or "betblits.com"}). {site.tagline}'.strip(),
        'Sports betting on football (pre-match and live/in-play) and the Aviator crash game. Players must be 18+.',
        '',
        'ACCOUNT: register on the website with a username, email, password and an agent code (from an agent). '
        'Identity verification (KYC) is needed before withdrawing: Account → Verification.',
        'WALLETS: Deposit (money paid in), Winnings (won money; withdrawable), Bonus (promotion money; must be played first).',
        f'BETTING: stake {_m(rules.min_stake)} to {_m(rules.max_stake)} per ticket, up to {rules.max_selections} matches per ticket. '
        f'Minimum ticket odds: {rules.deposit_min_odds} from the Deposit wallet, {rules.bonus_min_odds} from Bonus. '
        'Singles or multiples (accumulators). Several picks from the same match (e.g. Win & BTTS) combine into one entry at one '
        'price that accounts for how they move together.',
        f'BONUS WALLET: sports only, a multiple of at least {rules.bonus_min_legs} selections each at least {rules.bonus_min_leg_odds}; '
        f'win {rules.bonus_wins_to_convert} bonus tickets in a row and the bonus moves to Winnings (up to {_m(rules.bonus_max_conversion)}). '
        f'Unused bonus expires after {rules.bonus_expiry_hours} hours.',
        f'WITHDRAWALS: from Winnings, fee {wd.fee_percent.normalize():f}%; from Deposit, fee {wd.deposit_fee_percent.normalize():f}%. '
        f'Minimum {_m(wd.min_amount)}, maximum {_m(wd.max_amount)} at once, {_m(wd.daily_max)} a day. Staff pay them; the player is notified.',
    ]
    methods = [m.name for m in PaymentMethod.objects.filter(deposit_enabled=True)]
    if methods:
        lines.append(f'DEPOSITS: {", ".join(methods)}. On WhatsApp: DEPOSIT 10 ECOCASH. Most arrive within a minute.')
    tiers = promos.live_deposit_bonuses()
    if tiers:
        lines.append('DEPOSIT BONUSES: ' + '; '.join(f'{t.name}: {t.percent.normalize():f}% from {_m(t.min_deposit)}'
                                                     + (f' (max {_m(t.max_bonus)})' if t.max_bonus else '') for t in tiers))
    offers = list(Promotion.objects.filter(active=True, deleted_at__isnull=True).exclude(code__startswith='SYS-')
                  .exclude(code__startswith='deposit-bonus:').values_list('name', flat=True)[:8])
    if offers:
        lines.append('PROMOTIONS: ' + '; '.join(offers))
    r = LossRefundSettings.load()
    if r.enabled:
        lines.append(f'LOST BY ONE REFUND: a multiple with odds above {r.min_odds.normalize():f} that lost on exactly one match gets back '
                     f'stake × ticket odds ÷ {r.divisor.normalize():f} ÷ the lost match’s odds, to Winnings, once all its matches finish'
                     + (f' (at most {_m(r.max_refund)})' if r.max_refund is not None else '') + '. Not for Bonus-wallet tickets.')
    cb = CashbackSettings.load()
    active_tiers = list(CashbackTier.objects.filter(active=True))
    if cb.enabled and active_tiers:
        lines.append(f'CASHBACK: every {cb.period_days} days, ' + '; '.join(
            f'lose {_m(t.min_loss)}+ with {t.min_tickets}+ tickets on {t.min_active_days}+ days → {t.percent.normalize():f}% back'
            + (f' (max {_m(t.max_amount)})' if t.max_amount is not None else '') for t in active_tiers) + '. Paid to Winnings.')
    lines += [
        'AVIATOR: a plane flies and the multiplier rises; cash out before it flies away. Free spins from promotions are claimed on '
        'the Aviator page. It runs on the website, not in WhatsApp.',
        f'WHATSAPP BOT: LOGIN (website username + password), REGISTER, MENU, TODAY, LIVE, LEAGUES, COUNTRY <name>, a match ID '
        f'to see its odds, then tap picks, BET <stake> and CONFIRM. BALANCE, OPEN, CASHOUT, DEPOSIT, WITHDRAW, HISTORY. '
        f'Most per ticket from WhatsApp {_m(chat.max_stake)}, {_m(chat.daily_cap)} a day. Logged out after '
        f'{chat.session_minutes} minutes idle.'
        + (' Withdrawals from WhatsApp need the chat PIN set on the website and only go to a number used for deposits.'
           if chat.allow_withdrawals else ' Withdrawals are done on the website.'),
        'RESPONSIBLE GAMBLING: deposit limits, a lower WhatsApp limit and self-exclusion are in Account → Settings on the website.',
    ]
    if site.support_email:
        lines.append(f'CONTACT: {site.support_email}')
    if chat.ai_knowledge.strip():
        lines += ['', 'NOTES FROM STAFF:', chat.ai_knowledge.strip()[:4000]]
    return '\n'.join(lines)


def account_summary(player_id: int) -> str:
    """The logged-in player's own account, for "where is my deposit?" questions."""
    from apps.accounts.models import Player
    from apps.sportsbook.models import Bet, BetSlip
    from apps.wallet import services as wallet
    from apps.wallet.models import PaymentTransaction, WithdrawalRequest
    p = Player.objects.filter(pk=player_id).first()
    if p is None:
        return ''
    b = wallet.get_balances(player_id)
    deps = PaymentTransaction.objects.filter(player_id=player_id).order_by('-id')[:3]
    wds = WithdrawalRequest.objects.filter(player_id=player_id).order_by('-id')[:3]
    open_n = (Bet.objects.filter(player_id=player_id, status__in=('open', 'accepting')).count()
              + BetSlip.objects.filter(player_id=player_id, status__in=('open', 'accepting')).count())
    fmt = '%d %b %H:%M'
    return '\n'.join([
        f'PLAYER: {p.username}, identity {p.kyc_status}.',
        f'BALANCES: Deposit {_m(b["deposit"])}, Winnings {_m(b["winnings"])}, Bonus {_m(b["bonus"])}.',
        'RECENT DEPOSITS: ' + ('; '.join(f'{_m(d.amount)} {d.method} {d.status} {timezone.localtime(d.created_at):{fmt}}'
                                         for d in deps) or 'none'),
        'RECENT WITHDRAWALS: ' + ('; '.join(f'{_m(w.amount)} {w.get_status_display()} {timezone.localtime(w.created_at):{fmt}}'
                                            for w in wds) or 'none'),
        f'OPEN TICKETS: {open_n}.',
    ])


SYSTEM = """You are the customer support assistant of {site}, a sports betting and Aviator site, on WhatsApp.

Answer ONLY from the FACTS below and the player's ACCOUNT (if given). If the facts don't cover it, say so briefly and set handoff=true.
Rules:
- Talk only about {site}: its betting, wallets, deposits, withdrawals, bonuses, promotions, Aviator, the WhatsApp bot and the website.
- Never give betting tips, predictions or "sure bets". Never encourage betting more or chasing losses; if someone seems to struggle, mention limits and self-exclusion.
- Never ask for, accept or repeat a password, PIN, OTP or card number. If one is sent, tell them to delete it.
- You cannot place bets, move money, change accounts or approve anything: explain how the player does it (menu commands or the website).
- Set handoff=true for: money missing or late (deposit not credited, withdrawal not received), disputes about a ticket's result, account changes or lockouts, complaints, anything about fraud, or when you are not sure. Then reply that a person from the team will answer here.
- Reply in the player's language (English, Shona or Ndebele). WhatsApp style: short, friendly, at most 6 lines, *bold* for key words, no markdown headings or tables.

FACTS:
{facts}
{account}"""

SCHEMA = {'type': 'OBJECT', 'properties': {
    'reply': {'type': 'STRING'}, 'handoff': {'type': 'BOOLEAN'}, 'reason': {'type': 'STRING'}},
    'required': ['reply', 'handoff']}


def _history(address: str, channel: str) -> list[dict]:
    since = timezone.now() - timedelta(hours=24)
    ins = [(m.received_at, 'user', m.text) for m in InboundMessage.objects.filter(channel=channel, address=address, received_at__gte=since)
           .order_by('-received_at')[:HISTORY]]
    outs = [(m.created_at, 'model', m.text) for m in OutboundMessage.objects.filter(channel=channel, address=address, created_at__gte=since)
            .order_by('-created_at')[:HISTORY]]
    turns = sorted(ins + outs, key=lambda t: t[0])[-HISTORY:]
    contents = []
    for _, role, text in turns:
        text = (text or '')[:400]
        if contents and contents[-1]['role'] == role:            # Gemini wants the roles to alternate
            contents[-1]['parts'][0]['text'] += '\n' + text
        else:
            contents.append({'role': role, 'parts': [{'text': text}]})
    return contents


def _over_limit(address: str, cfg: ChatbotSettings) -> bool:
    key = f'chatbot:ai:{address}:{timezone.localdate():%Y%m%d}'
    try:
        n = cache.incr(key)
    except ValueError:
        cache.set(key, 1, 26 * 3600)
        n = 1
    return n > cfg.ai_daily_limit


def ask(question: str, *, address: str = '', channel: str = 'whatsapp', player_id: Optional[int] = None,
        history: bool = True) -> dict:
    """{'reply', 'handoff', 'reason'} from Gemini, or raises on failure."""
    import requests
    from apps.branding.models import SiteIdentity
    cfg = ChatbotSettings.load()
    site = SiteIdentity.load().site_name or 'BetBlits'
    system = SYSTEM.format(site=site, facts=knowledge(),
                           account=f'\nACCOUNT (the player asking, logged in):\n{account_summary(player_id)}' if player_id else '')
    contents = _history(address, channel) if (history and address) else []
    question = services.redact(question)[:1000]
    if contents and contents[-1]['role'] == 'user':
        contents[-1]['parts'][0]['text'] += '\n' + question
    else:
        contents.append({'role': 'user', 'parts': [{'text': question}]})
    if contents[0]['role'] != 'user':
        contents = contents[1:]
    body = {'system_instruction': {'parts': [{'text': system}]}, 'contents': contents,
            'generationConfig': {'temperature': 0.3, 'maxOutputTokens': 700, 'responseMimeType': 'application/json',
                                 'responseSchema': SCHEMA}}
    res = requests.post(ENDPOINT.format(model=config.value('ai_model', cfg)), json=body, timeout=25,
                        headers={'x-goog-api-key': config.value('gemini_api_key', cfg)})
    if res.status_code >= 300:
        raise RuntimeError(f'Gemini {res.status_code}: {res.text[:200]}')
    data = res.json()
    text = data['candidates'][0]['content']['parts'][0]['text']
    out = json.loads(text)
    return {'reply': str(out.get('reply') or '').strip()[:1500], 'handoff': bool(out.get('handoff')),
            'reason': str(out.get('reason') or '')[:300]}


def handoff(address: str, *, channel: str = 'whatsapp', player_id: Optional[int] = None, reason: str = '',
            question: str = '', source: str = 'ai') -> SupportRequest:
    """Ask a person to take over (one open request per number)."""
    open_ = SupportRequest.objects.filter(channel=channel, address=address, resolved_at__isnull=True).first()
    if open_:
        return open_
    return SupportRequest.objects.create(channel=channel, address=address, player_id=player_id, reason=reason[:300],
                                         question=services.redact(question)[:2000], source=source)


def answer(*, address: str, question: str, channel: str = 'whatsapp', player_id: Optional[int] = None) -> list[dict]:
    """The replies to send for a free-text question."""
    cfg = ChatbotSettings.load()
    if _over_limit(address, cfg):
        handoff(address, channel=channel, player_id=player_id, reason='Daily AI question limit reached', question=question)
        return [{'text': 'You’ve asked a lot of questions today, so I’ve passed this one to our team: a person will reply here.',
                 'buttons': ['MENU']}]
    try:
        out = ask(question, address=address, channel=channel, player_id=player_id)
    except Exception:  # noqa: BLE001 — the player must always get an answer
        logger.exception('AI assistant failed for …%s', address[-4:])
        handoff(address, channel=channel, player_id=player_id, reason='AI unavailable', question=question)
        return [{'text': UNAVAILABLE, 'buttons': ['MENU']}]
    reply = out['reply'] or UNAVAILABLE
    if out['handoff']:
        handoff(address, channel=channel, player_id=player_id, reason=out['reason'] or 'Needs a person', question=question)
        if 'person' not in reply.lower() and 'team' not in reply.lower():
            reply += '\n\nI’ve passed this to our team: a person will reply here.'
    return [{'text': reply, 'buttons': ['MENU']}]
