from django import template

register = template.Library()


@register.filter
def money(value):
    """1490 -> '1 490 ₽'"""
    try:
        n = round(float(value))
    except (TypeError, ValueError):
        return "—"
    return f"{n:,}".replace(",", "\u00a0") + "\u00a0₽"


@register.filter
def badge(status):
    """CSS-класс бейджа по статусу."""
    return {
        "available": "ok", "confirmed": "ok", "paid": "ok", "completed": "muted",
        "occupied": "warn", "pending": "warn",
        "maintenance": "bad", "cancelled": "bad", "failed": "bad", "refunded": "muted",
    }.get(status, "muted")
