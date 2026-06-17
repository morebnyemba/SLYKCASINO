"""Custom middleware for SLYK Casino backend."""

BLOCKED_COUNTRIES = {'US', 'FR', 'AU', 'SG', 'HK'}  # example blocked jurisdictions


class GeoBlockMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip non-API paths and health check
        if not request.path.startswith('/api/') or request.path == '/api/health/':
            return self.get_response(request)
        country = request.META.get('HTTP_CF_IPCOUNTRY') or request.META.get('HTTP_X_COUNTRY_CODE', '')
        if country.upper() in BLOCKED_COUNTRIES:
            from rest_framework.response import Response
            from rest_framework.renderers import JSONRenderer
            response = Response(
                {'detail': f'Service not available in your region ({country})'},
                status=403,
            )
            response.accepted_renderer = JSONRenderer()
            response.accepted_media_type = 'application/json'
            response.renderer_context = {}
            response.render()
            return response
        return self.get_response(request)
