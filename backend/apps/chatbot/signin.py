"""Logging in and signing up in the chat with the website's own details.

LOGIN asks for the username (or email), then the password, and checks them
exactly as the website's login does. REGISTER asks for the agent code (checked
against active agents), a username, the 18+ / terms confirmation, and last the
password, so the account is created the moment the password arrives and the
password is never kept anywhere: the same account then works on the website.

A message that answers "send your password" is stored hidden (views.handle_inbound),
so passwords never show in the staff inbox. Each step waits up to 10 minutes;
CANCEL, MENU or BACK leave the flow.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from . import services

FLOW_FOR = timedelta(minutes=10)
ESCAPES = {'CANCEL', 'NO', 'MENU', 'BACK', 'STOP', 'EXIT', 'QUIT'}
DELETE_HINT = '💡 For your safety, delete your password message from this chat (long-press it → Delete for me).'


class SignInMixin:
    """Mixed into engine.Conversation."""

    # -- running a flow ------------------------------------------------------------------
    def _flow(self) -> tuple[str, dict] | tuple[None, None]:
        for key in ('signin', 'signup'):
            f = self.state.get(key)
            if isinstance(f, dict):
                if timezone.datetime.fromisoformat(f['expires']) < self.now:
                    self.state.pop(key, None)
                    continue
                return key, f
        return None, None

    def _step(self, key: str, step: str, **data) -> None:
        f = self.state.get(key) if isinstance(self.state.get(key), dict) else {}
        self.state[key] = {**f, **data, 'step': step, 'expires': (self.now + FLOW_FOR).isoformat()}

    def in_flow(self, text: str):
        """If a log-in or sign-up question is waiting, this message answers it (returns replies), else None."""
        key, f = self._flow()
        if key is None:
            return None
        word = text.strip().upper()
        if word in ESCAPES:
            self.state.pop(key, None)
            return None if word in ('MENU', 'BACK') else [self._r('Cancelled.', 'MENU')]
        return self._signin_step(f, text) if key == 'signin' else self._signup_step(f, text)

    @staticmethod
    def _r(text: str, *buttons):
        from .engine import _reply
        return _reply(text, *buttons)

    # -- logging in -----------------------------------------------------------------------
    def login(self, args: list[str]) -> list[dict]:
        """LOGIN, LOGIN <username>, or LOGIN <username> <password> in one message."""
        if self.logged_in:
            return [self._r('You are already logged in.', 'MENU')]
        self.state.pop('signup', None)
        if len(args) >= 2:
            return self._try_login(args[0], ' '.join(args[1:]))
        if len(args) == 1:
            self._step('signin', 'password', username=args[0])
            return [self._password_prompt()]
        self._step('signin', 'username')
        from .engine import _site
        return [self._r(f'👤 *Log in* with your {_site()} website details.\n\nSend your *username* (or email).',
                        ['CANCEL', '✖ Cancel'])]

    def _password_prompt(self):
        return self._r('🔑 Now send your *password*.\n\nWe hide it from our records. Delete it from this chat afterwards.',
                       ['CANCEL', '✖ Cancel'])

    def _signin_step(self, f: dict, text: str) -> list[dict]:
        if f['step'] == 'username':
            self._step('signin', 'password', username=text.strip())
            return [self._password_prompt()]
        username = f.get('username', '')
        self.state.pop('signin', None)
        return self._try_login(username, text.strip())

    def _try_login(self, username: str, password: str) -> list[dict]:
        try:
            player = services.password_login(self.address, username, password)
            from apps.accounts import services as accounts
            accounts.check_responsible_gambling(player)
        except (services.ChatError, ValueError) as exc:
            return [self._r(f'🔒 {exc}', ['LOGIN', '🔓 Try again'], 'MENU')]
        return self._logged_in(player, f'✅ Logged in as *{player.username}*.')

    def _logged_in(self, player, head: str) -> list[dict]:
        self.link = services.attach(self.address, player.id, channel=self.channel)
        self._start_session()
        from apps.accounts import services as accounts
        accounts.audit(player.id, 'chat_login', None, number=f'…{self.address[-4:]}')
        from apps.notifications import services as notes
        notes.notify(player_id=player.id, kind='account_alert', title='WhatsApp login',
                     body=f'WhatsApp …{self.address[-4:]} logged in to your account. Not you? Change your password now.')
        return [self._r(f'{head} You stay logged in while you keep chatting; after {self.cfg.session_minutes} minutes '
                        f'without a message you are logged out. Send *LOGOUT* when you are done.\n\n{DELETE_HINT}',
                        'MENU', ['ACCOUNT', '👤 My account'])]

    # -- signing up ------------------------------------------------------------------------
    def register(self) -> list[dict]:
        from apps.accounts import signup
        if self.logged_in:
            return [self._r('You are already logged in to an account.', 'MENU')]
        self.state.pop('signin', None)
        from .engine import _site
        if signup.agent_code_required():
            self._step('signup', 'code')
            return [self._r(f'📝 *Create your {_site()} account*\n\nStep 1 of 4: send your *agent code*. '
                            'You need one to register: ask your agent.', ['CANCEL', '✖ Cancel'])]
        self._step('signup', 'code')
        return [self._r(f'📝 *Create your {_site()} account*\n\nStep 1 of 4: send your *agent code*, or SKIP if you '
                        'don’t have one.', ['SKIP', 'Skip'], ['CANCEL', '✖ Cancel'])]

    def _signup_step(self, f: dict, text: str) -> list[dict]:
        from apps.accounts import signup
        value = text.strip()
        step = f['step']
        if step == 'code':
            code = '' if value.upper() == 'SKIP' else value
            try:
                agent = signup.check_agent_code(code)
            except signup.SignupError as exc:
                return [self._r(f'⚠️ {exc} Send the code again, or CANCEL.', ['CANCEL', '✖ Cancel'])]
            self._step('signup', 'username', agent_code=agent.code if agent else '')
            return [self._r('✅ Agent code accepted.\n\nStep 2 of 4: choose a *username* (letters, numbers or _, '
                            'at least 3). You will use it on the website too.' if agent else
                            'Step 2 of 4: choose a *username* (letters, numbers or _, at least 3).', ['CANCEL', '✖ Cancel'])]
        if step == 'username':
            problem = self._username_problem(value)
            if problem:
                return [self._r(f'⚠️ {problem} Try another username.', ['CANCEL', '✖ Cancel'])]
            from apps.accounts import utils as account_utils
            self._step('signup', 'terms', username=account_utils.normalize_username(value))
            from .menus import site_url
            return [self._r(f'Step 3 of 4: confirm you are *18 or older* and accept our terms '
                            f'({site_url("/legal/terms")}).', ['YES', '✅ I am 18+ and agree'], ['CANCEL', '✖ Cancel'])]
        if step == 'terms':
            if value.upper() not in ('YES', 'Y', 'AGREE', 'I AGREE'):
                return [self._r('You must be 18 or older and accept the terms to register.', ['YES', '✅ I am 18+ and agree'],
                                ['CANCEL', '✖ Cancel'])]
            self._step('signup', 'password')
            return [self._r('Step 4 of 4: send the *password* you want (at least 8 characters). You will use it on the '
                            'website too.\n\nWe hide it from our records. Delete it from this chat afterwards.',
                            ['CANCEL', '✖ Cancel'])]
        # step == 'password': create the account now; the password is never stored anywhere.
        if not 8 <= len(value) <= 128:
            return [self._r('⚠️ Use a password of 8 to 128 characters. Send it again.', ['CANCEL', '✖ Cancel'])]
        self.state.pop('signup', None)
        try:
            player = signup.sign_up(username=f['username'], email='', password=value, agent_code=f.get('agent_code', ''),
                                    source='whatsapp')
        except signup.SignupError as exc:
            return [self._r(f'⚠️ {exc} Send REGISTER to start again.', ['REGISTER', '📝 Register'], 'MENU')]
        from .engine import _site
        return self._logged_in(player, f'🎉 Welcome to {_site()}, *{player.username}*! Your account is ready. '
                                       'Log in on the website with the same username and password.')

    @staticmethod
    def _username_problem(value: str) -> str:
        from django.contrib.auth import get_user_model
        from apps.accounts import utils as account_utils
        name = account_utils.normalize_username(value)
        if len(name) < 3 or len(value) > 30:
            return 'Use 3 to 30 letters, numbers or underscores.'
        if get_user_model().objects.filter(username__iexact=name).exists():
            return 'That username is taken.'
        return ''
