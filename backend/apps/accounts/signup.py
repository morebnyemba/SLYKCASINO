"""Creating an account: the one path the website and WhatsApp both use.

A valid agent code is mandatory while the affiliate programme's
`require_agent_code` is on (a superuser switch): no code, no account. The
account and its referral are created together, so a player can never end up
registered without the agent who brought them.
"""
from __future__ import annotations

from typing import Optional

from django.db import IntegrityError, transaction

from . import services


class SignupError(ValueError):
    """Why the account can't be created; `field` names the form field it belongs to."""

    def __init__(self, message: str, field: str = 'detail'):
        super().__init__(message)
        self.field = field


def agent_code_required() -> bool:
    from apps.affiliates.models import AffiliateProgramme
    return AffiliateProgramme.load().require_agent_code


def check_agent_code(code: str):
    """The active agent for `code`, None when no code was given and none is needed, or SignupError."""
    from apps.affiliates import services as affiliates
    code = (code or '').strip()
    if not code:
        if agent_code_required():
            raise SignupError('An agent code is required to register. Ask your agent for theirs.', 'agent_code')
        return None
    agent = affiliates.get_active_by_code(code)
    if agent is None:
        raise SignupError('That agent code isn’t valid. Check it with your agent.', 'agent_code')
    return agent


@transaction.atomic
def sign_up(*, username: str, email: str, password: str, agent_code: str = '', campaign: str = '',
            request=None, source: str = 'web'):
    """Create the player (and their referral to the agent). Raises SignupError."""
    agent = check_agent_code(agent_code)
    try:
        player = services.register_player(username=username, email=email or '', password=password)
    except IntegrityError as exc:
        raise SignupError('username or email already registered') from exc
    except ValueError as exc:
        raise SignupError(str(exc)) from exc
    if agent is not None:
        from apps.affiliates import services as affiliates
        if affiliates.attach_referral(player_id=player.id, code=agent.code, campaign=campaign) is None and agent_code_required():
            raise SignupError('That agent code can’t be used for this account.', 'agent_code')
    services.audit(player.id, 'register', request, source=source, agent=agent.code if agent else '')
    from apps.risk import services as risk
    from common.client_ip import client_ip
    risk.safely(risk.on_register, player.id, client_ip(request) if request else '')
    return player
