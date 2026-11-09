"""promotions transport (DRF)."""
from __future__ import annotations

from rest_framework import serializers

from decimal import Decimal

from .models import Banner, DepositBonus, PromoCode, Promotion, PromotionClaim, Tournament, TournamentEntry


class BannerSerializer(serializers.ModelSerializer):
    is_live = serializers.BooleanField(read_only=True)

    class Meta:
        model = Banner
        fields = [
            'id', 'title', 'subtitle', 'image_url', 'mobile_image_url', 'video_url', 'motion', 'focus', 'overlay_text', 'link_url', 'cta_label',
            'placement', 'sort_order', 'active', 'is_live', 'starts_at', 'ends_at',
        ]


class PromotionSerializer(serializers.ModelSerializer):
    claim_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Promotion
        fields = [
            'id', 'name', 'kind', 'active', 'bonus_amount', 'wagering_multiplier',
            'starts_at', 'ends_at', 'code', 'terms_html', 'claim_count',
        ]


class PromotionClaimSerializer(serializers.ModelSerializer):
    promotion_name = serializers.CharField(source='promotion.name', read_only=True)
    promotion_code = serializers.CharField(source='promotion.code', read_only=True)

    class Meta:
        model = PromotionClaim
        fields = [
            'id', 'promotion', 'promotion_name', 'promotion_code', 'source', 'bonus_amount',
            'wagering_required', 'wagering_progress', 'status',
            'bonus_credited', 'created_at', 'completed_at',
        ]
        read_only_fields = fields


class TournamentSerializer(serializers.ModelSerializer):
    is_live = serializers.BooleanField(read_only=True)
    entry_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Tournament
        fields = [
            'id', 'name', 'description', 'metric', 'prize_pool', 'currency',
            'active', 'is_live', 'starts_at', 'ends_at', 'entry_count',
        ]
        read_only_fields = fields


class TournamentEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = TournamentEntry
        fields = ['id', 'player_name', 'score', 'updated_at']
        read_only_fields = fields


class DepositBonusSerializer(serializers.ModelSerializer):
    """A deposit promotion tier, as staff edit it."""

    class Meta:
        model = DepositBonus
        fields = ['id', 'name', 'active', 'min_deposit', 'max_deposit', 'percent', 'max_bonus',
                  'wagering_multiplier', 'limit', 'starts_at', 'ends_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        low, high = get('min_deposit'), get('max_deposit')
        if low is not None and low < 0:
            raise serializers.ValidationError({'min_deposit': 'Can’t be negative.'})
        if high is not None and low is not None and high < low:
            raise serializers.ValidationError({'max_deposit': 'Must be at least the minimum deposit.'})
        pct = get('percent')
        if pct is not None and not (Decimal('0') < pct <= Decimal('500')):
            raise serializers.ValidationError({'percent': 'Between 0 and 500%.'})
        if (get('max_bonus') or 0) < 0:
            raise serializers.ValidationError({'max_bonus': 'Can’t be negative (0 = no cap).'})
        if (get('wagering_multiplier') or 0) < 0:
            raise serializers.ValidationError({'wagering_multiplier': 'Can’t be negative.'})
        start, end = get('starts_at'), get('ends_at')
        if start and end and end <= start:
            raise serializers.ValidationError({'ends_at': 'Must be after the start.'})
        return attrs


class PublicDepositBonusSerializer(serializers.ModelSerializer):
    """What players are shown on the deposit screen."""

    class Meta:
        model = DepositBonus
        fields = ['id', 'name', 'min_deposit', 'max_deposit', 'percent', 'max_bonus', 'wagering_multiplier', 'limit', 'ends_at']
        read_only_fields = fields


class PromoCodeSerializer(serializers.ModelSerializer):
    """Staff view of a promo code, with how often it has been used."""
    uses = serializers.IntegerField(read_only=True, default=0)
    total_given = serializers.CharField(read_only=True, default='0.00')
    # Declared so uniqueness is checked on the normalised (upper-case) code below.
    code = serializers.CharField(max_length=40)

    class Meta:
        model = PromoCode
        fields = ['id', 'code', 'name', 'description', 'active', 'kind', 'value', 'max_bonus', 'min_deposit',
                  'starts_at', 'ends_at', 'max_uses', 'per_player_limit', 'created_by', 'created_at', 'updated_at',
                  'uses', 'total_given']
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def validate_code(self, value):
        from .promo_codes import CODE_RE, normalise
        code = normalise(value)
        if not CODE_RE.match(code):
            raise serializers.ValidationError('3–40 letters, numbers, - or _.')
        taken = PromoCode.objects.filter(code=code)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError('A promo code with this code already exists.')
        return code

    def validate(self, attrs):
        kind = attrs.get('kind', getattr(self.instance, 'kind', 'percent'))
        value = attrs.get('value', getattr(self.instance, 'value', None))
        if value is not None and value <= 0:
            raise serializers.ValidationError({'value': 'Must be above zero.'})
        if kind == 'percent' and value is not None and value > 500:
            raise serializers.ValidationError({'value': 'At most 500%.'})
        starts = attrs.get('starts_at', getattr(self.instance, 'starts_at', None))
        ends = attrs.get('ends_at', getattr(self.instance, 'ends_at', None))
        if starts and ends and ends <= starts:
            raise serializers.ValidationError({'ends_at': 'Must be after the start.'})
        return attrs
