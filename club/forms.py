from datetime import datetime, timedelta

from django import forms
from django.utils import timezone

from .models import Computer, GameSession, Payment, Tariff


class ComputerForm(forms.ModelForm):
    class Meta:
        model = Computer
        fields = ["computer_number", "computer_name", "category", "specifications", "status"]

    def clean_computer_number(self):
        n = self.cleaned_data["computer_number"]
        if n < 1:
            raise forms.ValidationError("Номер должен быть положительным.")
        return n


class TariffForm(forms.ModelForm):
    class Meta:
        model = Tariff
        fields = ["tariff_name", "category", "kind", "price_per_hour", "description", "is_active"]

    def clean_price_per_hour(self):
        p = self.cleaned_data["price_per_hour"]
        if p < 0:
            raise forms.ValidationError("Цена не может быть отрицательной.")
        return p


class PeriodForm(forms.Form):
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def period(self):
        today = timezone.localdate()
        if not self.is_valid():
            return today, today
        d_from = self.cleaned_data.get("date_from") or today
        d_to = self.cleaned_data.get("date_to") or d_from
        if d_to < d_from:
            d_from, d_to = d_to, d_from
        return d_from, d_to


class StartSessionForm(forms.Form):
    computer = forms.ModelChoiceField(Computer.objects.all(), label="Компьютер", required=False)
    booking_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    tariff = forms.ModelChoiceField(Tariff.objects.filter(is_active=True), label="Тариф")
    client_email = forms.EmailField(label="Email клиента", required=False)


class PaymentForm(forms.Form):
    session = forms.ModelChoiceField(GameSession.objects.filter(end_time__isnull=False), label="Сессия")
    payment_method = forms.ChoiceField(choices=Payment.Method.choices, label="Способ оплаты")


def parse_local_datetime(date_str, time_str):
    """'2026-11-02' + '19:30' -> aware datetime во времени клуба или None."""
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None
    return timezone.make_aware(naive, timezone.get_current_timezone())


def end_from_hours(start, hours):
    return start + timedelta(hours=int(hours))
