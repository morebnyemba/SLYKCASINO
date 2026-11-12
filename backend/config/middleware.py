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
        return staff_user(request) is not None


def staff_user(request):
    """The staff login behind a request (Django admin session or admin-console
    JWT), or None."""
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        return user if user.is_staff else None
    if not request.META.get('HTTP_AUTHORIZATION', '').startswith('Bearer '):
        return None
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication
        found = JWTAuthentication().authenticate(request)
    except Exception:  # noqa: BLE001 — a bad token is the view's business, not ours
        return None
    return found[0] if found and found[0].is_staff else None


class SettingsCosignMiddleware:
    """Revenue-share settings change only with every partner's co-signature:
    a staff save to one of them is held (202) until all partners approve, then
    replayed as the requester (apps.revenue.changes). The Django admin can't
    edit those records at all."""

    SAFE = ('GET', 'HEAD', 'OPTIONS')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in self.SAFE:
            return self.get_response(request)
        from apps.revenue import changes
        if changes.django_admin_locked(request.path):
            if staff_user(request) is not None:
                from django.http import HttpResponse
                return HttpResponse('These settings change only with every partner\'s co-signature — use the admin '
                                    'console, where the change is sent to the partners.', status=403,
                                    content_type='text/plain; charset=utf-8')
            return self.get_response(request)
        label = changes.governed(request.path)
        if label is None:
            return self.get_response(request)
        user = staff_user(request)
        if user is None:
            return self.get_response(request)
        from django.http import JsonResponse
        try:
            change = changes.hold(request, user)
        except changes.ChangeError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)
        if change is None:
            return self.get_response(request)
        waiting = changes.waiting_for(change)
        return JsonResponse({
            'pending': True, 'change_id': change.id,
            'detail': f'Not applied yet — sent to the partners for co-signing. Waiting for: {", ".join(waiting)}. '
                      'It applies as soon as every partner approves (Money › Revenue-share changes).',
            'waiting_for': waiting,
        }, status=202)
