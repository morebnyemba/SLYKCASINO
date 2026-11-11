import pytest


@pytest.fixture(autouse=True)
def _any_odds_from_any_wallet(request, django_db_blocker):
    """Most tests are about other features: let any wallet bet at any odds.
    The wallet rules have their own tests, marked `wallet_rules`, which keep
    the real minimums. (Only database tests can bet, so only they're touched.)"""
    from django.test import TransactionTestCase

    cls = request.node.cls
    if request.node.get_closest_marker('wallet_rules') or not (cls and issubclass(cls, TransactionTestCase)):
        return
    from apps.wallet.models import WalletRules
    with django_db_blocker.unblock():
        WalletRules.objects.update_or_create(pk=1, defaults={
            'deposit_min_odds': 1, 'bonus_min_odds': 1, 'winnings_min_odds': 1,
        })


@pytest.fixture(autouse=True)
def _manual_affiliate_payouts(request, django_db_blocker):
    """Most tests cover the affiliate balance, approvals and payout requests, so
    they run with automatic approval and payout off. Tests of the automatic
    flow (the programme default) are marked `affiliate_auto`."""
    from django.test import TransactionTestCase

    cls = request.node.cls
    if request.node.get_closest_marker('affiliate_auto') or not (cls and issubclass(cls, TransactionTestCase)):
        return
    from apps.affiliates.models import AffiliateProgramme
    with django_db_blocker.unblock():
        AffiliateProgramme.load()
        AffiliateProgramme.objects.filter(pk=1).update(auto_payout=False, auto_approve_commissions=False)


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """Rate-limit counters live in the cache and test user ids repeat, so
    start every test with none."""
    from django.core.cache import cache
    cache.clear()
