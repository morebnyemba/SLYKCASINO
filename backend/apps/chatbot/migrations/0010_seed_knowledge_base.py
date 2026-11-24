"""Starter knowledge base answers. Staff edit them under Admin → Knowledge base; the
{placeholders} are filled from the live settings each time an answer is sent."""
from django.db import migrations

ARTICLES = [
    # category, question, other wordings, keywords, answer, buttons
    ('betting', 'How do I place a bet?',
     'how to bet\nhow do i bet on whatsapp\nhow to place a bet on the website\nhow does betting work\nndingabheja sei',
     'place a bet,how to bet',
     'On WhatsApp: send *TODAY* (or *LIVE*), open a match by its number, tap your picks, then *Place bet*, type your stake '
     'and *CONFIRM*.\nOn the website: tap the odds you want, they go on your betslip, enter a stake and place it.\n'
     'Stakes are {min_stake} to {max_stake}, up to {max_selections} matches per ticket.',
     'TODAY,LIVE,MENU'),
    ('betting', 'What are odds and how are winnings worked out?',
     'how do odds work\nwhat does 2.50 mean\nhow much will i win\nhow are winnings calculated\npossible win',
     'how do odds work',
     'Odds show what you get back per $1 staked. A $2 stake at odds 2.50 returns *$5.00* ($3.00 profit plus your stake).\n'
     'On a multiple the odds of every pick multiply together, and every pick must win.',
     'TODAY,MENU'),
    ('betting', 'What is a multiple (accumulator) and can I combine picks from one match?',
     'what is an accumulator\nwhat is a multi bet\ncan i pick two markets in the same match\nsame match combo\nbet builder',
     'accumulator,same match',
     'A multiple puts several picks on one ticket: the odds multiply, and every pick must win.\n'
     'Picks from the *same match* (e.g. Win & Both teams to score) join into one combined pick at one price that allows '
     'for how they go together, so it is usually lower than the two odds multiplied.',
     'TODAY,MENU'),
    ('betting', 'What are the betting limits?',
     'minimum stake\nmaximum stake\nhow many matches can i put on a ticket\nminimum odds\nlowest bet',
     'minimum stake,maximum stake,minimum odds',
     '• Stake: {min_stake} to {max_stake} per ticket\n• Up to {max_selections} matches per ticket\n'
     '• Minimum ticket odds: {deposit_min_odds} (Deposit wallet), {bonus_min_odds} (Bonus wallet)\n'
     '• On WhatsApp: at most {chat_max_stake} per ticket and {chat_daily_cap} a day',
     'RULES,MENU'),
    ('betting', 'Can I bet on live matches?',
     'live betting\nin play betting\ncan i bet while the match is playing\nwhy are live odds closed',
     'live betting,in play',
     'Yes: send *LIVE* to see matches in play. Live prices change quickly, so a bet is checked for a few seconds before '
     'it is accepted, and a market closes while it is suspended (e.g. after a goal). Late in a match markets close for good.',
     'LIVE,MENU'),
    ('betting', 'How do I cash out a ticket early?',
     'cash out\nearly cashout\ncan i cash out my bet\ntake my money before the match ends',
     'cash out,cashout',
     'Send *CASHOUT* to see your open tickets that can be cashed out and the amount offered now. Tap one and confirm. '
     'The offer changes with the matches.',
     'CASHOUT,MENU'),
    ('deposits', 'How do I deposit?',
     'how to deposit\nhow do i put money in my account\nhow to fund my account\nhow to deposit with ecocash\nndingaisa sei mari',
     'how to deposit,top up',
     'Deposit with: {deposit_methods}.\nOn WhatsApp send *DEPOSIT*, the amount and the method, e.g. *DEPOSIT 10 ECOCASH*, '
     'then approve the prompt on your phone. On the website: Account → Wallet → Deposit. Most deposits arrive within a minute.\n'
     'Bonus: {deposit_bonuses}.',
     'DEPOSIT,BALANCE,MENU'),
    ('withdrawals', 'How do I withdraw my winnings?',
     'how to withdraw\nhow do i cash my money\nhow to get my winnings\nhow can i take out my money\nndingabvisa sei mari',
     'how to withdraw',
     'Withdraw from your *Winnings* wallet on the website: Account → Wallet → Withdraw. {chat_withdrawals}\n'
     'Minimum {min_withdrawal}, maximum {max_withdrawal} at once and {daily_withdrawal_max} a day. Your identity must be '
     'verified first. Our team pays withdrawals and you get a message when it is sent.',
     'BALANCE,WITHDRAWALS,MENU'),
    ('withdrawals', 'What does it cost to withdraw?',
     'withdrawal fee\nwhy was money deducted when i withdrew\nwithdrawal charges\nhow much do you charge to withdraw',
     'withdrawal fee,withdrawal charges',
     'Withdrawing from *Winnings* costs {withdrawal_fee}. Withdrawing deposit money you haven’t played costs '
     '{deposit_withdrawal_fee}. The fee is shown before you confirm.',
     'BALANCE,MENU'),
    ('withdrawals', 'How long does a withdrawal take?',
     'when will i get my withdrawal\nhow long to receive my money\nwithdrawal time\nhow fast are payouts',
     'withdrawal time',
     'Our team pays withdrawals as they come in, usually the same day, and you get a message when it is sent. '
     'Send *WITHDRAWALS* to see the status of yours.',
     'WITHDRAWALS,MENU'),
    ('bonuses', 'How does the Bonus wallet work?',
     'what is bonus money\nhow do i use my bonus\nhow to convert bonus to cash\nwhy can i not withdraw my bonus\nbonus rules',
     'bonus wallet,bonus rules',
     '{bonus_rules}\nSend *BONUS* to see yours.',
     'BONUS,MENU'),
    ('bonuses', 'What promotions are running?',
     'any promotions\nwhat offers do you have\npromo code\nfree bets\ncurrent promotions',
     'promotions,promo code,offers',
     'Running now: {promotions}.\nDeposit bonus: {deposit_bonuses}.\nGot a promo code? Send *PROMO* and the code.',
     'OFFERS,MENU'),
    ('bonuses', 'What is the lost-by-one refund?',
     'lost by one\nmy ticket lost by one game\nrefund when one match loses\none team cut my ticket',
     'lost by one,lost by 1',
     '{refund_rule}',
     'TICKETS,MENU'),
    ('bonuses', 'How does cashback work?',
     'cashback\ndo you give money back when i lose\nloss back\ncash back on losses',
     'cashback,cash back',
     '{cashback_rule}',
     'MENU'),
    ('account', 'How do I register?',
     'how to open an account\nhow to sign up\ncreate account\nhow do i join\nndinonyoresa sei',
     'register,sign up,create account',
     'Send *REGISTER* here, or sign up at {site_url}. You need a username, a password and an *agent code* from a BetBlits '
     'agent: you can’t register without a valid code. Use the same username and password on WhatsApp and the website.',
     'REGISTER,LOGIN,MENU'),
    ('account', 'What is an agent code and where do I get one?',
     'agent code\nwhere do i get an agent code\ni do not have an agent code\ninvalid agent code',
     'agent code',
     'An agent code links your account to the BetBlits agent who introduced you, and it is needed to register. Ask the '
     'agent who told you about us, or contact {support_email}.',
     'REGISTER,MENU'),
    ('account', 'I forgot my password',
     'reset password\ncant log in\nforgot my password\nhow do i change my password\ni cannot login',
     'forgot password,reset password',
     'Reset it at {site_url}forgot-password: we email you a link. Never send your password or PIN in this chat: nobody from '
     'BetBlits will ever ask for it.',
     'LOGIN,MENU'),
    ('account', 'How do I verify my identity (KYC)?',
     'verification\nkyc\nwhy do i need to verify\nupload id\nhow long does verification take',
     'verification,kyc,verify',
     'On the website open Account → Verification and upload a clear photo of your ID. It is needed before your first '
     'withdrawal and is usually checked within a day. You get a message when it is done.',
     'MENU'),
    ('whatsapp', 'What can I do on WhatsApp?',
     'whatsapp commands\nhow does the bot work\nwhat commands can i use\nhelp with the bot',
     'commands,whatsapp bot',
     'Send *MENU* for everything. Handy words: *TODAY*, *LIVE*, *LEAGUES*, *COUNTRY* <name>, *BALANCE*, *OPEN*, *CASHOUT*, '
     '*DEPOSIT*, *HISTORY*, *SUPPORT*. Log in with *LOGIN* and your website details; you are logged out after '
     '{idle_minutes} minutes idle.',
     'MENU'),
    ('aviator', 'How do I play Aviator?',
     'aviator\nhow does aviator work\nplane game\nhow to claim free spins\naviator free spins',
     'aviator,free spins',
     'A plane takes off and the multiplier climbs: cash out before it flies away to win your stake × the multiplier. '
     'Aviator is on the website ({site_url}aviator), not in WhatsApp. Free spins from promotions are claimed on the Aviator page.',
     'AVIATOR,MENU'),
    ('safety', 'How do I set limits or take a break from gambling?',
     'self exclusion\ndeposit limit\ni want to stop gambling\ni am addicted\nblock my account',
     'self exclusion,deposit limit,addicted',
     'You can set deposit limits, a lower WhatsApp limit or exclude yourself in Account → Settings on the website. '
     'If gambling stops being fun, take a break: we are here to help at {support_email}.',
     'SAFE,MENU'),
    ('other', 'Is BetBlits safe and legit?',
     'is this legit\nis this a scam\ncan i trust you\nare you licensed\nis my money safe',
     'legit,licensed',
     'Your balance, bets and withdrawals follow the same rules on WhatsApp and the website, withdrawals need your '
     'verified identity, and we never ask for your password or PIN. Full terms: {site_url}legal/terms',
     'RULES,MENU'),
]


def seed(apps, schema_editor):
    Article = apps.get_model('chatbot', 'KnowledgeArticle')
    if Article.objects.exists():
        return
    Article.objects.bulk_create([
        Article(category=cat, question=q, example_questions=ex, keywords=kw, answer=a, buttons=b, updated_by='starter')
        for cat, q, ex, kw, a, b in ARTICLES
    ])


class Migration(migrations.Migration):
    dependencies = [('chatbot', '0009_knowledge_base')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
