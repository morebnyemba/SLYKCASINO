"""Chat betting Celery tasks: sending replies, and telling the player how an
in-play bet or a deposit turned out."""
from __future__ import annotations

from celery import shared_task


@shared_task(name='apps.chatbot.tasks.send_replies')
def send_replies(channel: str, address: str, replies: list[dict]) -> int:
    from . import services
    return services.send_now(channel, address, replies)


@shared_task(name='apps.chatbot.tasks.report_ticket')
def report_ticket(channel: str, address: str, kind: str, obj_id: int) -> None:
    """After the in-play acceptance delay: accepted or rejected (refunded)."""
    from apps.sportsbook.models import Bet, BetSlip
    from . import services
    obj = (Bet if kind == 'bet' else BetSlip).objects.filter(pk=obj_id).first()
    if obj is None:
        return
    if obj.status == 'accepting':
        report_ticket.apply_async(args=(channel, address, kind, obj_id), countdown=10, retry=False)
        return
    ref = obj.code or obj.id
    text = (f'❌ Ticket {ref} was not accepted: the price or the match changed during the in-play check. '
            'Your stake is back in your wallet.'
            if obj.status == 'rejected' else f'✅ Ticket {ref} is confirmed. Good luck!')
    services.send_now(channel, address, [{'text': text}])


@shared_task(name='apps.chatbot.tasks.report_deposit')
def report_deposit(channel: str, address: str, reference: str, tries: int = 0) -> None:
    """Check a chat deposit with Paynow and say when it's in (or failed)."""
    from apps.wallet import payments
    from apps.wallet.models import PaymentTransaction
    from . import services
    txn = PaymentTransaction.objects.filter(reference=reference).first()
    if txn is None:
        return
    txn = payments.refresh(txn)
    if txn.status == PaymentTransaction.Status.PAID:
        services.send_now(channel, address, [{'text': f'✅ Your ${txn.amount:.2f} deposit is in your wallet.',
                                              'buttons': ['BALANCE', 'GAMES']}])
    elif txn.status == PaymentTransaction.Status.PENDING and tries < 5:
        report_deposit.apply_async(args=(channel, address, reference, tries + 1), countdown=60, retry=False)
    elif txn.status != PaymentTransaction.Status.PENDING:
        services.send_now(channel, address, [{'text': f'❌ Your ${txn.amount:.2f} deposit did not go through. '
                                                      'Send DEPOSIT and the amount to try again.'}])


@shared_task(name='apps.chatbot.tasks.purge_bot_questions')
def purge_bot_questions(days: int = 90) -> int:
    """The question log holds what players typed: keep it 90 days."""
    from datetime import timedelta
    from django.utils import timezone
    from .models import BotQuestion
    return BotQuestion.objects.filter(created_at__lt=timezone.now() - timedelta(days=days)).delete()[0]
