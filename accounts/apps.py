from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"
    verbose_name = "Пользователи"

    def ready(self):
        # В таблице users по спецификации нет колонки last_login,
        # поэтому отключаем стандартное обновление этого поля при входе.
        from django.contrib.auth import user_logged_in
        from django.contrib.auth.models import update_last_login
        user_logged_in.disconnect(update_last_login, dispatch_uid="update_last_login")
