from django.contrib import admin
from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("user_id", "full_name", "email", "phone", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("full_name", "email", "phone")
    readonly_fields = ("password", "created_at")
    # Пароли меняются только через штатные механизмы Django (хэш), не руками.

    def has_add_permission(self, request):
        return False  # пользователей создаём через регистрацию / createsuperuser, чтобы пароль всегда хэшировался
