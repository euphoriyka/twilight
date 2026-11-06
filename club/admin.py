from django.contrib import admin

from .models import Booking, Computer, GameSession, Payment, Tariff

# Запасной вход /admin/ для разработчика. Основной интерфейс — /admin-panel/.
admin.site.register(Computer, list_display=("computer_number", "computer_name", "category", "status"))
admin.site.register(Tariff, list_display=("tariff_name", "category", "kind", "price_per_hour", "is_active"))
admin.site.register(Booking, list_display=("booking_id", "user", "computer", "start_time", "end_time", "status"),
                    list_filter=("status",))
admin.site.register(GameSession, list_display=("session_id", "user", "computer", "tariff", "start_time", "end_time",
                                               "total_amount"))
admin.site.register(Payment, list_display=("payment_id", "session", "amount", "payment_method", "status",
                                           "transaction_number"), list_filter=("status",))
