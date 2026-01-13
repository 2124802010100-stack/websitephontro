from django import template
from django.db.models import Avg, Count
from website.models import LandlordReview

register = template.Library()

@register.simple_tag
def landlord_rating_avg(user):
    """Return average rating (float with 1 decimal) for a landlord user."""
    if not user or not getattr(user, 'id', None):
        return 0
    avg = LandlordReview.objects.filter(landlord=user, is_approved=True).aggregate(a=Avg('rating'))['a'] or 0
    return round(float(avg), 1)

@register.simple_tag
def landlord_rating_count(user):
    if not user or not getattr(user, 'id', None):
        return 0
    return LandlordReview.objects.filter(landlord=user, is_approved=True).count()

@register.simple_tag
def latest_landlord_reviews(user, limit=3):
    """Return queryset of latest reviews for display."""
    try:
        limit = int(limit)
    except Exception:
        limit = 3
    return LandlordReview.objects.filter(landlord=user, is_approved=True).select_related('reviewer').order_by('-created_at')[:limit]
