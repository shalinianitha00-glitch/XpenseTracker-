from django import template

register = template.Library()


@register.filter
def currency(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    sign = "-" if number < 0 else ""
    return f"{sign}₹{abs(number):,.2f}"


@register.filter
def abs_currency(value):
    try:
        return f"₹{abs(float(value)):,.2f}"
    except (TypeError, ValueError):
        return value
