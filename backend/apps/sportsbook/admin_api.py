"""Operator console API for the sportsbook (staff only): the api-football
connection, the league catalogue, and hand-managed matches.

Everything here is IsAdminUser. Writes go through the models' normal save so
realtime publishing (post_save) and previous-odds tracking keep working.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .clients import ApiFootballClient
from .models import Bet, BetLeg, Event, LeagueSetting, Market, ProviderCredential, Team
from .services import FINISHED_STATUSES, LIVE_STATUSES, VOID_STATUSES, trading_state

PROVIDER = ApiFootballClient.provider_name


class AdminPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


# -- feed connection ------------------------------------------------------------

def _key_hint(key: str) -> str:
    return f'••••{key[-4:]}' if len(key) >= 8 else ('••••' if key else '')


# The api-football jobs an operator can run on demand (Celery task names).
SYNC_JOBS = {
    'import_fixtures': ('apps.sportsbook.tasks.import_upcoming_fixtures', 'Import upcoming fixtures'),
    'sync_odds': ('apps.sportsbook.tasks.sync_fixture_odds', 'Refresh pre-match odds'),
    'sync_live': ('apps.sportsbook.tasks.sync_live_fixtures', 'Refresh live scores'),
    'sync_live_odds': ('apps.sportsbook.tasks.sync_live_odds', 'Refresh in-play odds'),
    'settle_finished': ('apps.sportsbook.tasks.settle_finished_fixtures', 'Settle finished matches'),
}


def _feed_summary() -> dict:
    from django.conf import settings

    credential = ProviderCredential.objects.filter(provider=PROVIDER).first()
    db_key = (credential.api_key if credential else '') or ''
    env_key = getattr(settings, 'API_FOOTBALL_KEY', '') or ''
    key = db_key or env_key
    db_url = (credential.base_url if credential else '') or ''
    now = timezone.now()
    events = Event.objects.all()
    schedules = []
    try:
        from django_celery_beat.models import PeriodicTask
        names = {task: label for task, label in SYNC_JOBS.values()}
        for t in PeriodicTask.objects.filter(task__in=names).select_related('interval', 'crontab'):
            schedules.append({
                'task': t.task, 'label': names[t.task], 'enabled': t.enabled,
                'last_run_at': t.last_run_at,
                'every': str(t.interval) if t.interval_id else (str(t.crontab) if t.crontab_id else ''),
            })
    except Exception:  # noqa: BLE001 — beat tables missing in some setups
        pass
    return {
        'provider': PROVIDER,
        'has_key': bool(key),
        'key_hint': _key_hint(key),
        'key_source': 'console' if db_key else ('environment' if env_key else 'none'),
        'base_url': db_url or getattr(settings, 'API_FOOTBALL_BASE_URL', ''),
        'base_url_source': 'console' if db_url else 'environment',
        'live_betting': bool(getattr(settings, 'SPORTSBOOK_LIVE_BETTING', False)),
        'live_odds_interval': getattr(settings, 'SPORTSBOOK_LIVE_ODDS_INTERVAL', None),
        'live_odds_stale': getattr(settings, 'SPORTSBOOK_LIVE_ODDS_STALE', None),
        'live_bet_delay': getattr(settings, 'SPORTSBOOK_LIVE_BET_DELAY', None),
        'counts': {
            'feed_events': events.filter(provider=PROVIDER).count(),
            'manual_events': events.exclude(provider=PROVIDER).count(),
            'upcoming': events.filter(starts_at__gt=now, is_open=True, has_odds=True).count(),
            'awaiting_odds': events.filter(starts_at__gt=now, has_odds=False).count(),
            'live': events.filter(status__in=LIVE_STATUSES).count(),
            'locked': events.filter(prices_locked=True).count(),
            'leagues_enabled': LeagueSetting.objects.filter(enabled=True).count(),
            'leagues_total': LeagueSetting.objects.count(),
            'markets_to_review': Market.objects.filter(settled=False).filter(
                Q(needs_review=True) | Q(kind=Market.Kind.MANUAL), event__starts_at__lt=now - timedelta(hours=2),
            ).count(),
        },
        'last_live_odds_at': events.aggregate(v=Max('live_odds_at'))['v'],
        'schedules': schedules,
        'jobs': [{'id': k, 'label': v[1]} for k, v in SYNC_JOBS.items()],
    }


class FeedSettingsView(APIView):
    """GET/PUT /api/admin/sportsbook/feed/ — the api-football connection.
    The key is write-only: reads show only its last four characters."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(_feed_summary())

    def put(self, request):
        credential, _ = ProviderCredential.objects.get_or_create(provider=PROVIDER)
        data = request.data
        if data.get('clear_key'):
            credential.api_key = ''
        elif (key := str(data.get('api_key') or '').strip()):
            credential.api_key = key[:200]
        if 'base_url' in data:
            url = str(data.get('base_url') or '').strip()
            if url and not url.startswith(('http://', 'https://')):
                return Response({'detail': 'Base URL must start with https://'}, status=status.HTTP_400_BAD_REQUEST)
            credential.base_url = url.rstrip('/')
        credential.save()
        from apps.accounts.services import audit
        audit(None, 'feed_settings_changed', request, provider=PROVIDER,
              key_changed=bool(data.get('api_key') or data.get('clear_key')))
        return Response(_feed_summary())


class FeedTestView(APIView):
    """POST /api/admin/sportsbook/feed/test/ — check the key against api-football."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            return Response({'ok': True, **ApiFootballClient().fetch_status()})
        except ValueError as exc:
            return Response({'ok': False, 'error': str(exc)})


class FeedSyncView(APIView):
    """POST /api/admin/sportsbook/feed/sync/ {job} — queue a feed job now."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        job = SYNC_JOBS.get(str(request.data.get('job', '')))
        if job is None:
            return Response({'detail': 'Unknown job.'}, status=status.HTTP_400_BAD_REQUEST)
        from config.celery import app
        try:
            result = app.send_task(job[0])
        except Exception as exc:  # noqa: BLE001 — broker down
            return Response({'detail': f'Could not queue the job: {exc.__class__.__name__}'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'queued': True, 'job': job[1], 'task_id': result.id}, status=status.HTTP_202_ACCEPTED)


# -- leagues --------------------------------------------------------------------

class AdminLeagueSerializer(serializers.ModelSerializer):
    upcoming_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = LeagueSetting
        fields = ['id', 'provider', 'league_id', 'name', 'country', 'logo_url', 'flag_url',
                  'enabled', 'sort_order', 'upcoming_count']
        read_only_fields = ['id', 'provider', 'upcoming_count']
        extra_kwargs = {'league_id': {'required': False}}
        # league_id is filled in for hand-added leagues, so skip the
        # (provider, league_id) check the model constraint would demand up front.
        validators = []

    def create(self, validated):
        # Leagues added by hand get their own id space under provider "manual".
        validated['provider'] = 'manual'
        if not validated.get('league_id'):
            top = LeagueSetting.objects.filter(provider='manual').aggregate(m=Max('league_id'))['m'] or 900000
            validated['league_id'] = top + 1
        return super().create(validated)


class AdminLeagueViewSet(viewsets.ModelViewSet):
    """/api/admin/sportsbook/leagues/ — ?search=, ?enabled=true|false, ?country="""
    serializer_class = AdminLeagueSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AdminPagination

    def get_queryset(self):
        p = self.request.query_params
        qs = LeagueSetting.objects.annotate(upcoming_count=Count(
            'events', filter=Q(events__starts_at__gt=timezone.now(), events__is_open=True), distinct=True,
        ))
        if (q := p.get('search', '').strip()):
            qs = qs.filter(Q(name__icontains=q) | Q(country__icontains=q) | Q(league_id__iexact=q) if q.isdigit()
                           else Q(name__icontains=q) | Q(country__icontains=q))
        if p.get('enabled') in ('true', 'false'):
            qs = qs.filter(enabled=p['enabled'] == 'true')
        if (country := p.get('country')):
            qs = qs.filter(country__iexact=country)
        return qs.order_by('sort_order', 'country', 'name')

    def destroy(self, request, *args, **kwargs):
        league = self.get_object()
        if league.events.exists():
            return Response({'detail': 'This league has matches. Disable it instead of deleting.'},
                            status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['post'])
    def bulk(self, request):
        """{ids: [...], enabled: bool} — switch many leagues on or off at once."""
        ids = [int(i) for i in request.data.get('ids', []) if str(i).isdigit()]
        if not ids or not isinstance(request.data.get('enabled'), bool):
            return Response({'detail': 'Send ids and enabled.'}, status=status.HTTP_400_BAD_REQUEST)
        updated = LeagueSetting.objects.filter(pk__in=ids).update(enabled=request.data['enabled'])
        return Response({'updated': updated})

    @action(detail=False, methods=['get'])
    def countries(self, request):
        rows = (LeagueSetting.objects.exclude(country='').values('country')
                .annotate(n=Count('id')).order_by('country'))
        return Response([{'country': r['country'], 'count': r['n']} for r in rows])


# -- matches --------------------------------------------------------------------

class _TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['id', 'name', 'logo_url']


class _LeagueBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeagueSetting
        fields = ['id', 'name', 'country', 'flag_url', 'logo_url']


def _team_for(name: str, current: Team | None) -> Team | None:
    """Hand-entered team: reuse the current team if the name is unchanged, else
    find or create a manual team with that name."""
    name = ' '.join((name or '').split())[:200]
    if not name:
        return None
    if current is not None and current.name == name:
        return current
    existing = Team.objects.filter(name__iexact=name).order_by('provider').first()
    return existing or Team.objects.create(name=name, provider='manual')


class AdminEventSerializer(serializers.ModelSerializer):
    home_team = _TeamSerializer(read_only=True)
    away_team = _TeamSerializer(read_only=True)
    league_detail = _LeagueBriefSerializer(source='league', read_only=True)
    league = serializers.PrimaryKeyRelatedField(queryset=LeagueSetting.objects.all(), allow_null=True, required=False)
    home_team_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    away_team_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    markets_count = serializers.IntegerField(read_only=True, default=0)
    bets_count = serializers.IntegerField(read_only=True, default=0)
    source = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    trading = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id', 'name', 'sport', 'provider', 'external_id', 'source', 'state', 'trading',
            'league', 'league_detail', 'home_team', 'away_team', 'home_team_name', 'away_team_name',
            'starts_at', 'status', 'elapsed', 'score_home', 'score_away', 'ht_score_home', 'ht_score_away',
            'odds', 'odds_draw', 'odds_away', 'previous_odds', 'has_odds', 'prices_locked',
            'featured', 'is_open', 'markets_count', 'bets_count',
        ]
        read_only_fields = ['id', 'provider', 'external_id', 'previous_odds']
        extra_kwargs = {'name': {'required': False}}

    def get_source(self, obj) -> str:
        return 'feed' if obj.provider == PROVIDER else 'manual'

    def get_state(self, obj) -> str:
        if obj.status in VOID_STATUSES:
            return 'void'
        if obj.status in FINISHED_STATUSES:
            return 'finished'
        if obj.status in LIVE_STATUSES:
            return 'live'
        if obj.starts_at and obj.starts_at <= timezone.now():
            return 'started'
        return 'upcoming'

    def get_trading(self, obj) -> dict:
        return trading_state(obj)

    def validate(self, attrs):
        for field in ('odds', 'odds_draw', 'odds_away'):
            v = attrs.get(field)
            if v is not None and v < 1:
                raise serializers.ValidationError({field: 'Odds must be at least 1.00.'})
        return attrs

    def _apply_teams(self, instance: Event, validated) -> None:
        home = validated.pop('home_team_name', None)
        away = validated.pop('away_team_name', None)
        if home is not None:
            instance.home_team = _team_for(home, instance.home_team)
        if away is not None:
            instance.away_team = _team_for(away, instance.away_team)
        if not validated.get('name') and instance.home_team and instance.away_team:
            validated['name'] = f'{instance.home_team.name} vs {instance.away_team.name}'

    def create(self, validated):
        event = Event(provider='manual')
        self._apply_teams(event, validated)
        if not validated.get('name'):
            raise serializers.ValidationError({'name': 'Give the match a name or both team names.'})
        for k, v in validated.items():
            setattr(event, k, v)
        event.save()
        return event

    def update(self, instance, validated):
        self._apply_teams(instance, validated)
        for k, v in validated.items():
            setattr(instance, k, v)
        instance.save()
        return instance


class AdminEventViewSet(viewsets.ModelViewSet):
    """/api/admin/sportsbook/events/ — every match, for operators.

    ?state=upcoming|live|finished|unpriced|closed|locked, ?q=, ?league=,
    ?source=feed|manual, ?featured=true, ?ordering=starts_at|-starts_at"""
    serializer_class = AdminEventSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AdminPagination

    def get_queryset(self):
        p = self.request.query_params
        now = timezone.now()
        qs = Event.objects.select_related('home_team', 'away_team', 'league').annotate(
            markets_count=Count('markets', distinct=True),
            bets_count=Count('bets', filter=Q(bets__status__in=('open', 'pending', 'accepting')), distinct=True),
        )
        state = p.get('state', '')
        if state == 'upcoming':
            qs = qs.filter(starts_at__gt=now).exclude(status__in=(*FINISHED_STATUSES, *VOID_STATUSES))
        elif state == 'live':
            qs = qs.filter(status__in=LIVE_STATUSES)
        elif state == 'finished':
            qs = qs.filter(status__in=(*FINISHED_STATUSES, *VOID_STATUSES))
        elif state == 'unpriced':
            qs = qs.filter(has_odds=False, starts_at__gt=now)
        elif state == 'closed':
            qs = qs.filter(is_open=False).exclude(status__in=(*FINISHED_STATUSES, *VOID_STATUSES))
        elif state == 'locked':
            qs = qs.filter(prices_locked=True)
        if (q := p.get('q', '').strip()):
            qs = qs.filter(Q(name__icontains=q) | Q(home_team__name__icontains=q)
                           | Q(away_team__name__icontains=q) | Q(external_id=q))
        if (league := p.get('league', '')).isdigit():
            qs = qs.filter(league_id=int(league))
        if p.get('source') == 'feed':
            qs = qs.filter(provider=PROVIDER)
        elif p.get('source') == 'manual':
            qs = qs.exclude(provider=PROVIDER)
        if p.get('featured') == 'true':
            qs = qs.filter(featured=True)
        ordering = '-starts_at' if p.get('ordering') == '-starts_at' or state == 'finished' else 'starts_at'
        return qs.order_by(ordering, 'id')

    def perform_update(self, serializer):
        before = serializer.instance
        changed = sorted(k for k in serializer.validated_data if k not in ('home_team_name', 'away_team_name'))
        serializer.save()
        from apps.accounts.services import audit
        audit(None, 'event_edited', self.request, event_id=before.id, fields=changed)

    def destroy(self, request, *args, **kwargs):
        event = self.get_object()
        if Bet.objects.filter(event_ref=event).exists() or BetLeg.objects.filter(event_ref=event).exists():
            return Response({'detail': 'Bets were placed on this match. Close or void it instead of deleting.'},
                            status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        now = timezone.now()
        done = (*FINISHED_STATUSES, *VOID_STATUSES)
        e = Event.objects
        return Response({
            'upcoming': e.filter(starts_at__gt=now).exclude(status__in=done).count(),
            'live': e.filter(status__in=LIVE_STATUSES).count(),
            'unpriced': e.filter(has_odds=False, starts_at__gt=now).count(),
            'closed': e.filter(is_open=False).exclude(status__in=done).count(),
            'finished': e.filter(status__in=done).count(),
            'locked': e.filter(prices_locked=True).count(),
        })

