"""affiliates transport (DRF). Mutations are delegated to services."""
from __future__ import annotations

from rest_framework import serializers

from .models import Affiliate, AffiliateProgramme, Commission, Payout


class AffiliateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Affiliate
        fields = [
            'id', 'code', 'status', 'revshare_percent', 'cpa_amount', 'cpa_min_deposit', 'cpa_percent', 'cpa_cap',
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


class ProgrammeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AffiliateProgramme
        fields = [
            'welcome_bonus_percent', 'welcome_bonus_cap', 'welcome_bonus_wagering', 'welcome_bonus_min_deposit',
            'default_revshare_percent', 'default_cpa_amount', 'default_cpa_min_deposit', 'default_cpa_percent',
            'default_cpa_cap', 'cpa_min_turnover_multiple', 'negative_carryover', 'min_payout', 'external_payouts',
            'updated_at',
        ]
        read_only_fields = fields


class PayoutSerializer(serializers.ModelSerializer):
    method_label = serializers.CharField(source='get_method_display', read_only=True)

    class Meta:
        model = Payout
        fields = [
            'id', 'amount', 'method', 'method_label', 'account_name', 'account_number', 'bank_name', 'status',
            'reference', 'note', 'created_at', 'decided_at',
        ]
        read_only_fields = fields


class AdminPayoutSerializer(PayoutSerializer):
    affiliate_code = serializers.CharField(source='affiliate.code', read_only=True)
    username = serializers.SerializerMethodField()
    kyc_status = serializers.SerializerMethodField()

    class Meta(PayoutSerializer.Meta):
        fields = PayoutSerializer.Meta.fields + ['affiliate', 'affiliate_code', 'username', 'kyc_status']
        read_only_fields = fields

    def get_username(self, obj) -> str:
        return self.context.get('players', {}).get(obj.affiliate.player_id, ('', ''))[0]

    def get_kyc_status(self, obj) -> str:
        return self.context.get('players', {}).get(obj.affiliate.player_id, ('', ''))[1]
