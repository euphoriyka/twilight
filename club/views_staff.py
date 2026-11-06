"""Админ-панель /admin-panel/ — только для role='admin' (проверка на сервере)."""
from datetime import date as date_cls, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import staff_required
from accounts.models import User

from . import services
from .forms import (ComputerForm, PaymentForm, PeriodForm, StartSessionForm, TariffForm)
from .models import Booking, Computer, GameSession, Payment, Tariff


def _next(request, default):
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect(default)


def _page(request, qs):
    return Paginator(qs, 15).get_page(request.GET.get("page"))


def _resolve_period(request):
    today = timezone.localdate()
    preset = request.GET.get("period", "today")
    if preset == "week":
        return preset, today - timedelta(days=6), today
    if preset == "month":
        return preset, today - timedelta(days=29), today
    if preset == "custom":
        d_from, d_to = PeriodForm(request.GET).period()
        return preset, d_from, d_to
    return "today", today, today


@staff_required
def dashboard(request):
    preset, d_from, d_to = _resolve_period(request)
    stats = services.period_stats(d_from, d_to)
    return render(request, "staff/dashboard.html", {
        "live": services.live_summary(), "stats": stats, "preset": preset,
        "active_sessions": GameSession.objects.filter(end_time__isnull=True)
        .select_related("user", "computer", "tariff"),
        "pending": Booking.objects.filter(status=Booking.Status.PENDING).select_related("user", "computer")
        .order_by("start_time")[:8],
    })


@staff_required
def stats(request):
    preset, d_from, d_to = _resolve_period(request)
    return render(request, "staff/stats.html", {"stats": services.period_stats(d_from, d_to), "preset": preset})


# ---------- компьютеры ----------
@staff_required
def computers(request):
    return render(request, "staff/computers.html", {"items": Computer.objects.all()})


@staff_required
def computer_edit(request, pk=None):
    obj = get_object_or_404(Computer, pk=pk) if pk else None
    form = ComputerForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        new_status = form.cleaned_data["status"]
        has_active = obj and GameSession.objects.filter(computer=obj, end_time__isnull=True).exists()
        if has_active and new_status != Computer.Status.OCCUPIED:
            form.add_error("status", "На компьютере идёт сессия — статус сменится после её завершения.")
        elif not has_active and new_status == Computer.Status.OCCUPIED:
            form.add_error("status", "Статус «Занят» ставится автоматически при старте сессии.")
        else:
            form.save()
            messages.success(request, "Компьютер сохранён.")
            return redirect("staff:computers")
    return render(request, "staff/form.html", {"form": form, "title": "Компьютер", "back": "staff:computers"})


@staff_required
@require_POST
def computer_status(request, pk):
    c = get_object_or_404(Computer, pk=pk)
    target = request.POST.get("status")
    if target not in (Computer.Status.AVAILABLE, Computer.Status.MAINTENANCE):
        messages.error(request, "Недопустимый статус.")
    elif GameSession.objects.filter(computer=c, end_time__isnull=True).exists():
        messages.error(request, "На компьютере идёт сессия.")
    else:
        c.status = target
        c.save(update_fields=["status"])
        messages.success(request, f"Компьютер №{c.computer_number}: {c.get_status_display()}.")
    return redirect("staff:computers")


# ---------- тарифы (удаления нет: только отключение) ----------
@staff_required
def tariffs(request):
    return render(request, "staff/tariffs.html", {"items": Tariff.objects.all()})


@staff_required
def tariff_edit(request, pk=None):
    obj = get_object_or_404(Tariff, pk=pk) if pk else None
    form = TariffForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Тариф сохранён. История сессий не изменится.")
        return redirect("staff:tariffs")
    return render(request, "staff/form.html", {"form": form, "title": "Тариф", "back": "staff:tariffs"})


@staff_required
@require_POST
def tariff_toggle(request, pk):
    t = get_object_or_404(Tariff, pk=pk)
    t.is_active = not t.is_active
    t.save(update_fields=["is_active"])
    messages.success(request, f"Тариф «{t.tariff_name}»: {'включён' if t.is_active else 'отключён'}.")
    return redirect("staff:tariffs")


# ---------- бронирования ----------
@staff_required
def bookings(request):
    qs = Booking.objects.select_related("user", "computer")
    status, q, date = request.GET.get("status", ""), request.GET.get("q", "").strip(), request.GET.get("date", "")
    if status in Booking.Status.values:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(user__full_name__icontains=q) | Q(user__email__icontains=q) | Q(user__phone__icontains=q))
    if date:
        try:
            day = date_cls.fromisoformat(date)
            d_from, d_to = services.day_bounds(day, day)
            qs = qs.filter(start_time__gte=d_from, start_time__lt=d_to)
        except ValueError:
            messages.error(request, "Неверная дата в фильтре.")
    return render(request, "staff/bookings.html", {
        "page": _page(request, qs), "statuses": Booking.Status.choices,
        "f": {"status": status, "q": q, "date": date},
    })


@staff_required
@require_POST
def booking_action(request, pk):
    mapping = {"confirm": Booking.Status.CONFIRMED, "cancel": Booking.Status.CANCELLED,
               "complete": Booking.Status.COMPLETED}
    target = mapping.get(request.POST.get("action"))
    try:
        if not target:
            raise services.ServiceError("Неизвестное действие.")
        services.set_booking_status(pk, target)
        messages.success(request, "Статус бронирования обновлён.")
    except (services.ServiceError, Booking.DoesNotExist) as e:
        messages.error(request, str(e) if isinstance(e, services.ServiceError) else "Бронирование не найдено.")
    return _next(request, "staff:bookings")


# ---------- сессии ----------
@staff_required
def sessions(request):
    qs = GameSession.objects.select_related("user", "computer", "tariff", "booking")
    if request.GET.get("active") == "1":
        qs = qs.filter(end_time__isnull=True)
    return render(request, "staff/sessions.html", {"page": _page(request, qs),
                                                   "only_active": request.GET.get("active") == "1"})


@staff_required
def session_start(request):
    initial = {}
    booking = None
    if request.GET.get("booking"):
        booking = get_object_or_404(Booking.objects.select_related("computer", "user"), pk=request.GET["booking"])
        initial = {"booking_id": booking.pk, "computer": booking.computer}
    form = StartSessionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            user = None
            if not d["booking_id"]:
                if not d["computer"] or not d["client_email"]:
                    raise services.ServiceError("Укажите компьютер и email клиента.")
                user = User.objects.filter(email__iexact=d["client_email"], role=User.Role.CLIENT).first()
                if not user:
                    raise services.ServiceError("Клиент с таким email не найден.")
            services.start_session(d["tariff"].pk, computer_id=d["computer"].pk if d["computer"] else None,
                                   booking_id=d["booking_id"] or None, user=user)
            messages.success(request, "Сессия начата.")
            return redirect("staff:sessions")
        except services.ServiceError as e:
            form.add_error(None, str(e))
    return render(request, "staff/session_start.html", {"form": form, "booking": booking})


@staff_required
@require_POST
def session_finish(request, pk):
    try:
        s = services.finish_session(pk)
        messages.success(request, f"Сессия завершена. К оплате: {s.total_amount} ₽.")
    except services.ServiceError as e:
        messages.error(request, str(e))
    return _next(request, "staff:sessions")


# ---------- платежи ----------
@staff_required
def payments(request):
    qs = Payment.objects.select_related("session__user", "session__computer")
    status = request.GET.get("status", "")
    if status in Payment.Status.values:
        qs = qs.filter(status=status)
    return render(request, "staff/payments.html", {"page": _page(request, qs), "status": status,
                                                   "statuses": Payment.Status.choices})


@staff_required
def payment_new(request):
    unpaid = GameSession.objects.filter(end_time__isnull=False, total_amount__gt=0) \
        .exclude(payments__status__in=[Payment.Status.PENDING, Payment.Status.PAID])
    form = PaymentForm(request.POST or None, initial={"session": request.GET.get("session")})
    form.fields["session"].queryset = unpaid.select_related("user", "computer")
    if request.method == "POST" and form.is_valid():
        try:
            p = services.register_payment(form.cleaned_data["session"].pk, form.cleaned_data["payment_method"])
            messages.success(request, f"Платёж принят: {p.amount} ₽ ({p.transaction_number}).")
            return redirect("staff:payments")
        except services.ServiceError as e:
            form.add_error(None, str(e))
    return render(request, "staff/form.html", {"form": form, "title": "Принять оплату", "back": "staff:payments"})


@staff_required
@require_POST
def payment_refund(request, pk):
    try:
        services.refund_payment(pk)
        messages.success(request, "Платёж отмечен как возвращённый.")
    except (services.ServiceError, Payment.DoesNotExist) as e:
        messages.error(request, str(e) if isinstance(e, services.ServiceError) else "Платёж не найден.")
    return redirect("staff:payments")
