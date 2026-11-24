"""The WhatsApp bot's knowledge base: finds the staff-written answer a player's question is asking for.

Pipeline for a message no menu command took (engine.dispatch):

1. Problems ("my deposit didn't arrive", "withdrawal stuck") skip straight answers:
   they need the AI (which can see the player's account) or a person.
2. A sure match (SURE_SCORE) is sent as staff wrote it: instant, free, the same every time.
3. With the AI on, everything else goes to Gemini with the closest answers first (ai.ask),
   and what it works out is learned (learn_wording / learn_draft) so the next player asking
   the same way gets the answer without it.
4. With the AI off or down: a close match (ANSWER_SCORE) is sent, near ones (SUGGEST_SCORE)
   are offered to tap, and the rest is logged as unanswered for staff to write.

Matching is by meaning-bearing words, not embeddings: plurals and typos are forgiven
("withdrawl", "deposits"), everyday synonyms (English and Shona) count as one word ("cash
out" and "withdraw", "kubvisa"), and rare words weigh more than common ones. A site has tens
to a few hundred answers, so this is fast, needs no vector store and every score can be
explained in the admin's Try it.

Answers may hold {placeholders} filled from the live settings when sent ({withdrawal_fee},
{min_stake}...), so a changed rule never leaves a stale answer behind.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Optional

# Sent as written, without asking the AI.
SURE_SCORE = 0.8
# With the AI off or down, sent as written.
ANSWER_SCORE = 0.6
# Closer than this but not close enough: offered as "did you mean" rows.
SUGGEST_SCORE = 0.34
MAX_SUGGESTIONS = 3
# Answers the AI reads with each question, closest first.
AI_ARTICLES = 40

STOP_WORDS = {
    'a', 'an', 'the', 'is', 'are', 'am', 'was', 'be', 'do', 'does', 'did', 'you', 'your', 'yours', 'i', 'me', 'my',
    'we', 'us', 'our', 'to', 'of', 'for', 'in', 'on', 'at', 'can', 'could', 'it', 'its', 'and', 'or', 'please',
    'pls', 'plz', 'any', 'there', 'have', 'has', 'with', 'from', 'this', 'that', 'will', 'would', 'should', 'u',
    'ur', 'im', 'hi', 'hello', 'hey', 'good', 'morning', 'afternoon', 'evening', 'just', 'want', 'know', 'like',
    'tell', 'about', 'if', 'so', 'also', 'some', 'what', 'whats', 'which', 'who', 'kindly', 'sir', 'madam', 'maam',
    'thanks', 'thank', 'ok', 'okay', 'still', 'get', 'need', 'one', 'only', 'really', 'now', 'way', 'possible',
    'guys', 'boss', 'bro', 'help', 'question', 'ask', 'mean', 'means',
    # Shona fillers: "ndoda kuziva" (I want to know), "here?" (question mark), "ndingaita sei?" (how can I)
    'ndoda', 'ndiri', 'kuziva', 'here', 'sei', 'ndingaita', 'ndinoda', 'kuti', 'ndapota', 'mhoro', 'makadii',
    'ndeipi', 'zvakadii', 'ko', 'iko', 'iye', 'imi', 'ini',
}

# Words players use for the same idea. Each maps to one canonical word.
SYNONYMS = {
    'withdraw': {'withdraw', 'withdrawal', 'withdrawl', 'widraw', 'payout', 'kubvisa', 'bvisa', 'kuburitsa',
                 'buritsa', 'encash'},
    'deposit': {'deposit', 'topup', 'fund', 'load', 'kuisa', 'isa', 'recharge'},
    'method': {'ecocash', 'onemoney', 'innbucks', 'omari', 'mukuru', 'zipit', 'zimswitch', 'paynow', 'card', 'visa',
               'mastercard', 'bank', 'transfer', 'method', 'methods', 'mobile'},
    'ticket': {'ticket', 'slip', 'betslip', 'coupon', 'booking'},
    'bet': {'bet', 'wager', 'kubheja', 'bheja', 'punt', 'betting'},
    'odds': {'odds', 'odd', 'price', 'prices'},
    'bonus': {'bonus', 'promo', 'promotion', 'offer', 'reward', 'freebet', 'gift'},
    'register': {'register', 'registration', 'signup', 'join', 'create', 'kunyoresa', 'nyoresa', 'new'},
    'login': {'login', 'signin', 'log', 'logon'},
    'password': {'password', 'passcode', 'forgot', 'forget', 'reset', 'forgotten'},
    'verify': {'verify', 'verification', 'verified', 'kyc', 'identity', 'id', 'document', 'documents', 'passport'},
    'balance': {'balance', 'wallet', 'funds', 'mari', 'money', 'cash'},
    'win': {'win', 'winning', 'winnings', 'won', 'profit'},
    'lose': {'lose', 'lost', 'loss', 'losses', 'losing'},
    'fee': {'fee', 'fees', 'charge', 'charges', 'commission', 'deduct', 'deduction', 'deducted', 'percent',
            'percentage'},
    'limit': {'limit', 'limits', 'minimum', 'maximum', 'min', 'max', 'least', 'most', 'smallest', 'biggest'},
    'time': {'time', 'long', 'when', 'hour', 'hours', 'minute', 'minutes', 'fast', 'quick', 'soon', 'delay',
             'late', 'days'},
    'live': {'live', 'inplay'},
    'match': {'match', 'game', 'games', 'fixture', 'fixtures', 'team', 'teams'},
    'aviator': {'aviator', 'plane', 'crash', 'jet', 'spin', 'spins', 'fly'},
    'cashback': {'cashback'},
    'refund': {'refund', 'refunds'},
    'agent': {'agent', 'agents', 'affiliate', 'referral', 'refer'},
    'person': {'person', 'human', 'support', 'staff', 'operator', 'customer', 'care', 'call', 'phone', 'contact'},
    'whatsapp': {'whatsapp', 'chat', 'bot', 'watsapp', 'whatsap'},
    'combo': {'combo', 'combine', 'accumulator', 'acca', 'multiple', 'multi', 'parlay'},
    'safe': {'safe', 'secure', 'trust', 'legit', 'legal', 'licensed', 'licence', 'license', 'scam'},
    'stop': {'exclude', 'exclusion', 'addiction', 'addicted', 'gambling', 'break', 'pause'},
}
CANONICAL = {word: canon for canon, words in SYNONYMS.items() for word in words}

# A problem with this player's own money or account: never answered from a general article.
PROBLEM = re.compile(
    r"\b(not|never|didn'?t|did not|haven'?t|hasn'?t|have not|has not|isn'?t|wasn'?t|no|still)\b[\w\s']{0,30}?"
    r"\b(receiv|arriv|reflect|credit|show|paid|pay|come|came|work|load|go through|went through|refund)"
    r"|\btaking (so |too )?long\b|\btoo long\b|\b(missing|stuck|pending|late|delayed|scam|scammed|stolen|hacked|cheat|cheated|complain|complaint|wrong|"
    r"failed|error|blocked|locked|suspended|deducted|disappeared|unfair|robbed|chakarasika|hazvisi)\b",
    re.IGNORECASE)


def stem(word: str) -> str:
    """A light English stemmer: enough to make "withdrawals", "withdrawing" and "withdraw" meet."""
    if word in CANONICAL:
        return CANONICAL[word]
    candidates = [word]
    if word.endswith('ies') and len(word) > 4:
        candidates = [word[:-3] + 'y']
    elif re.search(r'(x|ch|sh|ss|z)es$', word):
        candidates = [word[:-2]]
    elif word.endswith('ing') and len(word) > 5:
        candidates = [word[:-3], word[:-3] + 'e']
    elif word.endswith('ed') and len(word) > 4:
        candidates = [word[:-2], word[:-1]]
    elif word.endswith('s') and not word.endswith(('ss', 'us')) and len(word) > 3:
        candidates = [word[:-1]]
    for base in candidates:
        if base in CANONICAL:
            return CANONICAL[base]
    return candidates[0]


def tokens(text: str) -> list[str]:
    text = (text or '').lower().replace("'", '').replace('cash out', 'cashout').replace('top up', 'topup') \
        .replace('sign up', 'signup').replace('log in', 'login').replace('sign in', 'signin') \
        .replace('in play', 'inplay').replace('in-play', 'inplay').replace('free bet', 'freebet') \
        .replace('money back', 'cashback')
    words = re.findall(r'[a-z0-9]+', text)
    return [stem(w) for w in words if w not in STOP_WORDS and (len(w) > 1 or w.isdigit())]


def _close(a: str, b: str) -> bool:
    """Same word, or one typo away for words long enough to tell apart."""
    if a == b:
        return True
    # People rarely mistype the first letter, and checking it keeps "redeposit" from meaning "deposit".
    if len(a) < 4 or len(b) < 4 or abs(len(a) - len(b)) > 2 or a[0] != b[0]:
        return False
    m = SequenceMatcher(None, a, b)
    return m.real_quick_ratio() >= 0.8 and m.ratio() >= 0.8


def phrase_in(phrase: str, text: str) -> bool:
    """A keyword appears in the text as whole words."""
    return bool(phrase) and re.search(rf'(?<!\w){re.escape(phrase)}(?!\w)', text) is not None


def _plain(text: str) -> str:
    return ' '.join(re.findall(r'[a-z0-9]+', (text or '').lower().replace("'", '')))


def phrasings(article) -> list[str]:
    """Every way of asking an answer: the question, staff's other wordings and the ones the bot learned."""
    return [article.question, *(article.example_questions or '').splitlines(),
            *(article.learned_questions or '').splitlines()]


@dataclass
class Match:
    article: object
    score: float


class Index:
    """Answers ready to be searched. Cheap to build: tens to hundreds of answers, not millions."""

    def __init__(self, articles):
        self.articles = list(articles)
        self.phrasings: list[tuple[int, list[str]]] = []
        self.keywords: list[tuple[int, str]] = []
        self.exact: dict[str, int] = {}
        doc_words: list[set[str]] = []
        for i, article in enumerate(self.articles):
            words: set[str] = set()
            for line in phrasings(article):
                if not line.strip():
                    continue
                self.exact.setdefault(_plain(line), i)
                if found := tokens(line):
                    self.phrasings.append((i, found))
                    words.update(found)
            for keyword in (article.keywords or '').lower().split(','):
                keyword = keyword.strip()
                if keyword:
                    self.keywords.append((i, keyword))
                    if found := tokens(keyword):
                        self.phrasings.append((i, found))
                        words.update(found)
            doc_words.append(words)
        count = len(doc_words) or 1
        frequency: dict[str, int] = {}
        for words in doc_words:
            for word in words:
                frequency[word] = frequency.get(word, 0) + 1
        # Rare words say more about which answer is meant than words every answer shares.
        self.weight = {w: math.log((count + 1) / (n + 0.5)) + 1 for w, n in frequency.items()}
        self.vocabulary = list(self.weight)
        self.unknown_weight = max(self.weight.values(), default=1.0)

    def _weight(self, word: str) -> float:
        # A word no answer uses ("basketball") is the most telling of all: it's what nobody answered.
        return self.weight.get(word, self.unknown_weight)

    def _known(self, word: str) -> Optional[str]:
        if word in self.weight:
            return word
        return next((v for v in self.vocabulary if _close(word, v)), None)

    def search(self, text: str, limit: int = 5) -> list[Match]:
        lowered = ' ' + (text or '').lower() + ' '
        said = [self._known(w) or w for w in tokens(text)]
        best: dict[int, float] = {}
        if said:
            said_set = set(said)
            said_total = sum(self._weight(w) for w in said_set)
            for i, words in self.phrasings:
                wanted = set(words)
                covered = sum(self._weight(w) for w in wanted if w in said_set)
                if not covered:
                    continue
                recall = covered / sum(self._weight(w) for w in wanted)
                precision = sum(self._weight(w) for w in said_set if w in wanted) / said_total
                # Covering the question matters more than every word of the message being on topic.
                beta2 = 2.25
                score = (1 + beta2) * precision * recall / (beta2 * precision + recall)
                best[i] = max(best.get(i, 0.0), score)
        for i, keyword in self.keywords:
            if phrase_in(keyword, lowered):
                # A keyword staff typed is a strong signal; a longer one is a more specific one.
                best[i] = max(best.get(i, 0.0), 0.8 + min(len(keyword), 40) / 400)
        exact = self.exact.get(_plain(text))
        if exact is not None:
            best[exact] = 1.0
        ranked = sorted(best.items(), key=lambda p: (-p[1], p[0] != exact, p[0]))
        return [Match(self.articles[i], round(s, 3)) for i, s in ranked[:limit]]


def active_articles():
    from .models import KnowledgeArticle
    return KnowledgeArticle.objects.filter(is_active=True, is_draft=False).order_by('id')


def search(text: str, limit: int = 5) -> list[Match]:
    return Index(active_articles()).search(text, limit)


def is_problem(text: str) -> bool:
    return bool(PROBLEM.search(text or ''))


# -- live values ------------------------------------------------------------------------
def _m(v) -> str:
    return f'${Decimal(v):.2f}'


def _n(v) -> str:
    return f'{Decimal(v).normalize():f}'


class _Values(dict):
    def __missing__(self, key):
        return '{' + key + '}'          # an unknown placeholder stays as typed, so staff can see it


PLACEHOLDERS = {
    'site': 'Site name', 'site_url': 'Website address', 'min_stake': 'Smallest stake', 'max_stake': 'Largest stake',
    'max_selections': 'Most matches per ticket', 'deposit_min_odds': 'Minimum ticket odds (Deposit wallet)',
    'bonus_min_odds': 'Minimum ticket odds (Bonus wallet)', 'bonus_rules': 'How the Bonus wallet works',
    'withdrawal_fee': 'Fee withdrawing from Winnings', 'deposit_withdrawal_fee': 'Fee withdrawing from Deposit',
    'min_withdrawal': 'Smallest withdrawal', 'max_withdrawal': 'Largest withdrawal at once',
    'daily_withdrawal_max': 'Most withdrawn a day', 'deposit_methods': 'Deposit methods switched on',
    'deposit_bonuses': 'Deposit bonuses running', 'promotions': 'Promotions running',
    'refund_rule': 'Lost-by-one refund rule', 'cashback_rule': 'Cashback rule',
    'chat_max_stake': 'Most per ticket on WhatsApp', 'chat_daily_cap': 'WhatsApp limit per day',
    'idle_minutes': 'WhatsApp idle logout (minutes)', 'chat_withdrawals': 'Withdrawing on WhatsApp',
    'support_email': 'Support email',
}


def refund_rule() -> str:
    from apps.promotions.models import LossRefundSettings
    r = LossRefundSettings.load()
    if not r.enabled:
        return 'There is no lost-by-one refund at the moment.'
    return (f'A multiple with ticket odds above {_n(r.min_odds)} that lost on exactly one match gets back stake × ticket '
            f'odds ÷ {_n(r.divisor)} ÷ the lost match’s odds, paid to Winnings once all its matches finish'
            + (f' (at most {_m(r.max_refund)})' if r.max_refund is not None else '') + '. Bonus-wallet tickets don’t count.')


def cashback_rule() -> str:
    from apps.promotions.models import CashbackSettings, CashbackTier
    cb = CashbackSettings.load()
    tiers = list(CashbackTier.objects.filter(active=True).order_by('min_loss'))
    if not (cb.enabled and tiers):
        return 'There is no cashback at the moment.'
    return f'Every {cb.period_days} days: ' + '; '.join(
        f'lose {_m(t.min_loss)}+' + (f' with {t.min_tickets}+ tickets' if t.min_tickets else '')
        + (f' on {t.min_active_days}+ days' if t.min_active_days else '') + f' → {_n(t.percent)}% back'
        + (f' (max {_m(t.max_amount)})' if t.max_amount is not None else '') for t in tiers
    ) + '. Paid to Winnings; real-money play only.'


def placeholder_values() -> _Values:
    """The live values answers may quote, read now."""
    from apps.branding.models import SiteIdentity
    from apps.promotions import services as promos
    from apps.promotions.models import Promotion
    from apps.wallet.models import PaymentMethod, WalletRules, WithdrawalSettings
    from .menus import site_url
    from .models import ChatbotSettings
    site = SiteIdentity.load()
    rules, wd, chat = WalletRules.load(), WithdrawalSettings.load(), ChatbotSettings.load()
    methods = [m.name for m in PaymentMethod.objects.filter(deposit_enabled=True)]
    bonuses = promos.live_deposit_bonuses()
    offers = list(Promotion.objects.filter(active=True, deleted_at__isnull=True).exclude(code__startswith='SYS-')
                  .exclude(code__startswith='deposit-bonus:').values_list('name', flat=True)[:8])
    return _Values(
        site=site.site_name or 'BetBlits',
        site_url=site_url('/') or 'betblits.com/',
        min_stake=_m(rules.min_stake), max_stake=_m(rules.max_stake), max_selections=str(rules.max_selections),
        deposit_min_odds=_n(rules.deposit_min_odds), bonus_min_odds=_n(rules.bonus_min_odds),
        bonus_rules=(f'Bonus money is for sports only: a multiple of at least {rules.bonus_min_legs} selections, each at '
                     f'least {_n(rules.bonus_min_leg_odds)}. Win {rules.bonus_wins_to_convert} bonus tickets in a row and the '
                     f'bonus moves to Winnings (up to {_m(rules.bonus_max_conversion)}). Unused bonus expires after '
                     f'{rules.bonus_expiry_hours} hours.'),
        withdrawal_fee=f'{_n(wd.fee_percent)}%', deposit_withdrawal_fee=f'{_n(wd.deposit_fee_percent)}%',
        min_withdrawal=_m(wd.min_amount), max_withdrawal=_m(wd.max_amount), daily_withdrawal_max=_m(wd.daily_max),
        deposit_methods=', '.join(methods) or 'the methods shown on the Deposit page',
        deposit_bonuses='; '.join(f'{t.name}: {_n(t.percent)}% from {_m(t.min_deposit)}'
                                  + (f' (max {_m(t.max_bonus)})' if t.max_bonus else '') for t in bonuses)
        or 'no deposit bonus at the moment',
        promotions='; '.join(offers) or 'no other promotions at the moment',
        refund_rule=refund_rule(), cashback_rule=cashback_rule(),
        chat_max_stake=_m(chat.max_stake), chat_daily_cap=_m(chat.daily_cap), idle_minutes=str(chat.session_minutes),
        chat_withdrawals=('You can withdraw on WhatsApp with *WITHDRAW*, using the chat PIN set on the website; money only '
                          'goes to a number you deposited from.') if chat.allow_withdrawals
        else 'Withdrawals are made on the website.',
        support_email=site.support_email or 'our support team',
    )


def render(article, values: Optional[dict] = None) -> str:
    text = article.answer
    if '{' not in text:
        return text
    try:
        return text.format_map(values if values is not None else placeholder_values())
    except (ValueError, IndexError, AttributeError, KeyError):
        return text                     # a stray brace: send the answer as typed


def buttons(article) -> list[str]:
    return [b.strip().upper() for b in (article.buttons or '').split(',') if b.strip()][:3] or ['MENU']


def record_hit(article) -> None:
    from django.db.models import F
    from django.utils import timezone
    type(article).objects.filter(pk=article.pk).update(hit_count=F('hit_count') + 1, last_used_at=timezone.now())


def reply_for(article, values: Optional[dict] = None) -> dict:
    """The chat reply for an answer."""
    return {'text': render(article, values), 'buttons': buttons(article)}


def row(article) -> list[str]:
    """A list row for an answer (WhatsApp: title 24, description 72); tapping it sends FAQ <id>."""
    q = article.question
    title = q if len(q) <= 24 else q[:23].rsplit(' ', 1)[0].rstrip(' ,(') + '…'
    return [f'FAQ {article.pk}', title, q[:72] if len(q) > 24 else '']


def suggestions(matches: list[Match]) -> dict:
    """"Did you mean" rows for near answers."""
    rows = [row(m.article) for m in matches]
    rows.append(['SUPPORT', '💬 Ask a person', 'Someone from the team replies here'])
    return {'text': '🤔 I’m not sure I understood. Did you mean one of these?',
            'list': {'button': 'Choose a question', 'title': 'Did you mean', 'rows': rows}}


# -- the question log ----------------------------------------------------------------------
def log(*, address: str, channel: str, text: str, source: str, article=None, score: float = 0.0, reply: str = ''):
    from .models import BotQuestion
    from .services import redact
    return BotQuestion.objects.create(channel=channel, address=address, text=redact(text)[:2000], source=source,
                                      article=article, score=score, reply=(reply or '')[:2000])


# -- learning from the AI ------------------------------------------------------------------
MAX_LEARNED = 40       # wordings kept per answer; the oldest go first
MAX_DRAFTS = 200       # unreviewed drafts; past this the bot stops writing new ones until staff catch up
LEARN_MAX_CHARS = 150
# A phone number, an amount, a ticket or transaction number, an email or a link is about one player.
PRIVATE = re.compile(r'\d{3,}|\$\s?\d|@|https?://|www\.', re.IGNORECASE)


def learnable(text: str) -> Optional[str]:
    """The message tidied up, if it is a short, general question worth keeping; otherwise None."""
    tidy = ' '.join((text or '').split())
    if not (3 <= len(tidy) <= LEARN_MAX_CHARS) or PRIVATE.search(tidy) or is_problem(tidy) or not tokens(tidy):
        return None
    return tidy


def learn_wording(article, text: str) -> bool:
    """The AI answered this message from this answer: keep the wording so it matches without the AI next time.
    Only matching learns: what players are sent is still what staff wrote."""
    from django.db import transaction
    from .models import KnowledgeArticle
    tidy = learnable(text)
    if tidy is None:
        return False
    with transaction.atomic():
        article = KnowledgeArticle.objects.select_for_update().filter(pk=article.pk, is_active=True, is_draft=False).first()
        if article is None or _plain(tidy) in {_plain(line) for line in phrasings(article)}:
            return False
        top = search(tidy, limit=1)
        if top and top[0].article.pk == article.pk and top[0].score >= SURE_SCORE:
            return False                # already answered without the AI: nothing to learn
        learned = [line for line in article.learned_questions.splitlines() if line.strip()]
        article.learned_questions = '\n'.join([*learned, tidy][-MAX_LEARNED:])
        article.save(update_fields=['learned_questions', 'updated_at'])
    return True


def learn_draft(text: str, reply: str, category: str = 'other'):
    """The AI answered a general question no answer covers: save its reply as a draft for staff to approve.
    A draft is off, so players never get it until staff have read it. The same question asked again
    counts towards the draft already there, so the most asked come first."""
    from django.db import transaction
    from django.db.models import F
    from .models import KnowledgeArticle
    tidy = learnable(text)
    reply = (reply or '').strip()
    if tidy is None or not reply:
        return None
    with transaction.atomic():
        drafts = list(KnowledgeArticle.objects.select_for_update().filter(is_draft=True).order_by('id'))
        top = Index(drafts).search(tidy, limit=1) if drafts else []
        if top and top[0].score >= ANSWER_SCORE:
            draft = top[0].article
            if _plain(tidy) not in {_plain(line) for line in phrasings(draft)}:
                lines = [line for line in draft.example_questions.splitlines() if line.strip()]
                draft.example_questions = '\n'.join([*lines, tidy][-MAX_LEARNED:])
                draft.save(update_fields=['example_questions', 'updated_at'])
            KnowledgeArticle.objects.filter(pk=draft.pk).update(times_asked=F('times_asked') + 1)
            return draft
        if len(drafts) >= MAX_DRAFTS:
            return None
        cats = {c for c, _ in KnowledgeArticle.Category.choices}
        return KnowledgeArticle.objects.create(question=tidy[:200], answer=reply[:2000], is_active=False, is_draft=True,
                                               times_asked=1, category=category if category in cats else 'other',
                                               updated_by='AI draft')


@dataclass
class Decision:
    """What the bot does with a free-text message, before any AI call (engine and Try it share it)."""
    action: str                          # 'kb' | 'ai' | 'suggest' | 'none'
    matches: list = field(default_factory=list)
    problem: bool = False

    @property
    def best(self) -> Optional[Match]:
        return self.matches[0] if self.matches else None


def decide(text: str, *, ai_on: bool) -> Decision:
    matches = search(text)
    best = matches[0] if matches else None
    problem = is_problem(text)
    if not problem and best and best.score >= (SURE_SCORE if ai_on else ANSWER_SCORE):
        return Decision('kb', matches, problem)
    if ai_on:
        return Decision('ai', matches, problem)
    if not problem and best and best.score >= SUGGEST_SCORE:
        return Decision('suggest', [m for m in matches if m.score >= SUGGEST_SCORE][:MAX_SUGGESTIONS], problem)
    return Decision('none', matches, problem)
