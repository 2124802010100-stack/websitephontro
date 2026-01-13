from django.db import models
from django.contrib.auth.models import User
# from django.contrib.gis.db import models as gis_models  # Tạm tắt vì chưa có GDAL
# from django.contrib.gis.geos import Point
# from django.contrib.gis.measure import D
from multiselectfield import MultiSelectField
from django.utils import timezone
from datetime import timedelta
import math

class RoomCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class Feature(models.Model):
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class Province(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name

class District(models.Model):
    province = models.ForeignKey(Province, related_name="districts", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    def __str__(self):
        return f"{self.name} - {self.province.name}"

class Ward(models.Model):
    district = models.ForeignKey(District, related_name="wards", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    def __str__(self):
        return f"{self.name} - {self.district.name}"

class PointOfInterest(models.Model):
    """Model cho các điểm quan tâm (POI) như trường học, bệnh viện, siêu thị, bến xe"""
    POI_TYPES = [
        ('school', 'Trường học'),
        ('hospital', 'Bệnh viện'),
        ('supermarket', 'Siêu thị'),
        ('bus_station', 'Bến xe'),
        ('train_station', 'Ga tàu'),
        ('metro_station', 'Trạm Metro'),
        ('market', 'Chợ'),
        ('park', 'Công viên'),
        ('mall', 'Trung tâm thương mại'),
        ('bank', 'Ngân hàng'),
        ('atm', 'ATM'),
        ('pharmacy', 'Nhà thuốc'),
        ('restaurant', 'Nhà hàng'),
        ('cafe', 'Quán cà phê'),
        ('gym', 'Phòng gym'),
        ('other', 'Khác'),
    ]

    name = models.CharField(max_length=255, help_text="Tên địa điểm")
    poi_type = models.CharField(max_length=50, choices=POI_TYPES, default='other')
    # Fallback: Sử dụng FloatField thay vì PointField khi chưa có GDAL
    latitude = models.FloatField(help_text="Vĩ độ", null=True, blank=True)
    longitude = models.FloatField(help_text="Kinh độ", null=True, blank=True)
    address = models.CharField(max_length=500, blank=True, null=True)
    province = models.ForeignKey(Province, on_delete=models.SET_NULL, null=True, blank=True)
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True)
    ward = models.ForeignKey(Ward, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Điểm quan tâm (POI)"
        verbose_name_plural = "Các điểm quan tâm (POI)"
        indexes = [
            models.Index(fields=['poi_type', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_poi_type_display()})"

    @property
    def location(self):
        """Tương thích với code sử dụng location.coords"""
        if self.latitude and self.longitude:
            return type('obj', (object,), {'coords': [self.longitude, self.latitude]})
        return None

class CustomerProfile(models.Model):
    ROLE_CHOICES = [
        ('customer', 'Khách hàng'),
        ('owner', 'Chủ trọ'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')
    display_name = models.CharField(max_length=100, blank=True, null=True, help_text="Tên hiển thị cho người dùng đăng nhập bằng Google")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username

    def is_owner(self):
        return self.role == 'owner'

    def is_customer(self):
        return self.role == 'customer'

    def get_total_violations(self):
        """Tổng số lần vi phạm của user (tổng violation_count từ các bài đăng)"""
        from django.db.models import Sum
        total = self.user.rental_posts.aggregate(total=Sum('violation_count'))['total']
        return total or 0

    def should_be_suspended(self):
        """Kiểm tra xem user có nên bị khóa tài khoản không (>= 5 lần vi phạm)"""
        return self.get_total_violations() >= 5

# Các đặc điểm nổi bật
FEATURE_CHOICES = [
    ('day_du_noi_that', 'Đầy đủ nội thất'),
    ('co_may_lanh', 'Có máy lạnh'),
    ('co_thang_may', 'Có thang máy'),
    ('bao_ve_24_24', 'Có bảo vệ 24/24'),
    ('co_gac', 'Có gác'),
    ('co_may_giat', 'Có máy giặt'),
    ('khong_chung_chu', 'Không chung chủ'),
    ('co_ham_de_xe', 'Có hầm để xe'),
    ('co_ke_bep', 'Có kệ bếp'),
    ('co_tu_lanh', 'Có tủ lạnh'),
    ('gio_giac_tu_do', 'Giờ giấc tự do'),
]

class RentalPost(models.Model):
    CATEGORY_CHOICES = [
        ('phongtro', 'Phòng trọ, nhà trọ'),
        ('nhanguyencan', 'Nhà thuê nguyên căn'),
        ('canho', 'Cho thuê căn hộ'),
        ('canho_mini', 'Cho thuê căn hộ mini'),
        ('canho_dichvu', 'Cho thuê căn hộ dịch vụ'),
        ('oghep', 'Tìm người ở ghép'),
        ('matbang', 'Cho thuê mặt bằng + Văn phòng'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rental_posts')
    title = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=0)
    area = models.FloatField()
    province = models.ForeignKey(Province, on_delete=models.SET_NULL, null=True, blank=True)
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True)
    ward = models.ForeignKey(Ward, on_delete=models.SET_NULL, null=True, blank=True)
    street = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    # Tạm thời không dùng PointField vì chưa có GDAL
    # location = gis_models.PointField(geography=True, null=True, blank=True, help_text="Tọa độ GPS (SRID 4326)")
    image = models.ImageField(upload_to='uploads/', null=True, blank=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True, help_text="Số điện thoại liên hệ")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='phongtro')
    # Danh mục và tiện ích có thể quản trị từ admin (mới)
    category_obj = models.ForeignKey('RoomCategory', null=True, blank=True, on_delete=models.SET_NULL, related_name='posts')
    features_obj = models.ManyToManyField('Feature', blank=True, related_name='posts')
    features = MultiSelectField(choices=FEATURE_CHOICES, blank=True, default=[])
    expired_at = models.DateTimeField(null=True, blank=True)
    # Thời điểm gần nhất bài được gia hạn (phục vụ giới hạn lượt/ngày)
    renewed_at = models.DateTimeField(null=True, blank=True)
    is_rented = models.BooleanField(default=False)
    # Duyệt tin
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_posts')

    # Từ chối tin
    is_rejected = models.BooleanField(default=False, help_text="Admin đã từ chối tin")
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='rejected_posts')
    rejection_reason = models.TextField(blank=True, help_text="Lý do từ chối tin")

    # Soft delete (để chủ tin thấy các bài đã bị xóa bởi admin)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='deleted_posts')

    # AI Content Moderation
    ai_flagged = models.BooleanField(default=False, help_text="AI đã gắn cờ nội dung đáng ngờ")
    ai_confidence = models.FloatField(null=True, blank=True, help_text="Độ tin cậy của AI (0-1)")
    ai_reason = models.TextField(blank=True, help_text="Lý do AI gắn cờ")
    ai_checked_at = models.DateTimeField(null=True, blank=True, help_text="Thời gian AI kiểm tra")
    ai_rule_score = models.FloatField(null=True, blank=True, help_text="Điểm từ rule-based check")
    ai_ml_prediction = models.IntegerField(null=True, blank=True, help_text="Kết quả ML prediction")
    ai_ml_confidence = models.FloatField(null=True, blank=True, help_text="Độ tin cậy ML")

    # Số lần bị báo cáo
    violation_count = models.IntegerField(default=0, help_text="Tổng số lần bị báo cáo")


    def __str__(self):
        return self.title

    def get_nearby_pois(self, radius_km=2, poi_types=None):
        """Lấy các POI gần đây trong bán kính radius_km (sử dụng Haversine formula)

        Args:
            radius_km: Bán kính tìm kiếm (km)
            poi_types: List các loại POI cần lọc (optional)

        Returns:
            List các POI với khoảng cách
        """
        if not self.latitude or not self.longitude:
            return []

        pois = PointOfInterest.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            is_active=True
        )

        if poi_types:
            pois = pois.filter(poi_type__in=poi_types)

        # Tính khoảng cách bằng Haversine formula
        result = []
        for poi in pois:
            distance = self._calculate_distance(
                self.latitude, self.longitude,
                poi.latitude, poi.longitude
            )
            if distance <= radius_km:
                poi.distance_km = distance
                result.append(poi)

        # Sort theo distance
        result.sort(key=lambda x: x.distance_km)
        return result

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Tính khoảng cách giữa 2 điểm bằng Haversine formula (km)"""
        R = 6371  # Bán kính Trái Đất (km)

        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))

        return R * c

    def get_active_reports_count(self):
        """Đếm số báo cáo đang active (pending, reviewing)"""
        return self.reports.filter(status__in=['pending', 'reviewing']).count()

    @property
    def features_list(self):
        """Trả về danh sách label tiếng Việt của features"""
        return [dict(FEATURE_CHOICES).get(f, f) for f in self.features] if self.features else []

class RentalPostImage(models.Model):
    post = models.ForeignKey(RentalPost, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='rental_images/')

class RentalVideo(models.Model):
    post = models.ForeignKey(RentalPost, on_delete=models.CASCADE, related_name='videos')
    video = models.FileField(upload_to='uploads/videos/')
class SavedPost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_posts')
    post = models.ForeignKey('RentalPost', on_delete=models.CASCADE, related_name='saved_by')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')
    def __str__(self):
        return f"{self.user.username} - {self.post.title}"

class ChatThread(models.Model):
    post = models.ForeignKey(RentalPost, on_delete=models.CASCADE, related_name='chat_threads',null=True, blank=True)
    guest = models.ForeignKey(User, on_delete=models.CASCADE, related_name='guest_chats')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owner_chats')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    # Ẩn cuộc trò chuyện riêng cho từng phía
    hidden_for_guest = models.BooleanField(default=False)
    hidden_for_owner = models.BooleanField(default=False)
    hidden_for_guest_at = models.DateTimeField(null=True, blank=True)
    hidden_for_owner_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('post', 'guest', 'owner')
        ordering = ['-updated_at']

    def __str__(self):
        return f"Chat: {self.guest.username} - {self.owner.username} ({self.post.title})"

class ChatMessage(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='chat_images/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}..."

class SiteVisit(models.Model):
    path = models.CharField(max_length=255)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['created_at'])]


class Article(models.Model):
    """Bài viết tin tức/hướng dẫn do admin đăng."""
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    excerpt = models.TextField(blank=True)
    content = models.TextField()
    banner = models.ImageField(upload_to='uploads/', null=True, blank=True)
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title


class SuggestedLink(models.Model):
    """Liên kết gợi ý "Có thể bạn quan tâm"."""
    title = models.CharField(max_length=200)
    url = models.URLField()
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class DeletionLog(models.Model):
    """Lưu dấu vết các lần xóa bài đăng để chủ tin xem lại."""
    post_title = models.CharField(max_length=255)
    post_id = models.IntegerField()
    # Người thực hiện xóa (admin hoặc chính chủ)
    deleted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='performed_deletions')
    # Chủ sở hữu bài bị xóa (để hiện cho đúng người)
    deleted_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='deletion_logs')
    deleted_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True, help_text="Chi tiết lý do xóa")

    class Meta:
        ordering = ['-deleted_at']

    def __str__(self):
        return f"Post#{self.post_id} - {self.post_title}"


class OTPCode(models.Model):
    """OTP dùng xác thực thao tác nhạy cảm (cập nhật thông tin, khôi phục)."""
    PURPOSE_CHOICES = (
        ("profile_update", "Cập nhật thông tin"),
        ("account_recovery", "Khôi phục tài khoản"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_codes")
    email = models.EmailField()
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose", "created_at"]) ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP {self.purpose} for {self.user.username}"

    @classmethod
    def create_for_user(cls, user: User, email: str, purpose: str, ttl_minutes: int = 10):
        expires = timezone.now() + timedelta(minutes=ttl_minutes)
        from random import randint
        code = f"{randint(100000, 999999)}"
        return cls.objects.create(user=user, email=email, code=code, purpose=purpose, expires_at=expires)

    def is_valid(self, code: str) -> bool:
        return (not self.is_used) and (self.code == code) and (self.expires_at >= timezone.now())


class Wallet(models.Model):
    """Ví tiền của người dùng"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=15, decimal_places=0, default=0, help_text="Số dư (VNĐ)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ví của {self.user.username}: {self.balance:,} VNĐ"

    def add_balance(self, amount):
        """Thêm tiền vào ví"""
        self.balance += amount
        self.save(update_fields=['balance', 'updated_at'])

    def subtract_balance(self, amount):
        """Trừ tiền từ ví"""
        if self.balance >= amount:
            self.balance -= amount
            self.save(update_fields=['balance', 'updated_at'])
            return True
        return False


class RechargeTransaction(models.Model):
    """Lịch sử giao dịch nạp tiền"""
    STATUS_CHOICES = [
        ('pending', 'Chờ xử lý'),
        ('completed', 'Thành công'),
        ('failed', 'Thất bại'),
        ('cancelled', 'Đã hủy'),
    ]

    PAYMENT_METHOD_CHOICES = [

        ('momo', 'Ví MoMo'),

        ('vnpay', 'VNPay'),
        ('cash', 'Tiền mặt'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recharge_transactions')
    amount = models.DecimalField(max_digits=15, decimal_places=0, help_text="Số tiền nạp (VNĐ)")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='bank_transfer')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=100, unique=True, help_text="Mã giao dịch")
    momo_order_id = models.CharField(max_length=128, blank=True, null=True, help_text="Order ID trả về từ MoMo sandbox/production")
    raw_response = models.JSONField(null=True, blank=True, help_text="Lưu payload trả về từ cổng thanh toán")
    description = models.TextField(blank=True, help_text="Ghi chú")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True, help_text="Ghi chú của admin")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Nạp tiền {self.amount:,} VNĐ - {self.user.username} ({self.status})"

    def complete_transaction(self):
        """Hoàn thành giao dịch và cộng tiền vào ví"""
        if self.status == 'pending':
            wallet, created = Wallet.objects.get_or_create(user=self.user)
            wallet.add_balance(self.amount)
            self.status = 'completed'
            self.completed_at = timezone.now()
            self.save(update_fields=['status', 'completed_at'])
            return True
        return False

    @classmethod
    def create_spending(cls, user: User, amount: int, description: str = ""):
        """Ghi nhận giao dịch chi tiêu (trừ tiền) vào lịch sử."""
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        return cls.objects.create(
            user=user,
            amount=-abs(int(amount)),
            payment_method='cash',
            status='completed',
            transaction_id=f"SPN_{timezone.now().strftime('%Y%m%d%H%M%S')}_{unique_id}",
            description=description,
            completed_at=timezone.now(),
        )

    @classmethod
    def create_income(cls, user: User, amount: int, description: str = "", payment_method: str = 'cash'):
        """Ghi nhận giao dịch thu (cộng tiền) vào lịch sử."""
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        return cls.objects.create(
            user=user,
            amount=abs(int(amount)),
            payment_method=payment_method,
            status='completed',
            transaction_id=f"INC_{timezone.now().strftime('%Y%m%d%H%M%S')}_{unique_id}",
            description=description,
            completed_at=timezone.now(),
        )


class RentalRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Chờ xác nhận'),
        ('accepted', 'Đã chấp nhận'),
        ('declined', 'Đã từ chối'),
        ('confirmed', 'Khách đã xác nhận thuê'),
        ('cancelled', 'Đã hủy'),
    ]
    DEPOSIT_STATUS_CHOICES = [
        ('none', 'Không yêu cầu'),
        ('requested', 'Đã yêu cầu đặt cọc'),
        ('paid', 'Đã đặt cọc'),
        ('cancelled', 'Khách hủy đặt cọc'),
        ('waived', 'Không cần đặt cọc'),
        ('pending_payment', 'Đang chờ thanh toán'),
        ('confirmed_by_owner', 'Chủ đã xác nhận'),
    ]
    CANCEL_REQUEST_STATUS = [
        ('none', 'Không có yêu cầu'),
        ('waiting', 'Chờ xác nhận hủy'),
        ('approved', 'Đã xác nhận hủy'),
        ('rejected', 'Từ chối hủy'),
    ]
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rental_requests')
    post = models.ForeignKey('RentalPost', on_delete=models.CASCADE, related_name='rental_requests')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    message = models.TextField(blank=True)
    owner_response = models.TextField(blank=True)
    cancel_reason = models.TextField(blank=True)
    cancel_request_status = models.CharField(max_length=16, choices=CANCEL_REQUEST_STATUS, default='none')
    # Đặt cọc
    deposit_status = models.CharField(max_length=20, choices=DEPOSIT_STATUS_CHOICES, default='none')
    deposit_amount = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True, help_text="Số tiền đặt cọc (VNĐ)")
    deposit_requested_at = models.DateTimeField(null=True, blank=True)
    deposit_paid_at = models.DateTimeField(null=True, blank=True)
    deposit_cancelled_at = models.DateTimeField(null=True, blank=True)
    deposit_payment_method = models.CharField(max_length=20, blank=True, choices=[
        ('wallet', 'Ví nội bộ'),
        ('momo', 'MoMo'),
    ])
    deposit_transaction_id = models.CharField(max_length=100, blank=True, help_text="Mã giao dịch từ cổng thanh toán")
    deposit_payment_url = models.URLField(max_length=500, blank=True, help_text="Link thanh toán MoMo QR")
    deposit_confirmed_by_owner = models.BooleanField(default=False)
    deposit_confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Yêu cầu thuê: {self.customer.username} - {self.post.title} ({self.status})"

    def is_pending(self):
        return self.status == 'pending'

    def is_accepted(self):
        return self.status == 'accepted'

    def is_declined(self):
        return self.status == 'declined'

    def is_confirmed(self):
        return self.status == 'confirmed'

    def is_cancelled(self):
        return self.status == 'cancelled'

    def can_customer_confirm(self):
        return self.status == 'accepted'

    def can_owner_decide(self):
        return self.status == 'pending'


class VIPSubscription(models.Model):
    PLAN_CHOICES = [
        ("vip1", "VIP 1"),
        ("vip2", "VIP 2"),
        ("vip3", "VIP 3"),
    ]

    COLOR_MAP = {
        "vip1": "red",   # tiêu đề đỏ
        "vip2": "blue",  # tiêu đề xanh
        "vip3": "pink",  # tiêu đề hồng
    }

    POSTS_PER_DAY = {
        "vip1": 5,
        "vip2": 3,
        "vip3": 1,
    }

    POST_EXPIRE_DAYS = {
        "vip1": 7,  # 1 tuần
        "vip2": 3,
        "vip3": 2,
    }

    PRICES = {
        "vip1": 500_000,
        "vip2": 300_000,
        "vip3": 150_000,
    }

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vip_subscriptions")
    plan = models.CharField(max_length=8, choices=PLAN_CHOICES)
    registered_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Thời điểm hết hạn VIP")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-registered_at"]

    def __str__(self):
        return f"{self.user.username} - {self.get_plan_display()} (đến {self.expires_at:%d/%m/%Y})"

    @property
    def badge_color(self) -> str:
        # Lấy từ VIPPackageConfig trong database
        try:
            config = VIPPackageConfig.objects.get(plan=self.plan, is_active=True)
            return config.title_color
        except VIPPackageConfig.DoesNotExist:
            return self.COLOR_MAP.get(self.plan, "")

    @property
    def posts_per_day(self) -> int:
        # Lấy từ VIPPackageConfig trong database
        try:
            config = VIPPackageConfig.objects.get(plan=self.plan, is_active=True)
            return config.posts_per_day
        except VIPPackageConfig.DoesNotExist:
            return self.POSTS_PER_DAY.get(self.plan, 0)

    @property
    def post_expire_days(self) -> int:
        # Lấy từ VIPPackageConfig trong database
        try:
            config = VIPPackageConfig.objects.get(plan=self.plan, is_active=True)
            return config.expire_days
        except VIPPackageConfig.DoesNotExist:
            return self.POST_EXPIRE_DAYS.get(self.plan, 0)

    @property
    def price(self) -> int:
        # Lấy từ VIPPackageConfig trong database
        try:
            config = VIPPackageConfig.objects.get(plan=self.plan, is_active=True)
            return int(config.price)
        except VIPPackageConfig.DoesNotExist:
            return self.PRICES.get(self.plan, 0)

    @property
    def is_active(self) -> bool:
        return self.expires_at >= timezone.now()

    @classmethod
    def create_or_renew(cls, user: User, plan: str, duration_days: int = 30):
        now = timezone.now()
        expires = now + timedelta(days=duration_days)
        return cls.objects.create(user=user, plan=plan, expires_at=expires)


class PostReport(models.Model):
    """Báo cáo vi phạm bài đăng từ người dùng"""
    REASON_CHOICES = [
        ('fraud', 'Tin có dấu hiệu lừa đảo'),
        ('duplicate', 'Tin trung lặp nội dung'),
        ('inappropriate', 'Không liên hệ được chủ tin đăng'),
        ('wrong_info', 'Thông tin không đúng thực tế (giá, diện tích, hình ảnh...)'),
        ('other', 'Lý do khác'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Chờ xử lý'),
        ('reviewing', 'Đang xem xét'),
        ('resolved', 'Đã xử lý'),
        ('rejected', 'Từ chối'),
    ]

    post = models.ForeignKey(RentalPost, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Người báo cáo")
    reporter_name = models.CharField(max_length=100, verbose_name="Họ tên người báo cáo")
    reporter_phone = models.CharField(max_length=15, verbose_name="Số điện thoại")
    reason = models.CharField(max_length=50, choices=REASON_CHOICES, verbose_name="Lý do báo cáo")
    description = models.TextField(blank=True, verbose_name="Mô tả thêm")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian báo cáo")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Trạng thái")
    admin_note = models.TextField(blank=True, verbose_name="Ghi chú admin")

    # Tính năng cảnh báo và xử lý
    warning_sent = models.BooleanField(default=False, verbose_name="Đã gửi cảnh báo")
    warning_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm gửi cảnh báo")
    deadline_fix = models.DateTimeField(null=True, blank=True, verbose_name="Deadline sửa (24h)")
    auto_removed = models.BooleanField(default=False, verbose_name="Đã tự động gỡ")
    removed_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm gỡ bài")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Báo cáo vi phạm"
        verbose_name_plural = "Báo cáo vi phạm"

    def __str__(self):
        return f"Báo cáo #{self.id} - {self.post.title[:50]}"

    def send_warning_email(self):
        """Gửi email cảnh báo đến chủ bài đăng"""
        from django.core.mail import send_mail
        from django.conf import settings
        from django.utils import timezone
        from datetime import timedelta

        if self.warning_sent:
            return False, "Đã gửi cảnh báo rồi"

        owner = self.post.user
        owner_email = owner.email

        if not owner_email:
            return False, "Chủ nhà không có email"

        subject = f"⚠️ CẢNH BÁO VI PHẠM - Bài đăng: {self.post.title}"
        message = f"""Kính gửi {owner.username},

Bài đăng "{self.post.title}" của bạn đã bị báo cáo vi phạm bởi người dùng.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 THÔNG TIN BÁO CÁO:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Lý do: {self.get_reason_display()}
• Mô tả chi tiết: {self.description}
• Thời gian báo cáo: {self.created_at.strftime('%d/%m/%Y %H:%M')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ YÊU CẦU XỬ LÝ:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bạn có 24 giờ để xác nhận và xử lý vấn đề này bằng cách:
1. Chỉnh sửa lại nội dung bài đăng cho phù hợp
2. Hoặc gỡ bài đăng nếu thông tin không còn chính xác

⏰ Deadline: {(timezone.now() + timedelta(hours=24)).strftime('%d/%m/%Y %H:%M')}

Nếu sau 24 giờ bạn không xử lý, chúng tôi sẽ tự động gỡ bài đăng này khỏi trang website.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ LƯU Ý QUAN TRỌNG:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Việc vi phạm quy định nhiều lần có thể dẫn đến khóa tài khoản
• Vui lòng tuân thủ quy định đăng tin của chúng tôi
• Liên hệ admin nếu có thắc mắc

Trân trọng,
Đội ngũ Quản trị PhongTro.NMA
"""

        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [owner_email], fail_silently=False)
            self.warning_sent = True
            self.warning_sent_at = timezone.now()
            self.deadline_fix = timezone.now() + timedelta(hours=24)
            self.save(update_fields=['warning_sent', 'warning_sent_at', 'deadline_fix'])
            return True, "Đã gửi email cảnh báo"
        except Exception as e:
            return False, f"Lỗi gửi email: {str(e)}"


class DepositBill(models.Model):
    """Hóa đơn đặt cọc"""
    rental_request = models.OneToOneField(RentalRequest, on_delete=models.CASCADE, related_name='deposit_bill')
    bill_number = models.CharField(max_length=50, unique=True, help_text="Số hóa đơn")
    amount = models.DecimalField(max_digits=15, decimal_places=0, help_text="Số tiền đặt cọc (VNĐ)")
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='deposit_bills_as_customer')
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='deposit_bills_as_owner')
    post_title = models.CharField(max_length=255, help_text="Tên phòng")
    payment_method = models.CharField(max_length=20, help_text="Phương thức thanh toán")
    transaction_id = models.CharField(max_length=100, help_text="Mã giao dịch")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Ngày tạo bill")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Hóa đơn đặt cọc"
        verbose_name_plural = "Hóa đơn đặt cọc"

    def __str__(self):
        return f"Bill #{self.bill_number} - {self.amount:,} VNĐ"


class VIPPackageConfig(models.Model):
    """Model để admin có thể chỉnh sửa thông tin các gói VIP"""
    PLAN_CHOICES = [
        ("vip1", "VIP 1"),
        ("vip2", "VIP 2"),
        ("vip3", "VIP 3"),
    ]

    COLOR_CHOICES = [
        ("red", "Màu đỏ"),
        ("blue", "Màu xanh"),
        ("pink", "Màu hồng"),
    ]

    plan = models.CharField(max_length=8, choices=PLAN_CHOICES, unique=True, verbose_name="Gói VIP")
    name = models.CharField(max_length=50, verbose_name="Tên gói", default="Gói VIP")
    posts_per_day = models.IntegerField(verbose_name="Số tin đăng mỗi ngày", default=1)
    expire_days = models.IntegerField(verbose_name="Thời gian hết hạn (ngày)", default=1)
    title_color = models.CharField(max_length=10, choices=COLOR_CHOICES, verbose_name="Màu tiêu đề", default="red")
    price = models.DecimalField(max_digits=10, decimal_places=0, verbose_name="Giá gói (VNĐ)", default=0)
    stars = models.IntegerField(verbose_name="Số sao hiển thị", default=1, help_text="Số sao từ 1-5")
    is_active = models.BooleanField(default=True, verbose_name="Kích hoạt")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Cập nhật lần cuối")

    class Meta:
        ordering = ['plan']
        verbose_name = "Cấu hình gói VIP"
        verbose_name_plural = "Cấu hình gói VIP"

    def __str__(self):
        return f"{self.get_plan_display()} - {self.price:,.0f}₫"

    def get_expire_text(self):
        """Trả về text thời gian hết hạn"""
        if self.expire_days >= 7:
            weeks = self.expire_days // 7
            return f"{weeks} tuần" if weeks == 1 else f"{weeks} tuần"
        return f"{self.expire_days} ngày"


class LandlordReview(models.Model):
    """Đánh giá chủ trọ bởi khách hàng sau khi xác nhận thuê.
    Mỗi yêu cầu thuê (RentalRequest) chỉ được đánh giá một lần.
    """
    rental_request = models.OneToOneField(
        RentalRequest,
        on_delete=models.CASCADE,
        related_name='landlord_review'
    )
    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_landlord_reviews')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='written_landlord_reviews')
    rating = models.PositiveSmallIntegerField(default=5)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_approved = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['landlord', 'created_at'])]

    def __str__(self):
        return f"{self.reviewer.username} → {self.landlord.username}: {self.rating}★"

    @staticmethod
    def get_summary_for(landlord: User):
        from django.db.models import Avg, Count
        qs = LandlordReview.objects.filter(landlord=landlord, is_approved=True)
        summary = qs.aggregate(avg=Avg('rating'), total=Count('id'))
        avg = round(summary['avg'] or 0, 1)
        total = summary['total'] or 0
        return avg, total


class Notification(models.Model):
    """Thông báo hệ thống cho người dùng.
    Dùng đơn giản: lưu URL đích để khi click sẽ chuyển đến và đánh dấu đã đọc.
    """
    TYPE_CHOICES = [
        # Chủ trọ
        ("post_expired", "Phòng hết hạn"),
        ("chat_new", "Tin nhắn mới"),
        ("deposit_paid", "Khách đã đặt cọc"),
        ("rental_request_new", "Yêu cầu thuê mới"),
        ("review_received", "Khách đã đánh giá bạn"),
        ("vip_expired", "Gói VIP hết hạn"),
        ("vip_payment_success", "Thanh toán VIP thành công"),
        ("wallet_topup_success", "Nạp tiền ví thành công"),
        ("rental_cancel_requested", "Khách yêu cầu hủy phòng"),
        ("violation_warning", "Cảnh báo vi phạm bài đăng"),
        ("post_removed_violation", "Bài đăng bị gỡ do vi phạm"),
        # Khách hàng
        ("deposit_success", "Đặt cọc thành công"),
        ("deposit_confirmed", "Chủ trọ xác nhận đặt cọc"),
        ("rental_confirmed", "Xác nhận thuê phòng"),
        ("chat_reply", "Chủ trọ phản hồi tin nhắn"),
        ("rental_request_status", "Yêu cầu thuê được xử lý"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    url = models.CharField(max_length=512, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Liên kết tùy chọn tới các đối tượng hay dùng
    post = models.ForeignKey('RentalPost', null=True, blank=True, on_delete=models.SET_NULL)
    rental_request = models.ForeignKey('RentalRequest', null=True, blank=True, on_delete=models.SET_NULL)
    transaction = models.ForeignKey('RechargeTransaction', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', 'created_at']),
            models.Index(fields=['type', 'created_at'])
        ]

    def __str__(self):
        return f"[{self.user.username}] {self.title}"

