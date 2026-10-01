from django.urls import path

from .views import SiteIdentityView, SiteThemeView

urlpatterns = [
    path('branding/theme/', SiteThemeView.as_view(), name='site-theme'),
    path('branding/identity/', SiteIdentityView.as_view(), name='site-identity'),
]
