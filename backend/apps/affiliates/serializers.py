"""affiliates transport (DRF). Mutations are delegated to services."""
from __future__ import annotations

from rest_framework import serializers

from .models import Affiliate, Commission


class AffiliateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Affiliate
        fields = [
            'id', 'code', 'status', 'revshare_percent', 'cpa_amount', 'cpa_min_deposit',
            'website', 'created_at', 'approved_at',
        ]
        read_only_fields = fields


class AdminAffiliateSerializer(AffiliateSerializer):
    username = serializers.SerializerMethodField()
    referrals_count = serializers.IntegerField(read_only=True, default=0)
    clicks_count = serializers.IntegerField(read_only=True, default=0)

    class Meta(AffiliateSerializer.Meta):
        fields = AffiliateSerializer.Meta.fields + ['player_id', 'username', 'note', 'referrals_count', 'clicks_count']
        read_only_fields = fields

    def get_username(self, obj) -> str:
        return self.context.get('usernames', {}).get(obj.player_id, '')


class CommissionSerializer(serializers.ModelSerializer):
    affiliate_code = serializers.CharField(source='affiliate.code', read_only=True)

    class Meta:
        model = Commission
        fields = [
            'id', 'affiliate', 'affiliate_code', 'kind', 'period', 'base_amount', 'rate', 'amount',
            'active_players', 'status', 'note', 'created_at', 'decided_at', 'paid_at',
        ]
        read_only_fields = fields
