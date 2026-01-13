from django import template

register = template.Library()

@register.filter
def to_million(value):
    """Convert price from VND to million VND"""
    try:
        price_in_million = float(value) / 1000000
        # Format with 1 decimal place, remove trailing .0
        if price_in_million == int(price_in_million):
            return f"{int(price_in_million)}"
        else:
            return f"{price_in_million:.1f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return value
