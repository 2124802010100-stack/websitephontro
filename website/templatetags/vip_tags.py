from django import template
from django.utils import timezone
from django.utils.timesince import timesince
from website.models import VIPSubscription

register = template.Library()


@register.simple_tag
def vip_color(user) -> str:
    if not user or not getattr(user, 'id', None):
        return ''
    vip = VIPSubscription.objects.filter(user=user, expires_at__gte=timezone.now()).order_by('-expires_at').first()
    return vip.badge_color if vip else ''


@register.simple_tag
def vip_style_color(user) -> str:
    color = vip_color(user)
    if color == 'red':
        return '#ef4444'
    if color == 'blue':
        return '#3b82f6'
    if color == 'pink':
        return '#ec4899'
    return ''


@register.simple_tag
def vip_star_count(user) -> int:
    """Return number of stars to show for a user's active VIP plan.
    Falls back to VIPPackageConfig.stars when available; otherwise maps:
    vip1 -> 5, vip2 -> 4, vip3 -> 3. Non-VIP -> 0.
    """
    if not user or not getattr(user, 'id', None):
        return 0
    vip = VIPSubscription.objects.filter(user=user, expires_at__gte=timezone.now()).order_by('-expires_at').first()
    if not vip:
        return 0
    # Prefer reading configured stars from VIPPackageConfig via model property if present
    try:
        # Access via related config using the plan
        from website.models import VIPPackageConfig
        cfg = VIPPackageConfig.objects.filter(plan=vip.plan, is_active=True).first()
        if cfg and cfg.stars:
            return int(max(0, min(5, cfg.stars)))
    except Exception:
        pass
    # Fallback mapping
    mapping = {"vip1": 5, "vip2": 4, "vip3": 3}
    return mapping.get(vip.plan, 0)


@register.filter
def to_million(value):
    """Display price in million VND (price is already stored in million)"""
    try:
        price_value = float(value)
        if price_value == 0:
            return "Liên hệ"

        # Price is already in million, just format it
        if price_value == int(price_value):
            return f"{int(price_value)}"
        else:
            formatted = f"{price_value:.1f}"
            # Remove trailing zeros after decimal point
            if '.' in formatted:
                formatted = formatted.rstrip('0').rstrip('.')
            return formatted
    except (ValueError, TypeError):
        return "Liên hệ"


@register.filter
def timesince_vi(value):
    """Convert timesince to Vietnamese"""
    if not value:
        return ""

    try:
        time_str = timesince(value, timezone.now())

        # Replace English words with Vietnamese
        replacements = {
            'year': 'năm',
            'years': 'năm',
            'month': 'tháng',
            'months': 'tháng',
            'week': 'tuần',
            'weeks': 'tuần',
            'day': 'ngày',
            'days': 'ngày',
            'hour': 'giờ',
            'hours': 'giờ',
            'minute': 'phút',
            'minutes': 'phút',
            'second': 'giây',
            'seconds': 'giây',
        }

        for eng, vie in replacements.items():
            time_str = time_str.replace(eng, vie)

        return time_str
    except Exception:
        return ""



























