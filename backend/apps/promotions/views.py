"""promotions transport — catalog read; claiming is driven via services."""
from __future__ import annotations

from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.utils import timezone

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services

from . import services
from .models import Banner, BannerImage, DepositBonus, PromotionClaim, Tournament
from .serializers import (
    BannerSerializer,
    DepositBonusSerializer,
    PublicDepositBonusSerializer,
    PromotionClaimSerializer,
    PromotionSerializer,
    TournamentEntrySerializer,
    TournamentSerializer,
)


ADMIN_ACTIONS = ('update', 'partial_update', 'destroy')


class BannerViewSet(viewsets.ModelViewSet):
    """Public read of live banners; admin-only create/update/delete.

    Pass ?all=true (used by the operator console) to list every banner,
    including inactive and scheduled ones, and ?placement= for one surface."""
    serializer_class = BannerSerializer

    def get_queryset(self):
        qs = Banner.objects.all().order_by('sort_order', '-created_at')
        # ?placement=home_hero|sportsbook narrows to one surface.
        placement = self.request.query_params.get('placement')
        if placement:
            qs = qs.filter(placement=placement)
        # Edits come from the operator console and must reach any banner —
        # switched off, scheduled or expired — not just the live ones.
        if self.request.query_params.get('all') == 'true' or self.action in ADMIN_ACTIONS:
            return qs
        now = timezone.now()
        return (
            qs.filter(active=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        )

    def get_permissions(self):
        if self.action in ('create', *ADMIN_ACTIONS):
            return [IsAdminUser()]
        return [AllowAny()]


class PromotionViewSet(viewsets.ModelViewSet):
    """Public read of the promotion catalog; admin-only create/update/delete."""
    serializer_class = PromotionSerializer

    def get_queryset(self):
        # Deposit-bonus tiers keep their claims on a hidden promotion each; they
        # are managed as tiers (admin/deposit-bonuses), so never listed here.
        qs = services.list_promotions().exclude(code__startswith='deposit-bonus:')
        # System promotions (e.g. the referral welcome bonus) are granted
        # automatically, never listed for players to claim.
        if not (self.request.user and self.request.user.is_staff):
            qs = qs.exclude(code__startswith='SYS-')
        return qs

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminUser()]
        if self.action == 'claim':
            return [IsAuthenticated()]
        return [AllowAny()]

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='claim')
    def claim(self, request, pk=None):
        """POST /api/promotions/{id}/claim/ — claim a promotion bonus."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            claim = services.claim_promotion(player_id=player.id, promotion_id=int(pk))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PromotionClaimSerializer(claim).data, status=status.HTTP_201_CREATED)


class MyClaimsViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PromotionClaimSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        player = accounts_services.get_current_player(self.request)
        if player is None:
            return PromotionClaim.objects.none()
        return PromotionClaim.objects.filter(player_id=player.id).order_by('-id')


class TournamentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = TournamentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return services.list_tournaments().annotate(entry_count=Count('entries'))

    @action(detail=True, methods=['get'], permission_classes=[AllowAny], url_path='leaderboard')
    def leaderboard(self, request, pk=None):
        """GET /api/promotions/tournaments/{id}/leaderboard/ — top entries (public)."""
        rows = services.leaderboard(int(pk))
        return Response(TournamentEntrySerializer(rows, many=True).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='join')
    def join(self, request, pk=None):
        """POST /api/promotions/tournaments/{id}/join/ — opt the player in."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            entry = services.join_tournament(
                player_id=player.id, player_name=player.username, tournament_id=int(pk),
            )
        except Tournament.DoesNotExist:
            return Response({'detail': 'tournament not found'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TournamentEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


# Banner uploads: the type is read from the file's own bytes, never from the
# client, so only real images are ever served back.
BANNER_IMAGE_MAX_BYTES = 5 * 1024 * 1024
BANNER_VIDEO_MAX_BYTES = 8 * 1024 * 1024


def _sniff_image_type(head: bytes):
    if head.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if head[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image/webp'
    return None


def _sniff_media_type(head: bytes):
    """An image, or a short video loop (MP4 or WebM), read from the file's own bytes."""
    if head[4:8] == b'ftyp':
        return 'video/mp4'
    if head.startswith(b'\x1a\x45\xdf\xa3'):
        return 'video/webm'
    return _sniff_image_type(head)


class BannerImageUploadView(APIView):
    """POST /api/promotions/banner-images/ (staff, multipart `file`) -> {id, url, kind}.
    An image (up to 5 MB) or a short MP4/WebM loop (up to 8 MB).
    `url` is site-relative, so it works on whichever domain serves the site."""
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get('file')
        if upload is None:
            return Response({'detail': 'Choose an image to upload.'}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > BANNER_VIDEO_MAX_BYTES:
            return Response({'detail': 'Files must be 8 MB or smaller (5 MB for images).'}, status=status.HTTP_400_BAD_REQUEST)
        content = upload.read()
        content_type = _sniff_media_type(content[:16])
        if content_type is None:
            return Response({'detail': 'Upload a JPG, PNG, WebP or GIF image, or an MP4 or WebM video.'},
                            status=status.HTTP_400_BAD_REQUEST)
        is_video = content_type.startswith('video/')
        if not is_video and len(content) > BANNER_IMAGE_MAX_BYTES:
            return Response({'detail': 'Images must be 5 MB or smaller.'}, status=status.HTTP_400_BAD_REQUEST)
        image = BannerImage.objects.create(content=content, content_type=content_type, size=len(content))
        return Response(
            {'id': image.id, 'url': f'/api/promotions/banner-images/{image.id}/', 'kind': 'video' if is_video else 'image'},
            status=status.HTTP_201_CREATED,
        )


class BannerImageView(APIView):
    """GET /api/promotions/banner-images/<id>/ — the image bytes, cached for a
    year (an upload never changes; a new design gets a new id)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request, pk: int):
        image = BannerImage.objects.filter(pk=pk).only('content', 'content_type').first()
        if image is None:
            raise Http404
        data = bytes(image.content)
        start, end, partial = 0, len(data) - 1, False
        wanted = request.headers.get('Range', '')
        if wanted.startswith('bytes=') and ',' not in wanted:
            # Browsers (iOS Safari above all) only play a video if it can be fetched in ranges.
            first, _, last = wanted[6:].partition('-')
            try:
                if first == '':
                    start = max(0, len(data) - int(last))
                else:
                    start = int(first)
                    end = min(int(last), len(data) - 1) if last else len(data) - 1
            except ValueError:
                start, end = 0, len(data) - 1
            else:
                if start > end or start >= len(data):
                    response = HttpResponse(status=416)
                    response['Content-Range'] = f'bytes */{len(data)}'
                    return response
                partial = True
        body = data[start:end + 1]
        response = HttpResponse(body, content_type=image.content_type, status=206 if partial else 200)
        response['Accept-Ranges'] = 'bytes'
        response['Content-Length'] = str(len(body))
        if partial:
            response['Content-Range'] = f'bytes {start}-{end}/{len(data)}'
        response['Cache-Control'] = 'public, max-age=31536000, immutable'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


def _announcement(a) -> dict:
    return {
        'enabled': a.enabled, 'title': a.title, 'message': a.message, 'tone': a.tone,
        'show_withdraw_button': a.show_withdraw_button, 'show_support_button': a.show_support_button,
        'updated_at': a.updated_at.isoformat() if a.updated_at else None,
    }


class AnnouncementView(APIView):
    """GET /api/announcement/ — the site-wide notice bar (public)."""
    permission_classes = [AllowAny]

    def get(self, request):
        from .models import SiteAnnouncement
        a = SiteAnnouncement.load()
        return Response(_announcement(a) if a.enabled and a.message.strip() else {'enabled': False})


class AdminAnnouncementView(APIView):
    """GET/PUT /api/admin/announcement/ — edit or switch off the notice bar."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from .models import SiteAnnouncement
        return Response(_announcement(SiteAnnouncement.load()))

    def put(self, request):
        from apps.accounts import services as accounts_services
        from .models import SiteAnnouncement
        a = SiteAnnouncement.load()
        d = request.data
        for f in ('enabled', 'show_withdraw_button', 'show_support_button'):
            if f in d:
                setattr(a, f, bool(d[f]))
        if 'title' in d:
            a.title = str(d['title'] or '').strip()[:80]
        if 'message' in d:
            a.message = str(d['message'] or '').strip()[:600]
        if d.get('tone') in SiteAnnouncement.Tone.values:
            a.tone = d['tone']
        if a.enabled and not a.message:
            return Response({'detail': 'Write a message before switching the notice on.'}, status=status.HTTP_400_BAD_REQUEST)
        a.updated_by = request.user.get_username()[:150]
        a.save()
        accounts_services.audit(None, 'site_announcement', request, enabled=a.enabled, title=a.title)
        return Response(_announcement(a))


class AdminDepositBonusViewSet(viewsets.ModelViewSet):
    """Staff: deposit promotion tiers (% of the deposit by amount), with how
    many bonuses each has given and their total."""
    serializer_class = DepositBonusSerializer
    permission_classes = [IsAdminUser]
    queryset = DepositBonus.objects.all()

    def list(self, request, *args, **kwargs):
        data = self.get_serializer(self.get_queryset(), many=True).data
        stats = services.deposit_bonus_stats()
        for row in data:
            s = stats.get(row['id'], {})
            row['given'] = s.get('given', 0)
            row['total_given'] = f"{s.get('total', 0):.2f}"
        return Response(data)

    def perform_create(self, serializer):
        tier = serializer.save()
        accounts_services.audit(None, 'deposit_bonus_created', self.request, id=tier.id, name=tier.name,
                                percent=str(tier.percent), min_deposit=str(tier.min_deposit))

    def perform_update(self, serializer):
        tier = serializer.save()
        accounts_services.audit(None, 'deposit_bonus_updated', self.request, id=tier.id, name=tier.name,
                                percent=str(tier.percent), active=tier.active)

    def perform_destroy(self, instance):
        accounts_services.audit(None, 'deposit_bonus_deleted', self.request, id=instance.id, name=instance.name)
        instance.delete()


class DepositBonusListView(APIView):
    """Public: the deposit promotions running now (for the deposit screen)."""
    permission_classes = [AllowAny]

    def get(self, request):
        tiers = services.live_deposit_bonuses()
        data = PublicDepositBonusSerializer(tiers, many=True).data
        player = accounts_services.get_current_player(request) if request.user.is_authenticated else None
        used = services.used_deposit_bonuses(player.id, tiers) if player else set()
        for row in data:
            row['used'] = row['id'] in used
        return Response(data)


class AdminPromoCodeViewSet(viewsets.ModelViewSet):
    """Staff: /api/admin/promo-codes/ — create, edit and deactivate promo codes
    (PATCH {active: false}). A code that has been used can't be deleted, only
    deactivated, so its history stays."""
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        from .serializers import PromoCodeSerializer
        return PromoCodeSerializer

    def get_queryset(self):
        from .models import PromoCode
        return PromoCode.objects.all()

    def list(self, request, *args, **kwargs):
        from . import promo_codes
        data = self.get_serializer(self.get_queryset(), many=True).data
        stats = promo_codes.stats()
        for row in data:
            s = stats.get(row['id'], {})
            row['uses'], row['total_given'] = s.get('uses', 0), s.get('total', '0.00')
        return Response(data)

    def perform_create(self, serializer):
        promo = serializer.save(created_by=self.request.user.get_username())
        accounts_services.audit(None, 'promo_code_created', self.request, id=promo.id, code=promo.code,
                                kind=promo.kind, value=str(promo.value))

    def perform_update(self, serializer):
        promo = serializer.save()
        accounts_services.audit(None, 'promo_code_updated', self.request, id=promo.id, code=promo.code,
                                active=promo.active, fields=sorted(serializer.validated_data))

    def destroy(self, request, *args, **kwargs):
        promo = self.get_object()
        if promo.redemptions.exists():
            return Response({'detail': 'This code has been used — deactivate it instead.'},
                            status=status.HTTP_409_CONFLICT)
        accounts_services.audit(None, 'promo_code_deleted', request, id=promo.id, code=promo.code)
        promo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PromoCodeCheckView(APIView):
    """POST /api/promo-codes/check/ {code, amount?} — can I use this code, and
    what would I get? Rate-limited so codes can't be guessed."""
    permission_classes = [IsAuthenticated]
    throttle_scope = 'promo_check'

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle
        return [*super().get_throttles(), ScopedRateThrottle()]

    def post(self, request):
        from decimal import Decimal, InvalidOperation

        from . import promo_codes
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'Player not found.'}, status=status.HTTP_404_NOT_FOUND)
        amount = None
        if request.data.get('amount') not in (None, ''):
            try:
                amount = Decimal(str(request.data['amount']))
            except (InvalidOperation, ValueError):
                return Response({'detail': 'Enter a valid amount.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            return Response({'valid': True, **promo_codes.preview(str(request.data.get('code') or ''),
                                                                   player_id=player.id, amount=amount)})
        except promo_codes.PromoError as exc:
            return Response({'valid': False, 'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
