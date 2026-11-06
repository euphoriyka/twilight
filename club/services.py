"""Вся бизнес-логика клуба. Views только вызывают эти функции."""
import math
import uuid
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from .models import Booking, Computer, GameSession, Payment, Tariff

MIN_BOOKING = timedelta(hours=1)
MAX_BOOKING = timedelta(hours=12)
MAX_ADVANCE = timedelta(days=30)
EARLY_START = timedelta(minutes=15)  # за сколько можно начать сессию по брони
NIGHT_START_HOUR, NIGHT_END_HOUR = 23, 8


class ServiceError(Exception):
    """Понятная пользователю ошибка бизнес-правил."""


# ---------- стоимость ----------
def billable_hours(start, end):
    """Округляем вверх до полного часа, минимум 1 час."""
    minutes = (end - start).total_seconds() / 60
    return max(1, math.ceil(minutes / 60))


def price_for(tariff, start, end):
    return (tariff.price_per_hour * billable_hours(start, end)).quantize(Decimal("0.01"))


def price_for_hours(tariff, hours):
    return (tariff.price_per_hour * int(hours)).quantize(Decimal("0.01"))


def is_night_interval(start, end):
    """Интервал целиком внутри одной ночи 23:00–08:00 (по времени клуба)."""
    s = timezone.localtime(start)
    if s.hour >= NIGHT_START_HOUR:
        limit = (s + timedelta(days=1)).replace(hour=NIGHT_END_HOUR, minute=0, second=0, microsecond=0)
    elif s.hour < NIGHT_END_HOUR:
        limit = s.replace(hour=NIGHT_END_HOUR, minute=0, second=0, microsecond=0)
    else:
        return False
    return end <= limit


def check_tariff_fits(tariff, computer, start, end):
    if not tariff.is_active:
        raise ServiceError("Этот тариф сейчас недоступен.")
    if tariff.category != computer.category:
        raise ServiceError("Тариф относится к другой категории компьютеров.")
    if tariff.kind == Tariff.Kind.NIGHT and not is_night_interval(start, end):
        raise ServiceError("Ночной тариф действует только с 23:00 до 08:00.")


# ---------- доступность ----------
def parse_interval(start, end):
    if start is None or end is None or timezone.is_naive(start) or timezone.is_naive(end):
        raise ServiceError("Укажите корректные дату и время.")
    return start, end


def validate_interval(start, end, now=None):
    now = now or timezone.now()
    if end <= start:
        raise ServiceError("Время окончания должно быть позже начала.")
    if start < now - timedelta(minutes=1):
        raise ServiceError("Нельзя бронировать время в прошлом.")
    if end - start < MIN_BOOKING:
        raise ServiceError("Минимальная длительность — 1 час.")
    if end - start > MAX_BOOKING:
        raise ServiceError("Максимальная длительность — 12 часов.")
    if start > now + MAX_ADVANCE:
        raise ServiceError("Бронировать можно не более чем на 30 дней вперёд.")


def busy_reason(computer, start, end, exclude_booking_id=None, now=None):
    """Строка с причиной, почему компьютер нельзя занять в интервале, либо None."""
    now = now or timezone.now()
    if computer.status == Computer.Status.MAINTENANCE:
        return "Компьютер на обслуживании."
    overlapping = Booking.objects.filter(
        computer=computer, status__in=Booking.ACTIVE, start_time__lt=end, end_time__gt=start)
    if exclude_booking_id:
        overlapping = overlapping.exclude(pk=exclude_booking_id)
    if overlapping.exists():
        return "На это время место уже забронировано."
    for s in GameSession.objects.filter(computer=computer, end_time__isnull=True).select_related("booking"):
        # у активной сессии без брони конец неизвестен: считаем, что занято «сейчас»
        until = s.booking.end_time if s.booking_id else max(now, s.start_time)
        if s.start_time < end and until > start:
            return "Сейчас на этом месте идёт сессия."
    return None


def availability_map(start, end):
    """{computer_id: причина или None} для всех компьютеров (карта зала, кабинет)."""
    now = timezone.now()
    return {c.pk: busy_reason(c, start, end, now=now) for c in Computer.objects.all()}


# ---------- бронирование ----------
@transaction.atomic
def create_booking(user, computer_id, start, end):
    start, end = parse_interval(start, end)
    validate_interval(start, end)
    try:
        # блокируем строку компьютера, чтобы две заявки не прошли проверку одновременно
        computer = Computer.objects.select_for_update().get(pk=computer_id)
    except Computer.DoesNotExist:
        raise ServiceError("Компьютер не найден.")
    reason = busy_reason(computer, start, end)
    if reason:
        raise ServiceError(reason)
    try:
        with transaction.atomic():
            return Booking.objects.create(user=user, computer=computer, start_time=start,
                                          end_time=end, status=Booking.Status.PENDING)
    except IntegrityError:  # последний рубеж — ограничение PostgreSQL
        raise ServiceError("На это время место уже занято.")


@transaction.atomic
def cancel_booking(booking_id, user=None):
    """Клиент отменяет только свою будущую бронь; админ (user=None) — любую активную."""
    try:
        booking = Booking.objects.select_for_update().get(pk=booking_id)
    except Booking.DoesNotExist:
        raise ServiceError("Бронирование не найдено.")
    if user is not None:
        if booking.user_id != user.pk:
            raise ServiceError("Бронирование не найдено.")  # чужие не раскрываем
        if booking.start_time <= timezone.now():
            raise ServiceError("Начавшуюся бронь отменить нельзя — обратитесь к администратору.")
    if booking.status not in Booking.ACTIVE:
        raise ServiceError("Это бронирование уже нельзя отменить.")
    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=["status"])
    return booking


@transaction.atomic
def set_booking_status(booking_id, new_status):
    """Переходы статусов брони для администратора."""
    allowed = {
        Booking.Status.PENDING: {Booking.Status.CONFIRMED, Booking.Status.CANCELLED},
        Booking.Status.CONFIRMED: {Booking.Status.COMPLETED, Booking.Status.CANCELLED},
    }
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if new_status not in allowed.get(booking.status, set()):
        raise ServiceError("Такой переход статуса недопустим.")
    if new_status == Booking.Status.COMPLETED and hasattr(booking, "game_session") \
            and booking.game_session.end_time is None:
        raise ServiceError("Сначала завершите связанную сессию.")
    booking.status = new_status
    booking.save(update_fields=["status"])
    return booking


# ---------- сессии ----------
@transaction.atomic
def start_session(tariff_id, computer_id=None, booking_id=None, user=None):
    now = timezone.now()
    booking = None
    if booking_id:
        try:
            booking = Booking.objects.select_for_update().get(pk=booking_id)
        except Booking.DoesNotExist:
            raise ServiceError("Бронирование не найдено.")
        if booking.status != Booking.Status.CONFIRMED:
            raise ServiceError("Сессию можно начать только по подтверждённой брони.")
        if hasattr(booking, "game_session"):
            raise ServiceError("По этой брони сессия уже создана.")
        if not (booking.start_time - EARLY_START <= now < booking.end_time):
            raise ServiceError("Сейчас не время этой брони.")
        computer_id, user = booking.computer_id, booking.user
    if not computer_id or user is None:
        raise ServiceError("Укажите компьютер и клиента.")
    try:
        computer = Computer.objects.select_for_update().get(pk=computer_id)
        tariff = Tariff.objects.get(pk=tariff_id)
    except (Computer.DoesNotExist, Tariff.DoesNotExist):
        raise ServiceError("Компьютер или тариф не найдены.")
    if computer.status == Computer.Status.MAINTENANCE:
        raise ServiceError("Компьютер на обслуживании.")
    if computer.status == Computer.Status.OCCUPIED or \
            GameSession.objects.filter(computer=computer, end_time__isnull=True).exists():
        raise ServiceError("Компьютер уже занят.")
    horizon = booking.end_time if booking else now + MIN_BOOKING
    check_tariff_fits(tariff, computer, now, max(horizon, now + timedelta(minutes=1)))
    if not booking:
        clash = Booking.objects.filter(computer=computer, status__in=Booking.ACTIVE,
                                       start_time__lt=now + MIN_BOOKING, end_time__gt=now)
        if clash.exists():
            raise ServiceError("На ближайший час есть бронирование этого места.")
    session = GameSession.objects.create(user=user, computer=computer, tariff=tariff,
                                         booking=booking, start_time=now)
    computer.status = Computer.Status.OCCUPIED
    computer.save(update_fields=["status"])
    return session


@transaction.atomic
def finish_session(session_id):
    try:
        session = GameSession.objects.select_for_update().select_related("tariff", "computer", "booking") \
            .get(pk=session_id)
    except GameSession.DoesNotExist:
        raise ServiceError("Сессия не найдена.")
    if session.end_time is not None:
        raise ServiceError("Сессия уже завершена.")
    now = timezone.now()
    session.end_time = now
    session.total_amount = price_for(session.tariff, session.start_time, now)
    session.save(update_fields=["end_time", "total_amount"])
    Computer.objects.filter(pk=session.computer_id).update(status=Computer.Status.AVAILABLE)
    if session.booking_id:
        Booking.objects.filter(pk=session.booking_id).update(status=Booking.Status.COMPLETED)
    return session


# ---------- платежи ----------
@transaction.atomic
def register_payment(session_id, method):
    if method not in Payment.Method.values:
        raise ServiceError("Выберите способ оплаты.")
    try:
        session = GameSession.objects.select_for_update().get(pk=session_id)
    except GameSession.DoesNotExist:
        raise ServiceError("Сессия не найдена.")
    if session.end_time is None:
        raise ServiceError("Сначала завершите сессию.")
    if session.total_amount <= 0:
        raise ServiceError("Сумма к оплате равна нулю.")
    if Payment.objects.filter(session=session, status__in=[Payment.Status.PENDING, Payment.Status.PAID]).exists():
        raise ServiceError("Платёж по этой сессии уже зарегистрирован.")
    try:
        with transaction.atomic():
            return Payment.objects.create(
                session=session, amount=session.total_amount, payment_method=method,
                status=Payment.Status.PAID, paid_at=timezone.now(),
                transaction_number="DEMO-" + uuid.uuid4().hex[:12].upper())  # демо: настоящего эквайринга нет
    except IntegrityError:
        raise ServiceError("Платёж по этой сессии уже зарегистрирован.")


@transaction.atomic
def refund_payment(payment_id):
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    if payment.status != Payment.Status.PAID:
        raise ServiceError("Вернуть можно только оплаченный платёж.")
    payment.status = Payment.Status.REFUNDED
    payment.save(update_fields=["status"])
    return payment


# ---------- статистика ----------
def day_bounds(date_from, date_to):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min), tz)
    return start, end


def _clip_minutes(s_start, s_end, p_start, p_end):
    a, b = max(s_start, p_start), min(s_end, p_end)
    return max(0.0, (b - a).total_seconds() / 60)


def period_stats(date_from, date_to):
    p_start, p_end = day_bounds(date_from, date_to)
    now = timezone.now()
    paid = Payment.objects.filter(status=Payment.Status.PAID, paid_at__gte=p_start, paid_at__lt=p_end)
    revenue = paid.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    finished = GameSession.objects.filter(end_time__gte=p_start, end_time__lt=p_end)
    avg_check = finished.aggregate(a=Avg("total_amount"))["a"] or Decimal("0")
    bookings = Booking.objects.filter(start_time__gte=p_start, start_time__lt=p_end)
    b_total = bookings.count()
    b_cancel = bookings.filter(status=Booking.Status.CANCELLED).count()

    sessions = list(GameSession.objects.filter(start_time__lt=p_end).select_related("computer", "tariff")
                    .exclude(end_time__lt=p_start))
    computers = list(Computer.objects.all())
    period_minutes = max(1.0, (min(p_end, max(now, p_start)) - p_start).total_seconds() / 60)
    busy = defaultdict(float)
    by_hour = {"Ночь 23–08": 0, "Утро 08–12": 0, "День 12–18": 0, "Вечер 18–23": 0}
    by_tariff = defaultdict(int)
    for s in sessions:
        busy[s.computer_id] += _clip_minutes(s.start_time, s.end_time or now, p_start, p_end)
        if p_start <= s.start_time < p_end:
            h = timezone.localtime(s.start_time).hour
            key = ("Ночь 23–08" if h >= 23 or h < 8 else "Утро 08–12" if h < 12
                   else "День 12–18" if h < 18 else "Вечер 18–23")
            by_hour[key] += 1
            by_tariff[s.tariff.tariff_name] += 1
    per_computer = [{"computer": c, "percent": round(min(100, busy[c.pk] / period_minutes * 100), 1)}
                    for c in computers]
    total_busy = sum(busy.values())
    utilization = round(min(100, total_busy / (period_minutes * max(1, len(computers))) * 100), 1)
    return {
        "revenue": revenue, "finished_count": finished.count(), "avg_check": avg_check,
        "bookings_total": b_total, "bookings_cancelled": b_cancel,
        "cancel_percent": round(b_cancel / b_total * 100, 1) if b_total else 0,
        "utilization": utilization, "per_computer": sorted(per_computer, key=lambda x: -x["percent"]),
        "by_hour": list(by_hour.items()), "by_tariff": sorted(by_tariff.items(), key=lambda x: -x[1]),
        "date_from": date_from, "date_to": date_to,
    }


def live_summary():
    """Текущее состояние клуба для дашборда."""
    comps = Computer.objects.values("status").annotate(n=Count("pk"))
    counts = {c["status"]: c["n"] for c in comps}
    return {
        "total": sum(counts.values()),
        "available": counts.get("available", 0),
        "occupied": counts.get("occupied", 0),
        "maintenance": counts.get("maintenance", 0),
        "active_sessions": GameSession.objects.filter(end_time__isnull=True).count(),
        "pending_bookings": Booking.objects.filter(status=Booking.Status.PENDING).count(),
    }
