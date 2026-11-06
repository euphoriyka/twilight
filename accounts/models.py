"""Пользователь = таблица `users` из физической модели БД."""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Нужен email")
        email = self.normalize_email(email).lower()
        extra.setdefault("role", User.Role.CLIENT)
        user = self.model(email=email, **extra)
        user.set_password(password)  # в БД попадает только хэш
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra["role"] = User.Role.ADMIN
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Администратор"
        CLIENT = "client", "Клиент"

    user_id = models.AutoField(primary_key=True)
    full_name = models.CharField("ФИО", max_length=150)
    email = models.EmailField("Email", max_length=255, unique=True)
    # Колонка называется password_hash, как в спецификации; хранит хэш Django.
    password = models.CharField("Хэш пароля", max_length=255, db_column="password_hash")
    phone = models.CharField("Телефон", max_length=20)
    role = models.CharField("Роль", max_length=10, choices=Role.choices, default=Role.CLIENT)
    created_at = models.DateTimeField("Дата регистрации", default=timezone.now)

    last_login = None  # колонки нет в спецификации

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name", "phone"]

    class Meta:
        db_table = "users"
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    # --- права: всё решает поле role ---
    @property
    def is_active(self):
        return True

    @property
    def is_staff(self):
        return self.role == self.Role.ADMIN

    @property
    def is_superuser(self):
        return self.role == self.Role.ADMIN

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def member_number(self):
        return f"TW-{self.pk:04d}"

    def has_perm(self, perm, obj=None):
        return self.is_staff

    def has_module_perms(self, app_label):
        return self.is_staff
