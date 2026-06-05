"""Root URL config — aggregates the bounded-context routers under /api/.

Nginx routes /api/ and /django-admin/ to this service. The frontend contract
(events/, bets/, players/, players/me/, wallet/, promotions/, chat/,
admin/stats/, health/) is preserved by the includes below.
"""
from django.contrib import admin
from django.urls import include, path

from . import views

api_patterns = [
    path('', include('apps.accounts.urls')),     # players/, players/me/
    path('', include('apps.wallet.urls')),        # wallet/
    path('', include('apps.sportsbook.urls')),    # events/, bets/
    path('', include('apps.casino.urls')),        # casino/games/
    path('', include('apps.promotions.urls')),    # promotions/
    path('', include('apps.livechat.urls')),      # chat/
    path('health/', views.health),
    path('admin/stats/', views.admin_stats),
]

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/', include(api_patterns)),
]
