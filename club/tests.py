"""Тесты бизнес-логики и доступа. Нужен PostgreSQL (ExclusionConstraint):
    python manage.py test
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Booking, Computer, GameSession, Payment, Tariff

User = get_user_model()


class Base(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user("c1@test.local", "Pass-12345-x", full_name="Клиент", phone="+79001112233")
        self.other = User.objects.create_user("c2@test.local", "Pass-12345-x", full_name="Другой", phone="+79001112244")
        self.admin = User.objects.create_user("a@test.local", "Pass-12345-x", full_name="Админ", phone="+79000000000",
                                              role=User.Role.ADMIN)
        self.pc = Computer.objects.create(computer_number=1, computer_name="TW-01", category="std")
        self.pc2 = Computer.objects.create(computer_number=2, computer_name="TW-02", category="std")
        self.hour = Tariff.objects.create(tariff_name="Std h", price_per_hour=Decimal("150"), category="std", kind="hour")
        self.night = Tariff.objects.create(tariff_name="Std n", price_per_hour=Decimal("110"), category="std", kind="night")
        self.start = (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)


class BookingTests(Base):
    def test_create_ok(self):
        b = services.create_booking(self.client_user, self.pc.pk, self.start, self.start + timedelta(hours=2))
        self.assertEqual(b.status, Booking.Status.PENDING)

    def test_overlap_rejected(self):
        services.create_booking(self.client_user, self.pc.pk, self.start, self.start + timedelta(hours=2))
        with self.assertRaises(services.ServiceError):
            services.create_booking(self.other, self.pc.pk, self.start + timedelta(hours=1), self.start + timedelta(hours=3))

    def test_adjacent_allowed(self):
        services.create_booking(self.client_user, self.pc.pk, self.start, self.start + timedelta(hours=2))
        services.create_booking(self.other, self.pc.pk, self.start + timedelta(hours=2), self.start + timedelta(hours=4))

    def test_other_computer_allowed(self):
        services.create_booking(self.client_user, self.pc.pk, self.start, self.start + timedelta(hours=2))
        services.create_booking(self.other, self.pc2.pk, self.start, self.start + timedelta(hours=2))

    def test_past_and_bad_interval_rejected(self):
        past = timezone.now() - timedelta(days=1)
        with self.assertRaises(services.ServiceError):
            services.create_booking(self.client_user, self.pc.pk, past, past + timedelta(hours=2))
        with self.assertRaises(services.ServiceError):
            services.create_booking(self.client_user, self.pc.pk, self.start, self.start - timedelta(hours=1))
        with self.assertRaises(services.ServiceError):
            services.create_booking(self.client_user, self.pc.pk, self.start, self.start + timedelta(minutes=20))

    def test_maintenance_rejected(self):
        self.pc.status = Computer.Status.MAINTENANCE
        self.pc.save()
        with self.assertRaises(services.ServiceError):
            services.create_booking(self.client_user, self.pc.pk, self.start, self.start + timedelta(hours=2))

    def test_cancelled_frees_slot(self):
        b = services.create_booking(self.client_user, self.pc.pk, self.start, self.start + timedelta(hours=2))
        services.cancel_booking(b.pk, user=self.client_user)
        services.create_booking(self.other, self.pc.pk, self.start, self.start + timedelta(hours=2))

    def test_cannot_cancel_foreign_booking(self):
        b = services.create_booking(self.client_user, self.pc.pk, self.start, self.start + timedelta(hours=2))
        with self.assertRaises(services.ServiceError):
            services.cancel_booking(b.pk, user=self.other)


class SessionPaymentTests(Base):
    def test_cost_rounding(self):
        s = timezone.now()
        self.assertEqual(services.price_for(self.hour, s, s + timedelta(minutes=10)), Decimal("150.00"))
        self.assertEqual(services.price_for(self.hour, s, s + timedelta(minutes=61)), Decimal("300.00"))

    def test_session_flow_and_payment(self):
        s = services.start_session(self.hour.pk, computer_id=self.pc.pk, user=self.client_user)
        self.pc.refresh_from_db()
        self.assertEqual(self.pc.status, Computer.Status.OCCUPIED)
        with self.assertRaises(services.ServiceError):  # второй старт на занятом ПК
            services.start_session(self.hour.pk, computer_id=self.pc.pk, user=self.other)
        with self.assertRaises(services.ServiceError):  # оплата до завершения
            services.register_payment(s.pk, "cash")
        done = services.finish_session(s.pk)
        self.assertEqual(done.total_amount, Decimal("150.00"))
        self.pc.refresh_from_db()
        self.assertEqual(self.pc.status, Computer.Status.AVAILABLE)
        p = services.register_payment(s.pk, "card")
        self.assertEqual(p.status, Payment.Status.PAID)
        with self.assertRaises(services.ServiceError):  # повторная оплата
            services.register_payment(s.pk, "card")
        with self.assertRaises(services.ServiceError):  # повторное завершение
            services.finish_session(s.pk)

    def test_refund_allows_new_payment(self):
        s = services.start_session(self.hour.pk, computer_id=self.pc.pk, user=self.client_user)
        services.finish_session(s.pk)
        p = services.register_payment(s.pk, "cash")
        services.refund_payment(p.pk)
        services.register_payment(s.pk, "cash")

    def test_wrong_category_tariff_rejected(self):
        vip = Computer.objects.create(computer_number=9, computer_name="V", category="vip")
        with self.assertRaises(services.ServiceError):
            services.start_session(self.hour.pk, computer_id=vip.pk, user=self.client_user)

    def test_start_by_confirmed_booking_only(self):
        now = timezone.now()
        b = Booking.objects.create(user=self.client_user, computer=self.pc, start_time=now,
                                   end_time=now + timedelta(hours=2), status=Booking.Status.PENDING)
        with self.assertRaises(services.ServiceError):
            services.start_session(self.hour.pk, booking_id=b.pk)
        b.status = Booking.Status.CONFIRMED
        b.save()
        s = services.start_session(self.hour.pk, booking_id=b.pk)
        self.assertEqual(s.user, self.client_user)
        services.finish_session(s.pk)
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.COMPLETED)


class AccessTests(Base):
    def test_guest_redirected(self):
        self.assertEqual(self.client.get(reverse("account:home")).status_code, 302)
        self.assertEqual(self.client.get(reverse("staff:dashboard")).status_code, 302)

    def test_client_forbidden_in_staff_panel(self):
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse("staff:dashboard")).status_code, 403)
        self.assertEqual(self.client.post(reverse("staff:session_finish", args=[1])).status_code, 403)

    def test_admin_opens_panel_and_pages(self):
        self.client.force_login(self.admin)
        for name in ["dashboard", "stats", "computers", "tariffs", "bookings", "sessions", "payments"]:
            self.assertEqual(self.client.get(reverse(f"staff:{name}")).status_code, 200, name)

    def test_client_sees_only_own_data(self):
        services.create_booking(self.other, self.pc.pk, self.start, self.start + timedelta(hours=2))
        self.client.force_login(self.client_user)
        r = self.client.get(reverse("account:bookings"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["page"]), 0)

    def test_registration_cannot_set_admin_role(self):
        r = self.client.post(reverse("account:register"), {
            "full_name": "Хакер", "email": "h@test.local", "phone": "+79001234567",
            "password1": "Strong-Pass-123", "password2": "Strong-Pass-123", "role": "admin"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(User.objects.get(email="h@test.local").role, User.Role.CLIENT)

    def test_home_and_api(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        r = self.client.get("/api/quote/", {"tariff_id": self.hour.pk, "hours": 3})
        self.assertEqual(r.json()["total"], "450.00")
        self.assertEqual(self.client.post("/api/book/", "{}", content_type="application/json").status_code, 401)
