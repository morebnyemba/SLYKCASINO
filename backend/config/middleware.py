"""Custom middleware for BetBlits backend."""

BLOCKED_COUNTRIES = {'US', 'FR', 'AU', 'SG', 'HK'}  # example blocked jurisdictions


class GeoBlockMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip non-API paths and health check
        if not request.path.startswith('/api/') or request.path == '/api/health/':
            return self.get_response(request)
        # Trust only the Cloudflare-set header. A client-supplied header (e.g.
        # X-Country-Code) is fully spoofable and must never be used to decide
        # jurisdiction blocking.
        country = request.META.get('HTTP_CF_IPCOUNTRY', '')
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


class AuditLockMiddleware:
    """While two weekly pool audits in a row are missed, the whole admin is
    read-only: every change made by a staff login is refused (the admin console
    and the Django admin alike), except the pool-audit actions that lift the
    lock and signing in/out. Players and the automatic jobs are not affected."""

    SAFE = ('GET', 'HEAD', 'OPTIONS')
    ALLOWED = (
        '/api/auth/',
        '/api/admin/revenue-share/audits/',
        '/api/admin/revenue-share/governance/',
        '/api/admin/lock-status/',
        '/django-admin/login/',
        '/django-admin/logout/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in self.SAFE or request.path.startswith(self.ALLOWED):
            return self.get_response(request)
        if not (request.path.startswith('/api/') or request.path.startswith('/django-admin/')):
            return self.get_response(request)
        if not self._is_staff(request):
            return self.get_response(request)
        from apps.revenue.audit import lock_state
        state = lock_state()
        if not state['locked']:
            return self.get_response(request)
        from django.http import JsonResponse
        return JsonResponse({'detail': state['message'], 'locked': True}, status=423)

    @staticmethod
    def _is_staff(request) -> bool:
        user = getattr(request, 'user', None)          # Django admin (session)
        if user is not None and user.is_authenticated:
            return bool(user.is_staff)
        if not request.META.get('HTTP_AUTHORIZATION', '').startswith('Bearer '):
            return False
        try:                                            # the admin console (JWT)
            from rest_framework_simplejwt.authentication import JWTAuthentication
            found = JWTAuthentication().authenticate(request)
        except Exception:  # noqa: BLE001 — a bad token is the view's business, not the lock's
            return False
        return bool(found and found[0].is_staff)
