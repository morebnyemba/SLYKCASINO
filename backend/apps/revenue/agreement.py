"""The revenue-share purchase agreement a buyer accepts before a sale counts.

The text lives here, not in the admin app, so the server can record exactly what
was accepted: each sale stores VERSION and the SHA-256 of the text. Change the
wording → bump VERSION (old sales keep the hash of the text they accepted).
Have a lawyer in the operator's jurisdiction review this before relying on it.
"""
import hashlib
import json

VERSION = '2026-11-14'
TITLE = 'Revenue share purchase agreement and risk disclosure'

SECTIONS = [
    ('What you are buying', [
        'You are buying a contractual right to a percentage of the platform’s daily real-money gross gaming '
        'revenue (GGR) after carried losses, paid into a share wallet when each day closes. The percentage is '
        'shown on your wallet.',
        'You are not buying shares, stock, membership, voting rights, ownership or any claim on the assets, '
        'licences, software, brand, player funds or goodwill of the operator. You get no say in how the platform '
        'is run.',
        'This is not a deposit, a loan, a bond or a savings product, and it is not covered by any deposit '
        'protection or investor compensation scheme.',
    ]),
    ('No guaranteed return', [
        'Payouts depend entirely on how players bet. GGR goes up and down, can be negative for days or months, '
        'and a losing day is carried forward and reduces later payouts. You may receive nothing for long periods, '
        'or ever.',
        'The price is worked out from the last 30 closed days. Past revenue does not predict future revenue, and '
        'the formula price is not a valuation, a forecast or a promise of what you will earn. Nobody at the '
        'operator has promised you a return, a payback period or a profit.',
        'You may lose the whole price you paid.',
    ]),
    ('Risks you accept', [
        'The platform may earn less, stop operating, be suspended, lose or fail to obtain a gambling licence, '
        'change its products, odds, bonuses or markets, or close. Any of these can reduce or end your payouts '
        'and the operator owes you nothing for it.',
        'Laws, regulators, taxes, payment providers, banks or data providers may change or act in ways that '
        'reduce revenue or stop payouts.',
        'Fraud, chargebacks, bonus abuse, technical faults, voided bets and corrections can change the GGR of a '
        'day after the fact; payouts follow the GGR as finally recorded.',
        'There is no market for your share. The operator does not have to buy it back. You can only sell it '
        'through the release process on the platform, which needs a buyer and pays you the release share of the '
        'price (currently 90%) only when, and if, a sale is confirmed.',
    ]),
    ('How changes work', [
        'Your percentage can only be cut or handed to someone else with your approval, except where this '
        'agreement or the law allows otherwise (for example fraud, a court order or a regulator’s instruction).',
        'The operator may change the size of the partner pool, the price formula and other share settings, but '
        'not in a way that reduces a percentage you already hold without your approval.',
    ]),
    ('Payment and taxes', [
        'You pay outside the platform (EcoCash, bank transfer or another agreed method). The sale counts only '
        'when an admin confirms the payment and records its reference. Until then your request may be rejected '
        'or expire, and any money already sent is returned less the sending fees.',
        'You are responsible for any tax on what you pay and what you receive, and for any approval you need '
        'under the laws that apply to you. Payouts may be held where the law requires.',
    ]),
    ('Your confirmations', [
        'You are at least 18, buying for yourself with money that is lawfully yours and that you can afford to '
        'lose, and you are allowed to make this purchase where you live.',
        'You have not relied on any statement about future earnings, from anyone, that is not in this agreement.',
        'You have had the chance to take independent legal, tax and financial advice.',
    ]),
    ('Liability', [
        'To the fullest extent the law allows, the operator, its directors, staff and other share holders are not '
        'liable to you for any loss of revenue, profit, payout, opportunity or the price you paid, or for any '
        'indirect or consequential loss, arising from the platform’s performance or from this agreement.',
        'If the operator is found liable to you anyway, its total liability is limited to the price you paid for '
        'the share concerned, less what you have already received from it.',
        'Nothing in this agreement excludes liability for fraud, or any liability that the law does not allow to '
        'be excluded.',
    ]),
    ('General', [
        'This agreement is governed by the law named in the platform’s Terms & Conditions. Your acceptance, the '
        'version of this text and its fingerprint are recorded with your purchase.',
        'If any part of this agreement cannot be enforced, the rest still applies.',
    ]),
]


def _canonical() -> str:
    return json.dumps({'version': VERSION, 'title': TITLE, 'sections': SECTIONS}, ensure_ascii=False, sort_keys=True)


TEXT_SHA256 = hashlib.sha256(_canonical().encode('utf-8')).hexdigest()


def payload() -> dict:
    return {'version': VERSION, 'title': TITLE, 'sha256': TEXT_SHA256,
            'sections': [{'heading': h, 'paragraphs': ps} for h, ps in SECTIONS]}
