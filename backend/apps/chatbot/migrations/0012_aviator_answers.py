"""Aviator is now playable on WhatsApp: update the starter answers that said it wasn't
(only where staff haven't edited them)."""
from django.db import migrations

AVIATOR = ('A plane takes off and the multiplier climbs: if it reaches your cash-out before it flies away, you win '
           'stake × that number.\nPlay it right here, no data needed: send *AVIATOR*, pick a stake and a cash-out, or type '
           '*AV 1 2* ($1 cashing out at 2.00x). *AV 1 2 10* plays 10 rounds, *CASH* cashes out early, *AV FREE* plays '
           'free spins. Results come here after every round. Also on the website: {site_url}aviator')
COMMANDS = ('Send *MENU* for everything. Handy words: *TODAY*, *LIVE*, *LEAGUES*, *COUNTRY* <name>, *BALANCE*, *OPEN*, '
            '*CASHOUT*, *DEPOSIT*, *HISTORY*, *AVIATOR* (play Aviator here), *SUPPORT*. Log in with *LOGIN* and your '
            'website details; you are logged out after {idle_minutes} minutes idle.')


def update(apps, schema_editor):
    Article = apps.get_model('chatbot', 'KnowledgeArticle')
    for question, answer, extra in (('How do I play Aviator?', AVIATOR, '\naviator on whatsapp\ncan i play aviator here\n'
                                                                        'aviator without data'),
                                    ('What can I do on WhatsApp?', COMMANDS, '')):
        a = Article.objects.filter(question=question, updated_by='starter').first()
        if a:
            a.answer = answer
            a.example_questions = (a.example_questions + extra).strip()
            a.buttons = 'AVIATOR,MENU'
            a.save(update_fields=['answer', 'example_questions', 'buttons'])


class Migration(migrations.Migration):
    dependencies = [('chatbot', '0011_aviator_on_whatsapp')]
    operations = [migrations.RunPython(update, migrations.RunPython.noop)]
