import re

from rest_framework import serializers

from .models import SiteIdentity, SiteTheme
from .tokens import TOKEN_KEYS

# logo_url renders as an <img src>; restrict to safe schemes (no javascript:/data:).
_LOGO_URL_RE = re.compile(r'^(https?://|/)')

# Deliberately strict: these values are interpolated into a raw <style> tag
# server-side with no HTML escaping, so only literal CSS color syntax is
# allowed — no url(), no comments, no semicolons/braces that could break out
# of the declaration.
_COLOR_RE = re.compile(
    r'^(#[0-9a-fA-F]{3,8}'
    r'|rgba?\(\s*\d{1,3}%?\s*,\s*\d{1,3}%?\s*,\s*\d{1,3}%?\s*(,\s*(0|1|0?\.\d+)\s*)?\)'
    r'|hsla?\(\s*\d{1,3}\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%\s*(,\s*(0|1|0?\.\d+)\s*)?\))$'
)


def _validate_tokens(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError('must be an object of token -> color')
    unknown = set(value) - set(TOKEN_KEYS)
    if unknown:
        raise serializers.ValidationError(f'unknown token(s): {", ".join(sorted(unknown))}')
    bad = {k: v for k, v in value.items() if not isinstance(v, str) or not _COLOR_RE.match(v.strip())}
    if bad:
        raise serializers.ValidationError(f'invalid color value(s) for: {", ".join(sorted(bad))}')
    return value


class SiteThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteTheme
        fields = ['light', 'dark', 'updated_at', 'updated_by_username']
        read_only_fields = ['updated_at', 'updated_by_username']

    def validate_light(self, value):
        return _validate_tokens(value)

    def validate_dark(self, value):
        return _validate_tokens(value)


class SiteIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteIdentity
        fields = ['site_name', 'tagline', 'logo_url', 'license_text', 'updated_at', 'updated_by_username']
        read_only_fields = ['updated_at', 'updated_by_username']

    def validate_logo_url(self, value):
        if value and not _LOGO_URL_RE.match(value.strip()):
            raise serializers.ValidationError('must be an http(s):// URL or a site-relative path')
        return value
