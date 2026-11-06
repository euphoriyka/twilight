"""Модели клуба = таблицы computers, tariffs, bookings, sessions, payments из xlsx-спецификации.

Расширения схемы (минимальные, см. README):
  * computers.category и tariffs.category — категория Standard/Premium/VIP
    (в xlsx её нет, а на сайте она есть);
  * tariffs.kind — тип тарифа: почасовой или ночной.
"""
from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import F, Func, Q
from django.utils import timezone


class Category(models.TextChoices):
    STD = "std", "Standard"
    PREM = "prem", "Premium"
    VIP = "vip", "VIP"


class TsTzRange(Func):
    """tstzrange(start, end) — нужен для запрета пересечения бронирований."""
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class Computer(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Доступен"
        OCCUPIED = "occupied", "Занят"
        MAINTENANCE = "maintenance", "Обслуживание"

    computer_id = models.AutoField(primary_key=True)
    computer_number = models.IntegerField("Номер места", unique=True)
    computer_name = models.CharField("Название", max_length=100)
    specifications = models.CharField("Характеристики", max_length=255, null=True, blank=True)
    status = models.CharField("Состояние", max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    category = models.CharField("Категория", max_length=10, choices=Category.choices, default=Category.STD)

    class Meta:
        db_table = "computers"
        ordering = ["computer_number"]
        verbose_name = "Компьютер"
        verbose_name_plural = "Компьютеры"

    def __str__(self):
        return f"№{self.computer_number} {self.computer_name}"


class Tariff(models.Model):
    class Kind(models.TextChoices):
        HOUR = "hour", "Почасовой"
        NIGHT = "night", "Ночной (23:00–08:00)"

    tariff_id = models.AutoField(primary_key=True)
    tariff_name = models.CharField("Название", max_length=100, unique=True)
    price_per_hour = models.DecimalField("Стоимость часа", max_digits=10, decimal_places=2)
    description = models.CharField("Описание", max_length=255, null=True, blank=True)
    is_active = models.BooleanField("Доступен", default=True)
    category = models.CharField("Категория", max_length=10, choices=Category.choices, default=Category.STD)
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices, default=Kind.HOUR)

    class Meta:
        db_table = "tariffs"
        ordering = ["category", "kind"]
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"
        constraints = [
            models.CheckConstraint(condition=Q(price_per_hour__gte=0), name="tariff_price_gte_0"),
        ]

    def __str__(self):
        return self.tariff_name


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        CONFIRMED = "confirmed", "Подтверждено"
        CANCELLED = "cancelled", "Отменено"
        COMPLETED = "completed", "Завершено"

    ACTIVE = ("pending", "confirmed")  # статусы, которые занимают время компьютера

    booking_id = models.AutoField(primary_key=True)
    # PROTECT: нельзя удалить пользователя/компьютер, у которого есть история.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    computer = models.ForeignKey(Computer, on_delete=models.PROTECT, related_name="bookings")
    start_time = models.DateTimeField("Начало", db_index=True)
    end_time = models.DateTimeField("Окончание")
    status = models.CharField("Статус", max_length=20, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField("Создано", default=timezone.now)

    class Meta:
        db_table = "bookings"
        ordering = ["-start_time"]
        verbose_name = "Бронирование"
        verbose_name_plural = "Бронирования"
        constraints = [
            models.CheckConstraint(condition=Q(end_time__gt=F("start_time")), name="booking_end_after_start"),
            # PostgreSQL сам не даст создать два активных бронирования
            # одного компьютера с пересекающимся временем (нужен btree_gist).
            ExclusionConstraint(
                name="booking_no_overlap",
                expressions=[
                    (TsTzRange("start_time", "end_time", RangeBoundary()), RangeOperators.OVERLAPS),
                    ("computer", RangeOperators.EQUAL),
                ],
                condition=Q(status__in=["pending", "confirmed"]),
            ),
        ]

    def __str__(self):
        return f"Бронь #{self.pk} · {self.computer} · {self.start_time:%d.%m %H:%M}"


class GameSession(models.Model):
    """Таблица `sessions` (имя модели другое, чтобы не путать с сессиями Django)."""
    session_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="game_sessions")
    computer = models.ForeignKey(Computer, on_delete=models.PROTECT, related_name="game_sessions")
    tariff = models.ForeignKey(Tariff, on_delete=models.PROTECT, related_name="game_sessions")
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="game_session")
    start_time = models.DateTimeField("Начало")
    end_time = models.DateTimeField("Окончание", null=True, blank=True)
    # Итог фиксируется при завершении, поэтому история не меняется при смене цен.
    total_amount = models.DecimalField("Итого", max_digits=10, decimal_places=2, default=0)

    class Meta:
        db_table = "sessions"
        ordering = ["-start_time"]
        verbose_name = "Игровая сессия"
        verbose_name_plural = "Игровые сессии"
        constraints = [
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="session_total_gte_0"),
            models.CheckConstraint(
                condition=Q(end_time__isnull=True) | Q(end_time__gte=F("start_time")),
                name="session_end_after_start"),
            # на одном компьютере не больше одной активной сессии
            models.UniqueConstraint(fields=["computer"], condition=Q(end_time__isnull=True),
                                    name="one_active_session_per_computer"),
        ]

    @property
    def is_active(self):
        return self.end_time is None

    def __str__(self):
        return f"Сессия #{self.pk} · {self.computer}"


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Наличные"
        CARD = "card", "Карта"
        ONLINE = "online", "Онлайн"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает оплаты"
        PAID = "paid", "Оплачено"
        REFUNDED = "refunded", "Возвращено"
        FAILED = "failed", "Ошибка оплаты"

    payment_id = models.AutoField(primary_key=True)
    session = models.ForeignKey(GameSession, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField("Сумма", max_digits=10, decimal_places=2)
    payment_method = models.CharField("Способ", max_length=10, choices=Method.choices)
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField("Оплачено", null=True, blank=True)
    transaction_number = models.CharField("Номер транзакции", max_length=100, null=True, blank=True, unique=True)

    class Meta:
        db_table = "payments"
        ordering = ["-payment_id"]
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_gt_0"),
            # защита от двойного нажатия: у сессии один «живой» платёж (ожидает/оплачен)
            models.UniqueConstraint(fields=["session"], condition=Q(status__in=["pending", "paid"]),
                                    name="one_live_payment_per_session"),
        ]

    def __str__(self):
        return f"Платёж #{self.pk} · {self.amount} ₽ · {self.get_status_display()}"
