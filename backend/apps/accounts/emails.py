"""accounts email helpers — thin wrappers around django.core.mail."""
from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def send_verification_email(player, token: str) -> None:
    """Send email-verification link to the player."""
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    subject = "Verify your SLYK Casino email"
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [player.email]

    text_body = (
        f"Hi {player.username},\n\n"
        f"Please verify your email address by clicking the link below:\n\n"
        f"{verify_url}\n\n"
        f"If you didn't create an account, you can ignore this email.\n\n"
        f"-- SLYK Casino"
    )
    html_body = (
        f"<p>Hi <strong>{player.username}</strong>,</p>"
        f"<p>Please verify your email address by clicking the link below:</p>"
        f'<p><a href="{verify_url}">{verify_url}</a></p>'
        f"<p>If you didn't create an account, you can ignore this email.</p>"
        f"<p>— SLYK Casino</p>"
    )

    msg = EmailMultiAlternatives(subject, text_body, from_email, to)
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)


def send_password_reset_email(user, uid: str, token: str) -> None:
    """Send password-reset link to the user."""
    reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    subject = "Reset your SLYK Casino password"
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [user.email]

    text_body = (
        f"Hi {user.username},\n\n"
        f"Click the link below to reset your password:\n\n"
        f"{reset_url}\n\n"
        f"This link expires in 1 hour. If you did not request a reset, ignore this email.\n\n"
        f"-- SLYK Casino"
    )
    html_body = (
        f"<p>Hi <strong>{user.username}</strong>,</p>"
        f"<p>Click the link below to reset your password:</p>"
        f'<p><a href="{reset_url}">{reset_url}</a></p>'
        f"<p>This link expires in 1 hour. If you did not request a reset, ignore this email.</p>"
        f"<p>— SLYK Casino</p>"
    )

    msg = EmailMultiAlternatives(subject, text_body, from_email, to)
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)


def send_welcome_email(player) -> None:
    """Send a welcome email after email verification."""
    subject = "Welcome to SLYK Casino!"
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [player.email]

    text_body = (
        f"Hi {player.username},\n\n"
        f"Your email has been verified. Welcome to SLYK Casino!\n\n"
        f"Log in and start playing at {settings.FRONTEND_URL}\n\n"
        f"-- SLYK Casino"
    )
    html_body = (
        f"<p>Hi <strong>{player.username}</strong>,</p>"
        f"<p>Your email has been verified. Welcome to <strong>SLYK Casino</strong>!</p>"
        f'<p><a href="{settings.FRONTEND_URL}">Log in and start playing</a></p>'
        f"<p>— SLYK Casino</p>"
    )

    msg = EmailMultiAlternatives(subject, text_body, from_email, to)
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)
