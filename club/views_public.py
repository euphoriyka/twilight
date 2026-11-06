"""Главная страница и небольшой JSON API для неё."""
import json
from datetime import timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import services
from .forms import end_from_hours, parse_local_datetime
from .models import Category, Computer, Tariff


@ensure_csrf_cookie
def home(request):
    now = timezone.now()
    busy = services.availability_map(now, now + timedelta(hours=1))
    computers = list(Computer.objects.all())
    tariffs = list(Tariff.objects.filter(is_active=True))
    rows = []
    for key, label in Category.choices:
        row = {"key": key, "label": label, "hour": None, "night": None}
        for t in tariffs:
            if t.category == key:
                row[t.kind] = t
        rows.append(row)
    rate = {key: next((t.price_per_hour for t in tariffs if t.category == key and t.kind == "hour"), None)
            for key, _ in Category.choices}
    seats = [{"c": c, "reason": busy.get(c.pk), "rate": rate.get(c.category)} for c in computers]
    tariffs_json = [{"id": t.pk, "name": t.tariff_name, "category": t.category, "kind": t.kind,
                     "price": str(t.price_per_hour)} for t in tariffs]
    return render(request, "index.html", {
        "tariff_rows": rows, "seats": seats, "tariffs_json": tariffs_json,
        "today": timezone.localdate().isoformat(),
    })


@require_GET
def api_computers(request):
    start = parse_datetime(request.GET.get("start", "")) or timezone.now()
    end = parse_datetime(request.GET.get("end", "")) or start + timedelta(hours=1)
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if timezone.is_naive(end):
        end = timezone.make_aware(end)
    if end <= start or end - start > services.MAX_BOOKING:
        return JsonResponse({"error": "Некорректный интервал."}, status=400)
    busy = services.availability_map(start, end)
    return JsonResponse({"computers": [
        {"id": c.pk, "number": c.computer_number, "name": c.computer_name, "category": c.category,
         "specs": c.specifications or "", "available": busy[c.pk] is None, "reason": busy[c.pk] or ""}
        for c in Computer.objects.all()]})


@require_GET
def api_quote(request):
    """Стоимость считает сервер, а не браузер."""
    try:
        tariff = Tariff.objects.get(pk=int(request.GET["tariff_id"]), is_active=True)
        hours = int(request.GET.get("hours", 1))
    except (KeyError, ValueError, Tariff.DoesNotExist):
        return JsonResponse({"error": "Тариф не найден."}, status=400)
    if not 1 <= hours <= 12:
        return JsonResponse({"error": "От 1 до 12 часов."}, status=400)
    return JsonResponse({"total": str(services.price_for_hours(tariff, hours)), "hours": hours,
                         "tariff": tariff.tariff_name})


@require_POST
def api_book(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"ok": False, "error": "Войдите, чтобы забронировать место.", "login": True},
                            status=401)
    if user.is_admin_role:
        return JsonResponse({"ok": False, "error": "Администратор бронирует через админ-панель."}, status=403)
    try:
        data = json.loads(request.body or "{}")
        computer_id = int(data.get("computer_id"))
        hours = int(data.get("hours"))
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Заполните все поля формы."}, status=400)
    start = parse_local_datetime(data.get("date"), data.get("time"))
    if start is None:
        return JsonResponse({"ok": False, "error": "Укажите дату и время."}, status=400)
    try:
        booking = services.create_booking(user, computer_id, start, end_from_hours(start, hours))
    except services.ServiceError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=409)
    return JsonResponse({"ok": True, "message": f"Заявка №{booking.pk} создана и ждёт подтверждения администратора."})
