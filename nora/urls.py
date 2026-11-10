from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("oauth/", include("social_django.urls", namespace="social")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("mapper.urls")),
]