from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User


class RegisterForm(forms.Form):
    """Роль в форме НЕТ: клиент не может назначить себе admin."""
    full_name = forms.CharField(label="ФИО", max_length=150)
    email = forms.EmailField(label="Email", max_length=255)
    phone = forms.CharField(label="Телефон", max_length=20)
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Повтор пароля", widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Этот email уже зарегистрирован.")
        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        digits = [c for c in phone if c.isdigit()]
        if not 10 <= len(digits) <= 15 or any(not (c.isdigit() or c in "+-() ") for c in phone):
            raise forms.ValidationError("Введите корректный номер телефона.")
        return phone

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Пароли не совпадают.")
        elif p1:
            try:
                password_validation.validate_password(p1)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return data

    def save(self):
        d = self.cleaned_data
        return User.objects.create_user(
            email=d["email"], password=d["password1"],
            full_name=d["full_name"].strip(), phone=d["phone"],
        )


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Неверный email или пароль.",
    }

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
