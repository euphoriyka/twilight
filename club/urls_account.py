from django.urls import path

from accounts import views as auth_views

from . import views_account as v

app_name = "account"
urlpatterns = [
    path("", v.home, name="home"),
    path("login/", auth_views.TwilightLoginView.as_view(), name="login"),
    path("register/", auth_views.register, name="register"),
    path("logout/", auth_views.logout_view, name="logout"),
    path("computers/", v.computers, name="computers"),
    path("book/", v.book, name="book"),
    path("bookings/", v.bookings, name="bookings"),
    path("bookings/<int:booking_id>/cancel/", v.cancel_booking, name="cancel_booking"),
    path("sessions/", v.sessions, name="sessions"),
    path("payments/", v.payments, name="payments"),
    path("tariffs/", v.tariffs, name="tariffs"),
]
