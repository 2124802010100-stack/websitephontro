from django.contrib.auth.models import User
from django.utils import timezone

from .models import RentalPost, SiteVisit, Province, VIPSubscription, Notification
from django.db.models import Count, Q


def admin_dashboard_stats(request):
    """Cung cấp số liệu cho admin/index.html.

    Hàm này an toàn và rẻ: chỉ dùng aggregate đơn giản.
    """
    try:
        users_count = User.objects.count()
    except Exception:
        users_count = 0

    # Django không có khái niệm "đang đăng nhập" dễ dàng. Tạm thời = tổng session auth.
    # Đơn giản hóa: đếm người dùng có hoạt động gần 24h qua (cần last_login).
    try:
        last_day = timezone.now() - timezone.timedelta(days=1)
        logged_in_count = User.objects.filter(last_login__gte=last_day).count()
    except Exception:
        logged_in_count = 0

    try:
        posts_count = RentalPost.objects.count()
        posts_approved = RentalPost.objects.filter(is_approved=True).count()
    except Exception:
        posts_count = 0
        posts_approved = 0

    try:
        today = timezone.now().date()
        visits_today = SiteVisit.objects.filter(created_at__date=today).count()
        week_ago = timezone.now() - timezone.timedelta(days=7)
        visits_week = SiteVisit.objects.filter(created_at__gte=week_ago).count()
    except Exception:
        visits_today = 0
        visits_week = 0

    return {
        "users_count": users_count,
        "logged_in_count": logged_in_count,
        "posts_count": posts_count,
        "posts_approved": posts_approved,
        "visits_today": visits_today,
        "visits_week": visits_week,
    }



def footer_data(request):
    """Cung cấp dữ liệu footer dùng chung cho mọi trang.

    - categories: lấy từ RentalPost.CATEGORY_CHOICES
    - footer_provinces: một số tỉnh để render link nhanh trong footer
    """
    from django.core.cache import cache

    # Cache categories (không thay đổi thường xuyên)
    categories = cache.get('footer_categories')
    if categories is None:
        try:
            categories = list(RentalPost.CATEGORY_CHOICES)
            cache.set('footer_categories', categories, 3600)  # Cache 1 giờ
        except Exception:
            categories = []

    # Cache footer provinces (cập nhật mỗi 15 phút)
    footer_provinces = cache.get('footer_provinces')
    if footer_provinces is None:
        try:
            from django.utils import timezone
            now = timezone.now()
            footer_provinces = list(Province.objects.annotate(
                post_count=Count(
                    'rentalpost',
                    filter=Q(
                        rentalpost__is_approved=True,
                        rentalpost__is_rented=False,
                        rentalpost__is_deleted=False
                    ) & (
                        Q(rentalpost__expired_at__isnull=True) |
                        Q(rentalpost__expired_at__gt=now)
                    )
                )
            ).filter(post_count__gt=0).order_by('-post_count')[:10])
            cache.set('footer_provinces', footer_provinces, 900)  # Cache 15 phút
        except Exception:
            footer_provinces = []

    return {
        'footer_categories': categories,
        'footer_provinces': footer_provinces,
    }


def vip_status(request):
    """Cung cấp trạng thái VIP hoạt động cho người dùng hiện tại (nếu có)."""
    if not request.user.is_authenticated:
        return {}
    try:
        vip = VIPSubscription.objects.filter(user=request.user, expires_at__gte=timezone.now()).order_by('-expires_at').first()
        return {
            'vip_active': vip,
        }
    except Exception:
        return {}


def notifications_context(request):
    """Đưa số lượng thông báo chưa đọc và 5 thông báo mới nhất vào context chung.
    Nhẹ nhàng: chỉ chạy khi user đã đăng nhập.
    """
    if not request.user.is_authenticated:
        return {}
    try:
        # Auto-create owner notifications for expired posts (once per day per post)
        try:
            if hasattr(request.user, 'customerprofile') and request.user.customerprofile.is_owner():
                now = timezone.now()
                expired_posts = RentalPost.objects.filter(user=request.user, expired_at__isnull=False, expired_at__lte=now, is_deleted=False)[:10]
                for p in expired_posts:
                    from datetime import timedelta
                    if not Notification.objects.filter(user=request.user, type='post_expired', post=p, created_at__gte=now - timedelta(days=1)).exists():
                        try:
                            from django.urls import reverse
                            Notification.objects.create(
                                user=request.user,
                                type='post_expired',
                                title='Phòng đã hết hạn',
                                message=f"Tin '{p.title[:40]}' đã hết hạn. Gia hạn để tiếp tục hiển thị.",
                                url=reverse('select_posts_to_renew'),
                                post=p,
                            )
                        except Exception:
                            pass
        except Exception:
            pass

        # VIP expired reminder once per day
        try:
            vip_latest = VIPSubscription.objects.filter(user=request.user).order_by('-expires_at').first()
            if vip_latest and vip_latest.expires_at < timezone.now():
                from datetime import timedelta
                if not Notification.objects.filter(user=request.user, type='vip_expired', created_at__gte=timezone.now()-timedelta(days=1)).exists():
                    from django.urls import reverse
                    Notification.objects.create(
                        user=request.user,
                        type='vip_expired',
                        title='Gói VIP đã hết hạn',
                        message='Gia hạn để tiếp tục hưởng quyền lợi VIP.',
                        url=reverse('subscribe_vip')
                    )
        except Exception:
            pass

        unread = Notification.objects.filter(user=request.user, is_read=False).count()
        recent = list(Notification.objects.filter(user=request.user).order_by('-created_at')[:5])
        return {
            'notifications_unread_count': unread,
            'notifications_recent': recent,
        }
    except Exception:
        return {}

def unread_messages_context(request):
    """Đếm số tin nhắn chưa đọc cho user hiện tại"""
    if not request.user.is_authenticated:
        return {}
    try:
        from .models import ChatMessage
        unread_count = ChatMessage.objects.filter(
            thread__is_active=True,
            is_deleted=False,
            is_read=False
        ).exclude(sender=request.user).filter(
            Q(thread__owner=request.user) | Q(thread__guest=request.user)
        ).count()
        return {
            'unread_messages_count': unread_count,
        }
    except Exception:
        return {}

def ai_moderation_alerts(request):
    """Cung cấp cảnh báo AI moderation cho admin dashboard"""
    if not request.user.is_authenticated or not request.user.is_staff:
        return {}

    try:
        # Tin đã gắn cờ AI chưa duyệt
        flagged_posts = RentalPost.objects.filter(
            ai_flagged=True,
            is_approved=False
        ).order_by('-ai_confidence', '-created_at')[:5]

        # Thống kê AI
        ai_stats = {
            'total_flagged': RentalPost.objects.filter(ai_flagged=True, is_approved=False).count(),
            'high_confidence_flagged': RentalPost.objects.filter(
                ai_flagged=True,
                is_approved=False,
                ai_confidence__gte=0.8
            ).count(),
            'pending_review': RentalPost.objects.filter(is_approved=False).count(),
        }

        return {
            'ai_flagged_posts': flagged_posts,
            'ai_stats': ai_stats,
        }
    except Exception:
        return {
            'ai_flagged_posts': [],
            'ai_stats': {'total_flagged': 0, 'high_confidence_flagged': 0, 'pending_review': 0},
        }

