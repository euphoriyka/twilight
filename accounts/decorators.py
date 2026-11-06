from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def client_required(view):
    """Личный кабинет: нужен вход. Администратора отправляем в его панель."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if request.user.is_admin_role:
            return redirect("staff:dashboard")
        return view(request, *args, **kwargs)
    return wrapper


def staff_required(view):
    """Админ-панель: гость -> вход, обычный клиент -> 403 (проверка на сервере)."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_admin_role:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper
