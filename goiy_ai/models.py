"""
Models để tracking hành vi người dùng cho hệ thống gợi ý
"""
from django.db import models
from django.contrib.auth.models import User
from website.models import RentalPost, Province, District
from django.utils import timezone


class PostView(models.Model):
    """Theo dõi lượt xem chi tiết bài đăng"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='ai_post_views')
    post = models.ForeignKey(RentalPost, on_delete=models.CASCADE, related_name='ai_views')
    session_id = models.CharField(max_length=100, help_text="Session ID cho user chưa đăng nhập")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)
    duration = models.IntegerField(default=0, help_text="Thời gian xem (giây)")

    class Meta:
        ordering = ['-viewed_at']
        indexes = [
            models.Index(fields=['user', 'viewed_at']),
            models.Index(fields=['post', 'viewed_at']),
            models.Index(fields=['session_id', 'viewed_at']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else self.session_id[:8]
        return f"{user_str} xem {self.post.title[:30]} lúc {self.viewed_at.strftime('%d/%m %H:%M')}"


class SearchHistory(models.Model):
    """Lịch sử tìm kiếm của người dùng"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='ai_search_history')
    session_id = models.CharField(max_length=100, help_text="Session ID cho user chưa đăng nhập")

    # Các tiêu chí tìm kiếm
    query = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=50, blank=True)
    province = models.ForeignKey(Province, on_delete=models.SET_NULL, null=True, blank=True)
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True)
    min_price = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True)
    max_price = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True)
    min_area = models.FloatField(null=True, blank=True)
    max_area = models.FloatField(null=True, blank=True)
    features = models.JSONField(default=list, blank=True, help_text="Danh sách features được chọn")

    # Metadata bổ sung
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, help_text="Thông tin trình duyệt")
    search_type = models.CharField(max_length=50, blank=True, default='manual', help_text="manual/recommendation_tab/filter/etc")

    searched_at = models.DateTimeField(auto_now_add=True)
    results_count = models.IntegerField(default=0, help_text="Số kết quả tìm thấy")

    class Meta:
        ordering = ['-searched_at']
        verbose_name = "Lịch sử tìm kiếm"
        verbose_name_plural = "Lịch sử tìm kiếm"
        indexes = [
            models.Index(fields=['user', 'searched_at']),
            models.Index(fields=['session_id', 'searched_at']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else self.session_id[:8]
        return f"{user_str} tìm '{self.query}' lúc {self.searched_at.strftime('%d/%m %H:%M')}"


class UserInteraction(models.Model):
    """Lưu các tương tác của user với bài đăng (xem, lưu, liên hệ)"""
    INTERACTION_TYPES = [
        ('view', 'Xem chi tiết'),
        ('save', 'Lưu tin'),
        ('unsave', 'Bỏ lưu tin'),
        ('contact', 'Liên hệ'),
        ('request', 'Gửi yêu cầu thuê'),
        ('share', 'Chia sẻ'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='ai_interactions')
    post = models.ForeignKey(RentalPost, on_delete=models.CASCADE, related_name='ai_interactions')
    session_id = models.CharField(max_length=100, blank=True)
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    # Metadata bổ sung
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, help_text="Thông tin trình duyệt")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Tương tác người dùng"
        verbose_name_plural = "Tương tác người dùng"
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['post', 'created_at']),
            models.Index(fields=['session_id', 'created_at']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else self.session_id[:8]
        return f"{user_str} - {self.get_interaction_type_display()} - {self.post.title[:30]}"

    # Trọng số cho từng loại tương tác (dùng cho tính toán điểm)
    @property
    def weight(self):
        """Trọng số của tương tác này"""
        WEIGHT_MAP = {
            'view': 1.0,
            'save': 3.0,
            'unsave': -2.0,
            'contact': 5.0,
            'request': 8.0,
            'share': 4.0,
        }
        return WEIGHT_MAP.get(self.interaction_type, 1.0)


class RecommendationLog(models.Model):
    """Log các lần gợi ý để phân tích hiệu quả"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='recommendation_logs')
    session_id = models.CharField(max_length=100, blank=True)
    recommended_posts = models.JSONField(help_text="Danh sách ID các bài được gợi ý")
    algorithm_used = models.CharField(max_length=50, help_text="Thuật toán được dùng (content/collaborative/hybrid)")
    created_at = models.DateTimeField(auto_now_add=True)

    # Tracking hiệu quả
    clicked_posts = models.JSONField(default=list, help_text="Các bài user đã click từ gợi ý")
    conversion_rate = models.FloatField(default=0.0, help_text="Tỷ lệ click/impression")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Log gợi ý"
        verbose_name_plural = "Log gợi ý"

    def __str__(self):
        user_str = self.user.username if self.user else self.session_id[:8]
        return f"Gợi ý cho {user_str} lúc {self.created_at.strftime('%d/%m %H:%M')}"
