from django.contrib import admin
from django.urls import include, path

from club import views_public

urlpatterns = [
    path("", views_public.home, name="home"),
    path("api/computers/", views_public.api_computers, name="api_computers"),
    path("api/quote/", views_public.api_quote, name="api_quote"),
    path("api/book/", views_public.api_book, name="api_book"),
    path("account/", include("club.urls_account")),
    path("admin-panel/", include("club.urls_staff")),
    path("django-admin/", admin.site.urls),  # запасной вход для разработчика
]
