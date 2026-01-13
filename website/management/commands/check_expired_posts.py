"""
Management command để kiểm tra và gửi email thông báo cho chủ trọ khi bài đăng hết hạn.
Chạy định kỳ (ví dụ: mỗi giờ) bằng cron job hoặc scheduled task.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from website.models import RentalPost, Notification


class Command(BaseCommand):
    help = 'Kiểm tra bài đăng hết hạn và gửi email thông báo cho chủ trọ'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # Lấy tất cả bài đăng đã hết hạn
        expired_posts = RentalPost.objects.filter(
            expired_at__isnull=False,
            expired_at__lte=now,
            is_deleted=False
        ).select_related('user', 'user__customerprofile')
        
        sent_count = 0
        skipped_count = 0
        
        for post in expired_posts:
            try:
                owner = post.user
                
                # Kiểm tra xem chủ trọ có phải là owner không
                if not hasattr(owner, 'customerprofile') or not owner.customerprofile.is_owner():
                    continue
                
                # Kiểm tra email
                if not owner.email:
                    self.stdout.write(self.style.WARNING(f'⚠️ Chủ trọ {owner.username} không có email'))
                    continue
                
                # Kiểm tra xem đã gửi email cho bài này chưa (trong 24h qua)
                recent_notification = Notification.objects.filter(
                    user=owner,
                    type='post_expired',
                    post=post,
                    created_at__gte=now - timezone.timedelta(hours=24)
                ).exists()
                
                if recent_notification:
                    skipped_count += 1
                    continue  # Đã gửi email trong 24h qua
                
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

💡 Để tiếp tục hiển thị bài đăng, vui lòng gia hạn:
🔗 Gia hạn ngay: {settings.SITE_URL}{reverse('expired_posts')}

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
                
                # Tạo notification trong DB để tránh gửi lại
                Notification.objects.create(
                    user=owner,
                    type='post_expired',
                    title='Phòng hết hạn',
                    message=f"Bài đăng '{post.title}' đã hết hạn.",
                    url=reverse('expired_posts'),
                    post=post,
                )
                
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f'✅ Đã gửi email cho {owner.email} - Bài #{post.id}: {post.title[:50]}'))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Lỗi xử lý bài #{post.id}: {e}'))
        
        self.stdout.write(self.style.SUCCESS(
            f'\n📊 Tổng kết: Đã gửi {sent_count} email, bỏ qua {skipped_count} bài (đã gửi trong 24h)'
        ))

