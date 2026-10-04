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
from .models import Banner, BannerImage, PromotionClaim, Tournament
from .serializers import (
    BannerSerializer,
    PromotionClaimSerializer,
    PromotionSerializer,
    TournamentEntrySerializer,
    TournamentSerializer,
)


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
        if self.request.query_params.get('all') == 'true':
            return qs
        now = timezone.now()
        return (
            qs.filter(active=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        )

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminUser()]
        return [AllowAny()]


class PromotionViewSet(viewsets.ModelViewSet):
    """Public read of the promotion catalog; admin-only create/update/delete."""
    serializer_class = PromotionSerializer

    def get_queryset(self):
        return services.list_promotions()

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


class BannerImageUploadView(APIView):
    """POST /api/promotions/banner-images/ (staff, multipart `file`) -> {id, url}.
    `url` is site-relative, so it works on whichever domain serves the site."""
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get('file')
        if upload is None:
            return Response({'detail': 'Choose an image to upload.'}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > BANNER_IMAGE_MAX_BYTES:
            return Response({'detail': 'Images must be 5 MB or smaller.'}, status=status.HTTP_400_BAD_REQUEST)
        content = upload.read()
        content_type = _sniff_image_type(content[:16])
        if content_type is None:
            return Response({'detail': 'Upload a JPG, PNG, WebP or GIF image.'}, status=status.HTTP_400_BAD_REQUEST)
        image = BannerImage.objects.create(content=content, content_type=content_type, size=len(content))
        return Response(
            {'id': image.id, 'url': f'/api/promotions/banner-images/{image.id}/'},
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
        response = HttpResponse(bytes(image.content), content_type=image.content_type)
        response['Cache-Control'] = 'public, max-age=31536000, immutable'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
