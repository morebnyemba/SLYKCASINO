"""sportsbook external interfaces — normalize an odds-feed provider into DTOs."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedMarket:
    external_id: str
    name: str
    odds: Decimal
    is_open: bool


class OddsFeedClient:
    """Interface to an external odds/results provider.

    `fetch_markets` returns normalized markets; `fetch_result` returns a settled
    outcome. Concrete HTTP omitted — the point is provider payloads are
    normalized here so services never see vendor-specific shapes.
    """

    provider_name = 'stub-odds'

    def fetch_markets(self) -> list[FeedMarket]:
        return [self._normalize(m) for m in self._call_markets()]

    def fetch_result(self, external_id: str) -> str:
        """Return 'won'|'lost'|'void'|'pending' for a market."""
        return self._call_result(external_id).get('outcome', 'pending')

    # -- internals ---------------------------------------------------------
    def _call_markets(self) -> list[dict[str, Any]]:
        return []

    def _call_result(self, external_id: str) -> dict[str, Any]:
        return {'outcome': 'pending'}

    def _normalize(self, raw: dict[str, Any]) -> FeedMarket:
        return FeedMarket(
            external_id=str(raw.get('id', '')),
            name=str(raw.get('name', '')),
            odds=Decimal(str(raw.get('odds', '1.95'))),
            is_open=bool(raw.get('open', True)),
        )


# -- api-football.com (https://www.api-football.com/documentation-v3) -------

FINISHED_STATUSES = {'FT', 'AET', 'PEN'}
LIVE_STATUSES = {'1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT'}


@dataclass(frozen=True)
class TeamInfo:
    external_id: str
    name: str
    logo_url: str = ''


@dataclass(frozen=True)
class FixtureUpdate:
    """A normalized api-football fixture, used to sync/settle a linked Event."""

    external_id: str
    name: str
    status: str
    starts_at: Optional[datetime]
    goals_home: Optional[int]
    goals_away: Optional[int]
    home_team: Optional[TeamInfo] = None
    away_team: Optional[TeamInfo] = None

    @property
    def is_finished(self) -> bool:
        return self.status in FINISHED_STATUSES

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES

    @property
    def result(self) -> Optional[str]:
        """'home'|'draw'|'away' once finished, else None."""
        if not self.is_finished or self.goals_home is None or self.goals_away is None:
            return None
        if self.goals_home > self.goals_away:
            return 'home'
        if self.goals_home < self.goals_away:
            return 'away'
        return 'draw'


class ApiFootballClient:
    """Thin client for api-football.com v3 — fetches fixtures (live scores,
    statuses, results) used to keep linked Events and bets in sync.

    The API key/base URL can be set either via a `ProviderCredential` row in
    Django admin (lets ops rotate a key without a redeploy) or via the
    API_FOOTBALL_KEY/API_FOOTBALL_BASE_URL env vars — the admin row wins when
    both are present. Either way, missing credentials make this a no-op
    (returns an empty list, never raises into callers), matching the rest of
    this app's pattern of safe-by-default external integrations.
    """

    provider_name = 'api-football'

    def __init__(self) -> None:
        credential = self._load_credential()
        self.api_key = (
            (credential.api_key if credential else '')
            or getattr(settings, 'API_FOOTBALL_KEY', '') or ''
        )
        base_url = (
            (credential.base_url if credential else '')
            or getattr(settings, 'API_FOOTBALL_BASE_URL', 'https://v3.football.api-sports.io')
        )
        self.base_url = base_url.rstrip('/')

    def _load_credential(self):
        from .models import ProviderCredential
        try:
            return ProviderCredential.objects.filter(provider=self.provider_name).first()
        except Exception:  # noqa: BLE001 — table may not exist yet (pre-migrate)
            return None

    def fetch_fixtures(
        self, *, date: Optional[str] = None, live: Optional[str] = None,
        league: Optional[int] = None, season: Optional[int] = None,
    ) -> list[FixtureUpdate]:
        """`date` is 'YYYY-MM-DD'; `live='all'` fetches all in-play fixtures.
        Returns [] (logged) on any missing key, network, or payload error."""
        if not self.api_key:
            return []
        params: dict[str, Any] = {}
        if date:
            params['date'] = date
        if live:
            params['live'] = live
        if league:
            params['league'] = league
        if season:
            params['season'] = season
        try:
            resp = requests.get(
                f'{self.base_url}/fixtures', params=params, timeout=5,
                headers={'x-apisports-key': self.api_key},
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError):
            logger.warning('api-football fetch_fixtures failed', exc_info=True)
            return []
        return [self._normalize(raw) for raw in payload.get('response', [])]

    def fetch_odds(
        self, *, date: Optional[str] = None, fixture: Optional[str] = None,
        league: Optional[int] = None, season: Optional[int] = None,
    ) -> list['OddsSnapshot']:
        """Pull 1X2 ("Match Winner") odds. `date` is 'YYYY-MM-DD'. Returns []
        (logged) on any missing key, network, or payload error."""
        if not self.api_key:
            return []
        params: dict[str, Any] = {}
        if date:
            params['date'] = date
        if fixture:
            params['fixture'] = fixture
        if league:
            params['league'] = league
        if season:
            params['season'] = season
        try:
            resp = requests.get(
                f'{self.base_url}/odds', params=params, timeout=5,
                headers={'x-apisports-key': self.api_key},
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError):
            logger.warning('api-football fetch_odds failed', exc_info=True)
            return []
        snapshots = []
        for raw in payload.get('response', []):
            snapshot = self._normalize_odds(raw)
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots

    def _normalize(self, raw: dict[str, Any]) -> FixtureUpdate:
        fixture = raw.get('fixture', {})
        teams = raw.get('teams', {})
        goals = raw.get('goals', {})
        home = (teams.get('home') or {}).get('name', '')
        away = (teams.get('away') or {}).get('name', '')
        starts_at = None
        date_str = fixture.get('date')
        if date_str:
            try:
                starts_at = datetime.fromisoformat(date_str)
            except ValueError:
                starts_at = None
        return FixtureUpdate(
            external_id=str(fixture.get('id', '')),
            name=f'{home} vs {away}',
            status=str((fixture.get('status') or {}).get('short', 'NS')),
            starts_at=starts_at,
            goals_home=goals.get('home'),
            goals_away=goals.get('away'),
            home_team=self._normalize_team(teams.get('home')),
            away_team=self._normalize_team(teams.get('away')),
        )

    def _normalize_team(self, raw: Optional[dict[str, Any]]) -> Optional[TeamInfo]:
        if not raw or raw.get('id') is None:
            return None
        return TeamInfo(
            external_id=str(raw['id']), name=str(raw.get('name', '')),
            logo_url=str(raw.get('logo', '') or ''),
        )

    def _normalize_odds(self, raw: dict[str, Any]) -> Optional['OddsSnapshot']:
        fixture_id = str((raw.get('fixture') or {}).get('id', ''))
        if not fixture_id:
            return None
        for bookmaker in raw.get('bookmakers', []):
            for bet in bookmaker.get('bets', []):
                if bet.get('name') != 'Match Winner':
                    continue
                prices = {v.get('value'): v.get('odd') for v in bet.get('values', [])}
                home, draw, away = prices.get('Home'), prices.get('Draw'), prices.get('Away')
                if home is None or away is None:
                    continue
                try:
                    return OddsSnapshot(
                        external_id=fixture_id,
                        odds_home=Decimal(str(home)),
                        odds_draw=Decimal(str(draw)) if draw is not None else None,
                        odds_away=Decimal(str(away)),
                    )
                except (ValueError, ArithmeticError):
                    continue
        return None


@dataclass(frozen=True)
class OddsSnapshot:
    """Normalized 1X2 ("Match Winner") prices for one fixture, from the first
    bookmaker offering that market in the response."""

    external_id: str
    odds_home: Decimal
    odds_draw: Optional[Decimal]
    odds_away: Decimal
