"""
Middleware để kiểm tra và gửi email thông báo bài đăng hết hạn
"""
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.core.cache import cache
from website.models import RentalPost, Notification
import logging

logger = logging.getLogger(__name__)


class ExpiredPostNotificationMiddleware:
    """
    Middleware kiểm tra bài đăng hết hạn và gửi email thông báo.
    Chạy mỗi 30 phút một lần (dùng cache để tránh chạy quá nhiều).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Kiểm tra xem đã chạy trong 30 phút gần đây chưa
        cache_key = 'expired_posts_check_last_run'
        last_run = cache.get(cache_key)

        if not last_run:
            # Chạy kiểm tra
            self.check_and_notify_expired_posts()
            # Set cache 30 phút
            cache.set(cache_key, timezone.now(), 30 * 60)

        response = self.get_response(request)
        return response

    def check_and_notify_expired_posts(self):
        """Kiểm tra và gửi thông báo cho bài đăng hết hạn"""
        try:
            now = timezone.now()

            # Lấy bài đăng hết hạn trong 1 giờ qua (chưa xử lý)
            expired_posts = RentalPost.objects.filter(
                expired_at__isnull=False,
                expired_at__lte=now,
                expired_at__gte=now - timezone.timedelta(hours=1),
                is_deleted=False
            ).select_related('user', 'user__customerprofile')

            for post in expired_posts:
                try:
                    owner = post.user

                    # Kiểm tra owner
                    if not hasattr(owner, 'customerprofile') or not owner.customerprofile.is_owner():
                        continue

                    # Kiểm tra email
                    if not owner.email:
                        continue

                    # Kiểm tra đã gửi thông báo chưa
                    already_notified = Notification.objects.filter(
                        user=owner,
                        type='post_expired',
                        post=post,
                        created_at__gte=now - timezone.timedelta(hours=24)
                    ).exists()

                    if already_notified:
                        continue

                    # Gửi email
                    subject = f"⏰ Bài đăng đã hết hạn - {post.title[:50]}"
                    message = f"""
Xin chào {owner.username},

Bài đăng của bạn đã hết hạn:

📋 Thông tin bài đăng:
- Tiêu đề: {post.title}
- Địa chỉ: {post.address or 'Chưa cập nhật'}
- Giá: {int(post.price):,} VNĐ/tháng
- Diện tích: {post.area} m²
- Hết hạn: {post.expired_at.strftime('%d/%m/%Y %H:%M')}

💡 Để tiếp tục hiển thị bài đăng, vui lòng gia hạn ngay:
🔗 {settings.SITE_URL}{reverse('expired_posts')}

---
Trân trọng,
Hệ thống PhongTro NMA
"""

                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [owner.email],
                        fail_silently=True,
                    )

                    # Tạo notification
                    Notification.objects.create(
                        user=owner,
                        type='post_expired',
                        title='Phòng hết hạn',
                        message=f"Bài đăng '{post.title}' đã hết hạn.",
                        url=reverse('expired_posts'),
                        post=post,
                    )

                    logger.info(f'Đã gửi email hết hạn cho user {owner.username} - Bài #{post.id}')

                except Exception as e:
                    logger.error(f'Lỗi gửi email hết hạn cho bài #{post.id}: {e}')

        except Exception as e:
            logger.error(f'Lỗi kiểm tra bài hết hạn: {e}')
