"""Личный кабинет клиента /account/ — клиент видит только свои данные."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import client_required

from . import services
from .forms import end_from_hours, parse_local_datetime
from .models import Booking, Category, Computer, GameSession, Payment, Tariff


def _page(request, qs):
    return Paginator(qs, 10).get_page(request.GET.get("page"))


@client_required
def home(request):
    u = request.user
    active = GameSession.objects.filter(user=u, end_time__isnull=True).select_related("computer", "tariff").first()
    upcoming = Booking.objects.filter(user=u, status__in=Booking.ACTIVE, end_time__gte=timezone.now()) \
        .select_related("computer").order_by("start_time")[:5]
    paid = sum(p.amount for p in Payment.objects.filter(session__user=u, status=Payment.Status.PAID))
    return render(request, "account/home.html", {
        "active": active, "upcoming": upcoming, "paid_total": paid,
        "sessions_count": GameSession.objects.filter(user=u, end_time__isnull=False).count(),
    })


@client_required
def computers(request):
    """Свободные места на выбранное время."""
    date, time_, hours = request.GET.get("date"), request.GET.get("time"), request.GET.get("hours", "2")
    start = parse_local_datetime(date, time_)
    rows, error = [], None
    if start:
        try:
            end = end_from_hours(start, hours)
            services.validate_interval(start, end)
            busy = services.availability_map(start, end)
            rows = [{"c": c, "reason": busy[c.pk]} for c in Computer.objects.all()]
        except (services.ServiceError, ValueError) as e:
            error = str(e) if isinstance(e, services.ServiceError) else "Укажите длительность числом."
    return render(request, "account/computers.html", {
        "rows": rows, "error": error, "searched": bool(start), "hours_choices": range(1, 13),
        "date": date or timezone.localdate().isoformat(), "time": time_ or "19:00", "hours": hours,
        "categories": Category.choices,
    })


@client_required
@require_POST
def book(request):
    start = parse_local_datetime(request.POST.get("date"), request.POST.get("time"))
    try:
        if start is None:
            raise services.ServiceError("Укажите дату и время.")
        b = services.create_booking(request.user, int(request.POST.get("computer_id") or 0), start,
                                    end_from_hours(start, int(request.POST.get("hours") or 0)))
        messages.success(request, f"Заявка №{b.pk} создана и ждёт подтверждения администратора.")
    except (services.ServiceError, ValueError) as e:
        messages.error(request, str(e) if isinstance(e, services.ServiceError) else "Проверьте поля формы.")
        return redirect("account:computers")
    return redirect("account:bookings")


@client_required
def bookings(request):
    qs = Booking.objects.filter(user=request.user).select_related("computer")
    return render(request, "account/bookings.html", {"page": _page(request, qs), "now": timezone.now()})


@client_required
@require_POST
def cancel_booking(request, booking_id):
    try:
        services.cancel_booking(booking_id, user=request.user)
        messages.success(request, "Бронирование отменено.")
    except services.ServiceError as e:
        messages.error(request, str(e))
    return redirect("account:bookings")


@client_required
def sessions(request):
    qs = GameSession.objects.filter(user=request.user).select_related("computer", "tariff")
    return render(request, "account/sessions.html", {"page": _page(request, qs)})


@client_required
def payments(request):
    qs = Payment.objects.filter(session__user=request.user).select_related("session__computer")
    return render(request, "account/payments.html", {"page": _page(request, qs)})


@client_required
def tariffs(request):
    return render(request, "account/tariffs.html", {"tariffs": Tariff.objects.filter(is_active=True)})
