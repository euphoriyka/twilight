"""Демо-данные для защиты проекта. Безопасно запускать повторно.

  python manage.py seed_demo_data            # создать то, чего ещё нет
  python manage.py seed_demo_data --reset --yes   # удалить ДЕМО-историю и создать заново
"""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from club import services
from club.models import Booking, Category, Computer, GameSession, Payment, Tariff

User = get_user_model()
DEMO_DOMAIN = "@demo.twilight.test"
DEMO_PASSWORD = "Twilight#2026"  # только для демо-пользователей

SPECS = {  # характеристики демонстрационные, не описание реального железа
    Category.STD: "Демо: игровой ПК базового уровня, монитор 24\"",
    Category.PREM: "Демо: повышенная производительность, монитор 27\" 2K",
    Category.VIP: "Демо: максимальная комплектация, отдельная зона",
}
TARIFFS = [  # (категория, тип, цена за час)
    (Category.STD, "hour", 150), (Category.STD, "night", 110),
    (Category.PREM, "hour", 220), (Category.PREM, "night", 165),
    (Category.VIP, "hour", 350), (Category.VIP, "night", 255),
]
CLIENTS = [("Алексей Морозов", "alexey", "+7 900 111-22-01"), ("Мария Лебедева", "maria", "+7 900 111-22-02"),
           ("Игорь Соколов", "igor", "+7 900 111-22-03"), ("Дарья Волкова", "daria", "+7 900 111-22-04")]


class Command(BaseCommand):
    help = "Создаёт демо-пользователей, компьютеры, тарифы и историю клуба."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="пересоздать демо-историю")
        parser.add_argument("--yes", action="store_true", help="подтверждение для --reset")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            if not opts["yes"]:
                raise CommandError("--reset удаляет демо-платежи, сессии и брони. Добавьте --yes.")
            self._reset()
        self._users()
        self._computers()
        self._tariffs()
        if GameSession.objects.filter(user__email__endswith=DEMO_DOMAIN).exists():
            self.stdout.write("История уже есть, пропускаю (используйте --reset --yes для пересоздания).")
        else:
            self._history()
        self.stdout.write(self.style.SUCCESS("Готово."))
        self.stdout.write(f"Админ: admin{DEMO_DOMAIN} / {DEMO_PASSWORD}")
        self.stdout.write(f"Клиент: alexey{DEMO_DOMAIN} / {DEMO_PASSWORD}")

    def _reset(self):
        demo = User.objects.filter(email__endswith=DEMO_DOMAIN)
        Payment.objects.filter(session__user__in=demo).delete()
        GameSession.objects.filter(user__in=demo).delete()
        Booking.objects.filter(user__in=demo).delete()
        Computer.objects.filter(status=Computer.Status.OCCUPIED).update(status=Computer.Status.AVAILABLE)

    def _users(self):
        if not User.objects.filter(email=f"admin{DEMO_DOMAIN}").exists():
            User.objects.create_user(f"admin{DEMO_DOMAIN}", DEMO_PASSWORD, full_name="Админ Демо",
                                     phone="+7 900 000-00-00", role=User.Role.ADMIN)
        for name, nick, phone in CLIENTS:
            if not User.objects.filter(email=f"{nick}{DEMO_DOMAIN}").exists():
                User.objects.create_user(f"{nick}{DEMO_DOMAIN}", DEMO_PASSWORD, full_name=name, phone=phone)

    def _computers(self):
        layout = [(Category.STD, 12), (Category.PREM, 8), (Category.VIP, 4)]
        n = 0
        for cat, count in layout:
            for _ in range(count):
                n += 1
                Computer.objects.update_or_create(
                    computer_number=n,
                    defaults={"computer_name": f"TW-{n:02d}", "category": cat, "specifications": SPECS[cat]})
        # два места «на обслуживании» для наглядности
        Computer.objects.filter(computer_number__in=[7, 19], status=Computer.Status.AVAILABLE) \
            .update(status=Computer.Status.MAINTENANCE)

    def _tariffs(self):
        labels = dict(Category.choices)
        for cat, kind, price in TARIFFS:
            name = f"{labels[cat]} · {'Почасовой' if kind == 'hour' else 'Ночной'}"
            Tariff.objects.update_or_create(
                tariff_name=name,
                defaults={"category": cat, "kind": kind, "price_per_hour": Decimal(price), "is_active": True,
                          "description": "Демо-тариф" + (" (23:00–08:00)" if kind == "night" else "")})

    # --- история ---
    def _comp(self, number):
        return Computer.objects.get(computer_number=number)

    def _hour_tariff(self, comp):
        return Tariff.objects.get(category=comp.category, kind="hour")

    def _finished(self, user, number, start, hours, pay="paid", booking_status=None):
        comp = self._comp(number)
        tariff = self._hour_tariff(comp)
        end = start + timedelta(hours=hours)
        booking = None
        if booking_status:
            booking = Booking.objects.create(user=user, computer=comp, start_time=start, end_time=end,
                                             status=booking_status, created_at=start - timedelta(days=1))
        total = services.price_for(tariff, start, end)
        s = GameSession.objects.create(user=user, computer=comp, tariff=tariff, booking=booking,
                                       start_time=start, end_time=end, total_amount=total)
        if pay:
            Payment.objects.create(
                session=s, amount=total, payment_method=["cash", "card", "online"][s.pk % 3], status=pay,
                paid_at=end if pay in ("paid", "refunded") else None,
                transaction_number=f"DEMO-{uuid.uuid4().hex[:10].upper()}" if pay != "pending" else None)
        return s

    def _history(self):
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        c = {nick: User.objects.get(email=f"{nick}{DEMO_DOMAIN}") for _, nick, _ in CLIENTS}
        users = list(c.values())
        # 14 завершённых сессий за последние 12 дней, разное время суток
        for i in range(14):
            day = now - timedelta(days=1 + i % 12)
            hour = [10, 14, 19, 21, 23, 2][i % 6]
            start = day.replace(hour=hour)
            pay = "refunded" if i == 5 else "failed" if i == 9 else "paid"
            number = 1 + (i * 3) % 24
            if number in (7, 19):  # эти места «на обслуживании»
                number = 2
            self._finished(users[i % 4], number, start, 1 + i % 4, pay=pay,
                           booking_status=Booking.Status.COMPLETED if i % 2 == 0 else None)
        # завершённая сессия с платежом «ожидает»
        self._finished(c["maria"], 14, now - timedelta(hours=6), 2, pay="pending")
        # три активные сессии (компьютеры становятся занятыми)
        for nick, number, mins in [("alexey", 3, 50), ("igor", 15, 95), ("daria", 22, 20)]:
            comp = self._comp(number)
            GameSession.objects.create(user=c[nick], computer=comp, tariff=self._hour_tariff(comp),
                                       start_time=timezone.now() - timedelta(minutes=mins))
            Computer.objects.filter(pk=comp.pk).update(status=Computer.Status.OCCUPIED)
        # будущие брони разных статусов (разные места/время, пересечений нет)
        base = (now + timedelta(days=1)).replace(hour=18)
        plan = [("alexey", 5, 0, 2, "confirmed"), ("maria", 10, 1, 3, "pending"), ("igor", 17, 0, 2, "confirmed"),
                ("daria", 21, 2, 2, "pending"), ("maria", 5, 3, 2, "cancelled"), ("igor", 8, 4, 2, "cancelled")]
        for nick, number, day_shift, hours, status in plan:
            start = base + timedelta(days=day_shift, hours=0 if status != "cancelled" else 1)
            Booking.objects.create(user=c[nick], computer=self._comp(number), start_time=start,
                                   end_time=start + timedelta(hours=hours), status=status)
