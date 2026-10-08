"""sportsbook external interfaces — normalize an odds-feed provider into DTOs."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import requests
from django.conf import settings

from .market_feed import FeedMarketData, parse_live_odds, parse_markets

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
class FixtureLeague:
    """The competition a fixture belongs to (from the fixture payload)."""

    external_id: int
    name: str
    country: str = ''
    logo_url: str = ''
    flag_url: str = ''


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
    ht_home: Optional[int] = None
    ht_away: Optional[int] = None
    ft_home: Optional[int] = None
    ft_away: Optional[int] = None
    elapsed: Optional[int] = None
    # Post-match facts (corners, cards, goal events, participants) when the
    # payload carried them — see normalize_facts. Same shape as Event.match_facts.
    facts: Optional[dict] = None
    league: Optional[FixtureLeague] = None

    @property
    def is_finished(self) -> bool:
        return self.status in FINISHED_STATUSES

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES

    @property
    def regulation_score(self) -> tuple[Optional[int], Optional[int]]:
        """90-minute score: api-football's `score.fulltime` when present (it
        excludes extra time), else the running `goals` total."""
        if self.ft_home is not None and self.ft_away is not None:
            return self.ft_home, self.ft_away
        return self.goals_home, self.goals_away

    @property
    def result(self) -> Optional[str]:
        """'home'|'draw'|'away' once finished (on the 90-minute score), else None."""
        home, away = self.regulation_score
        if not self.is_finished or home is None or away is None:
            return None
        if home > away:
            return 'home'
        if home < away:
            return 'away'
        return 'draw'


def _side_resolver(raw: dict[str, Any]):
    teams = raw.get('teams') or {}
    home_id = (teams.get('home') or {}).get('id')
    away_id = (teams.get('away') or {}).get('id')

    def side(team: Optional[dict[str, Any]]) -> Optional[str]:
        tid = (team or {}).get('id')
        if tid is not None and tid == home_id:
            return 'home'
        if tid is not None and tid == away_id:
            return 'away'
        return None
    return side


def normalize_facts(raw: dict[str, Any]) -> Optional[dict]:
    """Corners, cards, goal events and participants from an api-football fixture
    record (present when fetched by id). Returns None if the record has none of
    them. Goals after 90' (extra time) are dropped — markets settle on 90 minutes.
    Own goals are credited to the benefiting team; if the feed's attribution
    doesn't add up to the score, the other convention is tried (see settlement)."""
    events = raw.get('events')
    statistics = raw.get('statistics')
    lineups = raw.get('lineups')
    if not events and not statistics and not lineups:
        return None
    side = _side_resolver(raw)
    status = str(((raw.get('fixture') or {}).get('status') or {}).get('short', ''))
    facts: dict[str, Any] = {'extra_time': status in ('AET', 'PEN')}

    if statistics:
        per_side: dict[str, dict[str, int]] = {}
        for block in statistics:
            s = side(block.get('team'))
            if s is None:
                continue
            values = {str(st.get('type')): st.get('value') for st in block.get('statistics') or []}
            per_side[s] = {
                'corners': int(values.get('Corner Kicks') or 0),
                'yellow': int(values.get('Yellow Cards') or 0),
                'red': int(values.get('Red Cards') or 0),
            }
        if 'home' in per_side and 'away' in per_side:
            for key in ('corners', 'yellow', 'red'):
                facts[key] = [per_side['home'][key], per_side['away'][key]]

    if events is not None:
        goals = []
        for ev in events:
            if str(ev.get('type')) != 'Goal' or str(ev.get('detail')) == 'Missed Penalty':
                continue
            time = ev.get('time') or {}
            elapsed = int(time.get('elapsed') or 0)
            if elapsed > 90:
                continue  # extra time
            team_side = side(ev.get('team'))
            if team_side is None:
                continue
            goals.append({
                'minute': elapsed, 'extra': int(time.get('extra') or 0), 'side': team_side,
                'player': str((ev.get('player') or {}).get('name') or ''),
                'own_goal': str(ev.get('detail')) == 'Own Goal',
                'penalty': str(ev.get('detail')) == 'Penalty',
            })
        goals.sort(key=lambda g: (g['minute'], g['extra']))
        facts['goals'] = goals

    if lineups:
        names: list[str] = []
        for team in lineups:
            for entry in team.get('startXI') or []:
                name = (entry.get('player') or {}).get('name')
                if name:
                    names.append(str(name))
        # Substitutions name both players; whoever came on took part.
        for ev in events or []:
            if str(ev.get('type')).lower() == 'subst':
                for who in (ev.get('player'), ev.get('assist')):
                    name = (who or {}).get('name')
                    if name:
                        names.append(str(name))
        facts['participants'] = sorted(set(names))
    return facts


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

    def fetch_status(self) -> dict:
        """Account, plan and today's request quota (api-football /status).
        Raises ValueError with a readable message on any failure."""
        if not self.api_key:
            raise ValueError('No API key is set.')
        try:
            resp = requests.get(
                f'{self.base_url}/status', timeout=8, headers={'x-apisports-key': self.api_key},
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise ValueError(f'Could not reach api-football ({exc.__class__.__name__}).') from exc
        except ValueError as exc:
            raise ValueError('api-football returned an unreadable response.') from exc
        errors = payload.get('errors')
        if errors:
            message = '; '.join(str(v) for v in (errors.values() if isinstance(errors, dict) else errors))
            raise ValueError(message or 'api-football rejected the key.')
        response = payload.get('response') or {}
        account = response.get('account') or {}
        subscription = response.get('subscription') or {}
        requests_ = response.get('requests') or {}
        return {
            'account': ' '.join(filter(None, [account.get('firstname'), account.get('lastname')])) or account.get('email', ''),
            'email': account.get('email', ''),
            'plan': subscription.get('plan', ''),
            'active': bool(subscription.get('active')),
            'ends': subscription.get('end'),
            'requests_today': requests_.get('current'),
            'requests_limit': requests_.get('limit_day'),
        }

    def fetch_fixtures(
        self, *, date: Optional[str] = None, live: Optional[str] = None,
        league: Optional[int] = None, season: Optional[int] = None, next_count: Optional[int] = None,
    ) -> list[FixtureUpdate]:
        """`date` is 'YYYY-MM-DD'; `live='all'` fetches all in-play fixtures;
        `next_count` fetches the next N upcoming fixtures for `league`/`season`
        (api-football's own `next` lookahead query — no date needed).
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
        if next_count:
            params['next'] = next_count
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

    def fetch_fixtures_by_ids(self, ids: list[str]) -> list[FixtureUpdate]:
        """Full fixture records (score, status, events, statistics, lineups) for
        specific fixtures — what post-match settlement needs. api-football takes
        up to 20 ids per call. Returns what it could fetch; errors are logged."""
        if not self.api_key or not ids:
            return []
        fixtures: list[FixtureUpdate] = []
        for start in range(0, len(ids), 20):
            chunk = [i for i in ids[start:start + 20] if i]
            try:
                resp = requests.get(
                    f'{self.base_url}/fixtures', params={'ids': '-'.join(chunk)}, timeout=10,
                    headers={'x-apisports-key': self.api_key},
                )
                resp.raise_for_status()
                payload = resp.json()
            except (requests.RequestException, ValueError):
                logger.warning('api-football fetch_fixtures_by_ids failed', exc_info=True)
                continue
            fixtures.extend(self._normalize(raw) for raw in payload.get('response', []))
        return fixtures

    def fetch_odds(
        self, *, date: Optional[str] = None, fixture: Optional[str] = None,
        league: Optional[int] = None, season: Optional[int] = None,
    ) -> list['OddsSnapshot']:
        """Pull odds (1X2 + every other market). `date` is 'YYYY-MM-DD'.

        api-football pages this endpoint (10 fixtures per page), so every page is
        followed up to API_FOOTBALL_ODDS_MAX_PAGES — reading only page 1 misses
        almost every fixture on a busy date. Returns what it could fetch; errors
        are logged, never raised."""
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
        max_pages = int(getattr(settings, 'API_FOOTBALL_ODDS_MAX_PAGES', 20))
        snapshots = []
        page, total = 1, 1
        while page <= min(total, max_pages):
            try:
                resp = requests.get(
                    f'{self.base_url}/odds', params={**params, 'page': page}, timeout=10,
                    headers={'x-apisports-key': self.api_key},
                )
                resp.raise_for_status()
                payload = resp.json()
            except (requests.RequestException, ValueError):
                logger.warning('api-football fetch_odds failed (page %s)', page, exc_info=True)
                break
            if payload.get('errors'):
                # e.g. quota exhausted or a bad parameter — api-football reports
                # these with HTTP 200, so surface them instead of failing silently.
                logger.warning('api-football fetch_odds errors: %s', payload.get('errors'))
                break
            for raw in payload.get('response', []):
                snapshot = self._normalize_odds(raw)
                if snapshot is not None:
                    snapshots.append(snapshot)
            total = int((payload.get('paging') or {}).get('total') or 1)
            page += 1
        return snapshots

    def fetch_live_odds(self) -> list['LiveOddsSnapshot']:
        """In-play odds for every live fixture api-football prices (one call,
        refreshed by the provider every few seconds). Returns [] (logged) on any
        missing key, network, or payload error."""
        if not self.api_key:
            return []
        try:
            resp = requests.get(
                f'{self.base_url}/odds/live', timeout=5, headers={'x-apisports-key': self.api_key},
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError):
            logger.warning('api-football fetch_live_odds failed', exc_info=True)
            return []
        if payload.get('errors'):
            logger.warning('api-football fetch_live_odds errors: %s', payload.get('errors'))
            return []
        snapshots = []
        for raw in payload.get('response', []):
            snapshot = self._normalize_live_odds(raw)
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots

    def _normalize_live_odds(self, raw: dict[str, Any]) -> Optional['LiveOddsSnapshot']:
        fixture = raw.get('fixture') or {}
        fixture_id = str(fixture.get('id', '') or '')
        if not fixture_id:
            return None
        status = fixture.get('status') or {}
        long_status = str(status.get('long') or '')
        teams = raw.get('teams') or {}
        flags = raw.get('status') or {}
        first_half = long_status.strip().lower() in ('first half', '1st half')
        one_x_two, markets = parse_live_odds(raw.get('odds') or [], first_half=first_half)

        def goals(side: str) -> Optional[int]:
            value = (teams.get(side) or {}).get('goals')
            return int(value) if isinstance(value, (int, float)) or str(value).isdigit() else None

        elapsed = status.get('elapsed')
        return LiveOddsSnapshot(
            external_id=fixture_id,
            status=long_status,
            elapsed=int(elapsed) if isinstance(elapsed, (int, float)) else None,
            goals_home=goals('home'),
            goals_away=goals('away'),
            blocked=bool(flags.get('blocked') or flags.get('stopped') or flags.get('finished')),
            one_x_two=one_x_two,
            markets=tuple(markets),
        )

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
        score = raw.get('score') or {}
        halftime = score.get('halftime') or {}
        fulltime = score.get('fulltime') or {}
        status = fixture.get('status') or {}
        return FixtureUpdate(
            external_id=str(fixture.get('id', '')),
            name=f'{home} vs {away}',
            status=str(status.get('short', 'NS')),
            starts_at=starts_at,
            goals_home=goals.get('home'),
            goals_away=goals.get('away'),
            home_team=self._normalize_team(teams.get('home')),
            away_team=self._normalize_team(teams.get('away')),
            ht_home=halftime.get('home'),
            ht_away=halftime.get('away'),
            ft_home=fulltime.get('home'),
            ft_away=fulltime.get('away'),
            elapsed=status.get('elapsed'),
            facts=normalize_facts(raw),
            league=self._normalize_fixture_league(raw.get('league')),
        )

    def _normalize_fixture_league(self, raw: Optional[dict[str, Any]]) -> Optional[FixtureLeague]:
        if not raw or raw.get('id') is None:
            return None
        try:
            league_id = int(raw['id'])
        except (TypeError, ValueError):
            return None
        return FixtureLeague(
            external_id=league_id, name=str(raw.get('name') or ''),
            country=str(raw.get('country') or ''), logo_url=str(raw.get('logo') or ''),
            flag_url=str(raw.get('flag') or ''),
        )

    def _normalize_team(self, raw: Optional[dict[str, Any]]) -> Optional[TeamInfo]:
        if not raw or raw.get('id') is None:
            return None
        return TeamInfo(
            external_id=str(raw['id']), name=str(raw.get('name', '')),
            logo_url=str(raw.get('logo', '') or ''),
        )

    def fetch_leagues(self) -> list['LeagueInfo']:
        """Discover every league api-football currently has an active ("current")
        season for, so fixture import doesn't depend on operator-curated league
        IDs. One API call, but the caller still pays one /fixtures call per
        league returned here — see import_all_current_leagues. Returns []
        (logged) on any missing key, network, or payload error."""
        if not self.api_key:
            return []
        try:
            resp = requests.get(
                f'{self.base_url}/leagues', params={'current': 'true'}, timeout=10,
                headers={'x-apisports-key': self.api_key},
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError):
            logger.warning('api-football fetch_leagues failed', exc_info=True)
            return []
        leagues = []
        for raw in payload.get('response', []):
            league_info = self._normalize_league(raw)
            if league_info is not None:
                leagues.append(league_info)
        return leagues

    def _normalize_league(self, raw: dict[str, Any]) -> Optional['LeagueInfo']:
        league = raw.get('league') or {}
        league_id = league.get('id')
        if league_id is None:
            return None
        season_year = None
        for season in raw.get('seasons', []):
            if season.get('current'):
                season_year = season.get('year')
                break
        if season_year is None:
            return None
        return LeagueInfo(id=int(league_id), season=int(season_year), name=str(league.get('name', '')))

    def _normalize_odds(self, raw: dict[str, Any]) -> Optional['OddsSnapshot']:
        """1X2 prices from the first bookmaker offering "Match Winner", plus every
        other bet type (each taken from the first bookmaker that offers it) parsed
        into markets — see parse_markets."""
        fixture_id = str((raw.get('fixture') or {}).get('id', ''))
        if not fixture_id:
            return None
        snapshot: Optional[OddsSnapshot] = None
        bets_by_name: dict[str, dict[str, Any]] = {}
        for bookmaker in raw.get('bookmakers', []):
            for bet in bookmaker.get('bets', []):
                name = bet.get('name')
                if name and name not in bets_by_name:
                    bets_by_name[name] = bet
                if snapshot is not None or name != 'Match Winner':
                    continue
                prices = {v.get('value'): v.get('odd') for v in bet.get('values', [])}
                home, draw, away = prices.get('Home'), prices.get('Draw'), prices.get('Away')
                if home is None or away is None:
                    continue
                try:
                    snapshot = OddsSnapshot(
                        external_id=fixture_id,
                        odds_home=Decimal(str(home)),
                        odds_draw=Decimal(str(draw)) if draw is not None else None,
                        odds_away=Decimal(str(away)),
                    )
                except (ValueError, ArithmeticError):
                    continue
        if snapshot is None:
            return None
        include_manual = getattr(settings, 'SPORTSBOOK_IMPORT_MANUAL_MARKETS', False)
        markets = parse_markets(list(bets_by_name.values()), include_manual=include_manual)
        return OddsSnapshot(
            external_id=snapshot.external_id, odds_home=snapshot.odds_home,
            odds_draw=snapshot.odds_draw, odds_away=snapshot.odds_away, markets=tuple(markets),
        )


@dataclass(frozen=True)
class OddsSnapshot:
    """Normalized 1X2 ("Match Winner") prices for one fixture, from the first
    bookmaker offering that market in the response, plus its other markets."""

    external_id: str
    odds_home: Decimal
    odds_draw: Optional[Decimal]
    odds_away: Decimal
    # Every other market the feed offers for this fixture (goals, handicaps…).
    markets: tuple['FeedMarketData', ...] = ()


@dataclass(frozen=True)
class LiveOddsSnapshot:
    """One fixture from the in-play odds feed. `blocked` means the provider has
    stopped trading it (a goal/VAR check, stoppage, or the final whistle)."""

    external_id: str
    status: str
    elapsed: Optional[int]
    goals_home: Optional[int]
    goals_away: Optional[int]
    blocked: bool
    one_x_two: Optional[tuple[Decimal, Optional[Decimal], Decimal]]
    markets: tuple['FeedMarketData', ...] = ()


@dataclass(frozen=True)
class LeagueInfo:
    """A league api-football currently has an active season for, with that
    season's year — leagues each run on their own season numbering, so this
    travels with the ID rather than relying on a single global season."""

    id: int
    season: int
    name: str = ''
