from django.urls import path

from . import views_staff as v

app_name = "staff"
urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("stats/", v.stats, name="stats"),
    path("computers/", v.computers, name="computers"),
    path("computers/new/", v.computer_edit, name="computer_new"),
    path("computers/<int:pk>/edit/", v.computer_edit, name="computer_edit"),
    path("computers/<int:pk>/status/", v.computer_status, name="computer_status"),
    path("tariffs/", v.tariffs, name="tariffs"),
    path("tariffs/new/", v.tariff_edit, name="tariff_new"),
    path("tariffs/<int:pk>/edit/", v.tariff_edit, name="tariff_edit"),
    path("tariffs/<int:pk>/toggle/", v.tariff_toggle, name="tariff_toggle"),
    path("bookings/", v.bookings, name="bookings"),
    path("bookings/<int:pk>/action/", v.booking_action, name="booking_action"),
    path("sessions/", v.sessions, name="sessions"),
    path("sessions/start/", v.session_start, name="session_start"),
    path("sessions/<int:pk>/finish/", v.session_finish, name="session_finish"),
    path("payments/", v.payments, name="payments"),
    path("payments/new/", v.payment_new, name="payment_new"),
    path("payments/<int:pk>/refund/", v.payment_refund, name="payment_refund"),
]
