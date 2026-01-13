from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import RentalPost, ChatThread, ChatMessage, CustomerProfile, SiteVisit, Article, SuggestedLink, DeletionLog, PostReport, VIPPackageConfig, DepositBill, Notification, PointOfInterest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.utils import timezone as dj_tz
from django.template.response import TemplateResponse
from django.urls import path
from django.contrib.admin.views.decorators import staff_member_required


@admin.register(RentalPost)
class RentalPostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "price", "area", "is_rented", "is_approved", "ai_flagged", "ai_confidence", "created_at")
    list_display_links = ("id", "title")
    list_filter = ("category", "province", "district", "is_rented", "is_approved", "ai_flagged", "created_at")
    search_fields = ("title", "description", "user__username", "ai_reason")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 30
    actions = ("approve_posts", "unapprove_posts", "mark_rented", "mark_vacant", "retrain_ai_model",)

    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('user', 'title', 'description', 'price', 'area', 'category')
        }),
        ('Địa chỉ', {
            'fields': ('province', 'district', 'ward', 'street', 'address', 'latitude', 'longitude')
        }),
        ('Hình ảnh & Video', {
            'fields': ('image',)
        }),
        ('Trạng thái', {
            'fields': ('is_rented', 'is_approved', 'approved_at', 'approved_by')
        }),
        ('AI Content Moderation', {
            'fields': ('ai_flagged', 'ai_confidence', 'ai_reason', 'ai_checked_at', 'ai_rule_score', 'ai_ml_prediction', 'ai_ml_confidence'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('ai_checked_at', 'ai_rule_score', 'ai_ml_prediction', 'ai_ml_confidence')

    def approve_posts(self, request, queryset):
        from .ai_moderation.content_moderator import ContentModerator
        moderator = ContentModerator()

        # Chỉ học từ bài mà AI đã gắn cờ trước đó
        for post in queryset:
            if post.ai_flagged:  # Chỉ học nếu AI từng nghi ngờ bài này
                moderator.learn_from_decision(post.title, post.description, is_approved=True)

        updated = queryset.update(is_approved=True, approved_at=timezone.now(), approved_by=request.user)
        self.message_user(request, f"Đã duyệt {updated} tin và cập nhật AI")
    approve_posts.short_description = "Duyệt các tin đã chọn"

    def unapprove_posts(self, request, queryset):
        from .ai_moderation.content_moderator import ContentModerator
        moderator = ContentModerator()

        # Chỉ học từ bài mà AI đã gắn cờ (tránh học từ bài bị từ chối vì lý do khác)
        for post in queryset:
            if post.ai_flagged:  # Chỉ học nếu AI đã phát hiện vấn đề
                moderator.learn_from_decision(post.title, post.description, is_approved=False)

        updated = queryset.update(is_approved=False, approved_at=None, approved_by=None)
        self.message_user(request, f"Đã bỏ duyệt {updated} tin và cập nhật AI")
    unapprove_posts.short_description = "Bỏ duyệt các tin đã chọn"

    def mark_rented(self, request, queryset):
        updated = queryset.update(is_rented=True)
        self.message_user(request, f"Đã đánh dấu đã cho thuê {updated} tin")
    mark_rented.short_description = "Đánh dấu đã cho thuê"

    def mark_vacant(self, request, queryset):
        updated = queryset.update(is_rented=False)
        self.message_user(request, f"Đã mở lại {updated} tin")
    mark_vacant.short_description = "Mở lại (còn trống)"

    def retrain_ai_model(self, request, queryset):
        """Retrain AI model với dữ liệu mới"""
        try:
            from .ai_moderation.content_moderator import ContentModerator
            moderator = ContentModerator()
            accuracy = moderator.train_model()
            self.message_user(request, f"Đã retrain AI model với accuracy: {accuracy:.2f}")
        except Exception as e:
            self.message_user(request, f"Lỗi retrain model: {str(e)}", level='ERROR')
    retrain_ai_model.short_description = "Retrain AI Model"

    # Ghi log khi admin xóa một bài (từ trang chi tiết)
    def delete_model(self, request, obj):
        try:
            DeletionLog.objects.create(
                post_title=obj.title,
                post_id=obj.id,
                deleted_by=request.user,
                deleted_user=obj.user,
                reason='admin_delete'
            )
        except Exception:
            pass
        super().delete_model(request, obj)

    # Ghi log khi admin xóa nhiều bài (action Delete selected)
    def delete_queryset(self, request, queryset):
        try:
            logs = []
            for post in queryset:
                logs.append(DeletionLog(
                    post_title=post.title,
                    post_id=post.id,
                    deleted_by=request.user,
                    deleted_user=post.user,
                    reason='admin_delete'
                ))
            DeletionLog.objects.bulk_create(logs)
        except Exception:
            pass
        super().delete_queryset(request, queryset)


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    fields = ("created_at", "sender", "short_content", "is_read", "is_deleted")
    readonly_fields = ("created_at", "sender", "short_content")
    extra = 0

    def short_content(self, obj):
        text = obj.content or ""
        return (text[:60] + "...") if len(text) > 60 else text
    short_content.short_description = "Nội dung"


@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "owner", "guest", "is_active", "hidden_for_owner", "hidden_for_guest", "updated_at")
    list_display_links = ("id", "post")
    list_filter = ("is_active", "updated_at")
    search_fields = ("post__title", "owner__username", "guest__username")
    date_hierarchy = "updated_at"
    ordering = ("-updated_at",)
    list_per_page = 30
    autocomplete_fields = ("post", "owner", "guest")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("post", "owner", "guest", "is_active")}),
        ("Thời gian", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    inlines = [ChatMessageInline]

    actions = ("activate_threads", "deactivate_threads",)

    def activate_threads(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Đã kích hoạt {updated} cuộc trò chuyện")
    activate_threads.short_description = "Kích hoạt thread đã chọn"

    def deactivate_threads(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Đã tắt {updated} cuộc trò chuyện")
    deactivate_threads.short_description = "Tắt thread đã chọn"


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "thread_link", "sender", "short_content", "is_read", "is_deleted", "created_at")
    list_display_links = ("id", "thread_link")
    list_filter = ("is_read", "is_deleted", "created_at")
    search_fields = ("content", "sender__username", "thread__post__title")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    autocomplete_fields = ("thread", "sender")
    readonly_fields = ("created_at",)
    actions = ("soft_delete_messages", "restore_messages",)

    def thread_link(self, obj):
        return format_html("#{id} - {title}", id=obj.thread_id, title=obj.thread.post.title)
    thread_link.short_description = "Thread"

    def short_content(self, obj):
        text = obj.content or ""
        return (text[:80] + "...") if len(text) > 80 else text
    short_content.short_description = "Nội dung"

    def soft_delete_messages(self, request, queryset):
        updated = queryset.update(is_deleted=True, deleted_at=timezone.now())
        self.message_user(request, f"Đã thu hồi {updated} tin nhắn")
    soft_delete_messages.short_description = "Thu hồi tin nhắn (đặt is_deleted)"

    def restore_messages(self, request, queryset):
        updated = queryset.update(is_deleted=False, deleted_at=None)
        self.message_user(request, f"Đã khôi phục {updated} tin nhắn")
    restore_messages.short_description = "Khôi phục tin nhắn"


# Thêm một số model hữu ích khác
@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "phone", "role", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("user__username", "phone")

## Hidden: Province/District/Ward from admin as requested


# Tuỳ biến giao diện admin
admin.site.site_header = "Quản trị Phòng Trọ"
admin.site.site_title = "Quản trị Phòng Trọ"
admin.site.index_title = "Bảng điều khiển"

# Dashboard stats provider
def _stats_context():
    # Localized 'today' for Vietnam timezone, to avoid UTC date mismatches
    today = dj_tz.localtime(dj_tz.now()).date()
    # Revenue chart data (last 30 days)
    from django.db.models.functions import TruncDate
    from django.db.models import Sum
    from datetime import timedelta
    chart_days = 30
    chart_start = today - timedelta(days=chart_days-1)
    from .models import RechargeTransaction
    # Chỉ tính doanh thu từ VIP (amount < 0)
    chart_qs = RechargeTransaction.objects.filter(status='completed', created_at__date__gte=chart_start, amount__lt=0)
    chart_data = chart_qs.annotate(day=TruncDate('created_at')).values('day').order_by('day').annotate(total=Sum('amount'))
    chart_labels = []
    chart_values = []
    day_iter = chart_start
    chart_map = {d['day']: abs(d['total']) for d in chart_data}  # Chuyển thành số dương
    for i in range(chart_days):
        chart_labels.append(day_iter.strftime('%d/%m'))
        chart_values.append(int(chart_map.get(day_iter, 0) or 0))
        day_iter += timedelta(days=1)
    users_count = User.objects.count()
    sessions = Session.objects.filter(expire_date__gt=dj_tz.now())

    # Đếm chỉ users có session và còn tồn tại trong database
    user_ids_in_sessions = set()
    for s in sessions:
        try:
            user_id = s.get_decoded().get('_auth_user_id')
            if user_id:
                user_ids_in_sessions.add(int(user_id))
        except:
            pass

    # Lọc chỉ users còn tồn tại
    logged_in_count = User.objects.filter(id__in=user_ids_in_sessions).count()

    posts_count = RentalPost.objects.count()
    posts_approved = RentalPost.objects.filter(is_approved=True).count()
    now = dj_tz.now()
    # Revenue stats - chỉ tính doanh thu từ VIP (amount < 0 là chi tiêu cho VIP)
    revenue_day = RechargeTransaction.objects.filter(status='completed', created_at__date=today, amount__lt=0).aggregate(total=Sum('amount'))['total'] or 0
    revenue_day = abs(revenue_day)  # Chuyển thành số dương
    week_start = today - timezone.timedelta(days=today.weekday())
    revenue_week = RechargeTransaction.objects.filter(status='completed', created_at__date__gte=week_start, amount__lt=0).aggregate(total=Sum('amount'))['total'] or 0
    revenue_week = abs(revenue_week)
    month_start = today.replace(day=1)
    revenue_month = RechargeTransaction.objects.filter(status='completed', created_at__date__gte=month_start, amount__lt=0).aggregate(total=Sum('amount'))['total'] or 0
    revenue_month = abs(revenue_month)
    year_start = today.replace(month=1, day=1)
    revenue_year = RechargeTransaction.objects.filter(status='completed', created_at__date__gte=year_start, amount__lt=0).aggregate(total=Sum('amount'))['total'] or 0
    revenue_year = abs(revenue_year)
    # New approved posts today/this week (count by approved_at, not created_at)
    from datetime import datetime, time
    start_of_day = dj_tz.make_aware(datetime.combine(today, time.min))
    end_of_day = dj_tz.make_aware(datetime.combine(today, time.max))
    week_start_date = today - timezone.timedelta(days=today.weekday())
    start_of_week = dj_tz.make_aware(datetime.combine(week_start_date, time.min))

    posts_today = RentalPost.objects.filter(
        is_approved=True,
        approved_at__gte=start_of_day,
        approved_at__lte=end_of_day,
    ).count()

    posts_week = RentalPost.objects.filter(
        is_approved=True,
        approved_at__gte=start_of_week,
        approved_at__lte=end_of_day,
    ).count()

    # Pending posts - CHỈ HIỂN THỊ BÀI AI ĐÃ FLAG (để admin review)
    # Vì bài bình thường đã tự động duyệt rồi
    pending_posts = RentalPost.objects.filter(
        is_approved=False,
        ai_flagged=True  # Chỉ lấy bài AI đã cảnh báo
    ).order_by('-created_at')[:10]

    # Pie chart: Phân bố bài đăng theo khu vực (TP.HCM, Hà Nội, Đà Nẵng, Khác)
    from .models import Province
    region_map = {
        'TP.HCM': ['Hồ Chí Minh', 'TP.HCM', 'TP HCM', 'Thành phố Hồ Chí Minh'],
        'Hà Nội': ['Hà Nội', 'Ha Noi', 'TP Hà Nội', 'Thành phố Hà Nội'],
        'Đà Nẵng': ['Đà Nẵng', 'Da Nang', 'TP Đà Nẵng', 'Thành phố Đà Nẵng'],
    }
    region_counts = {'TP.HCM': 0, 'Hà Nội': 0, 'Đà Nẵng': 0, 'Khác': 0}
    for post in RentalPost.objects.filter(is_deleted=False):
        province_name = post.province.name if post.province else ''
        found = False
        for region, aliases in region_map.items():
            if province_name and any(alias.lower() in province_name.lower() for alias in aliases):
                region_counts[region] += 1
                found = True
                break
        if not found:
            region_counts['Khác'] += 1

    # Pie chart: Tỷ lệ loại tin đăng (Tin thường, VIP1, VIP2, VIP3)
    type_counts = {'VIP1': 0, 'VIP2': 0, 'VIP3': 0}
    from .models import VIPSubscription
    for post in RentalPost.objects.filter(is_deleted=False):
        vip = VIPSubscription.objects.filter(user=post.user, expires_at__gte=post.created_at).order_by('-expires_at').first()
        if vip:
            if vip.plan == 'vip1':
                type_counts['VIP1'] += 1
            elif vip.plan == 'vip2':
                type_counts['VIP2'] += 1
            elif vip.plan == 'vip3':
                type_counts['VIP3'] += 1
    # Only VIP posts are counted; no 'Tin thường'

    # Recent recharges (nạp tiền) and top rechargers
    recent_recharges = RechargeTransaction.objects.filter(status='completed', amount__gt=0).select_related('user').order_by('-created_at')[:10]
    from django.db.models import Sum
    top_rechargers = (
        RechargeTransaction.objects.filter(status='completed', amount__gt=0)
        .values('user__id', 'user__username')
        .annotate(total=Sum('amount'))
        .order_by('-total')[:10]
    )

    # Report statistics
    from .models import PostReport
    pending_reports_count = PostReport.objects.filter(status='pending').count()
    total_reports_count = PostReport.objects.count()

    # Tin đang hoạt động (approved, chưa hết hạn, chưa cho thuê)
    active_posts = RentalPost.objects.filter(
        is_approved=True,
        is_deleted=False,
        is_rented=False,
        expired_at__isnull=False,
        expired_at__gt=now
    ).select_related('user', 'province').order_by('-created_at')

    # Tin đã hết hạn
    expired_posts = RentalPost.objects.filter(
        is_approved=True,
        is_deleted=False,
        expired_at__isnull=False,
        expired_at__lte=now
    ).select_related('user', 'province').order_by('-expired_at')

    # Tin bị admin gỡ
    deleted_posts = RentalPost.objects.filter(
        is_deleted=True
    ).select_related('user', 'province', 'deleted_by').order_by('-deleted_at')

    return {
        'users_count': users_count,
        'logged_in_count': logged_in_count,
        'posts_count': posts_count,
        'posts_approved': posts_approved,
        'revenue_day': revenue_day,
        'revenue_week': revenue_week,
        'revenue_month': revenue_month,
        'revenue_year': revenue_year,
        'posts_today': posts_today,
        'posts_week': posts_week,
        'pending_posts': pending_posts,
        'pending_reports_count': pending_reports_count,
        'total_reports_count': total_reports_count,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'region_labels': list(region_counts.keys()),
        'region_values': list(region_counts.values()),
        'type_labels': [k for k in type_counts.keys()],
        'type_values': [v for v in type_counts.values()],
        'recent_recharges': recent_recharges,
        'top_rechargers': list(top_rechargers),
        'today_start': start_of_day,
        'today_end': end_of_day,
        'week_start': start_of_week,
        'active_posts': active_posts,
        'expired_posts': expired_posts,
        'deleted_posts': deleted_posts,
    }

def custom_admin_index(request):
    context = admin.site.each_context(request)
    context.update(_stats_context())

    # Thêm AI moderation alerts
    if request.user.is_authenticated and request.user.is_staff:
        try:
            from .context_processors import ai_moderation_alerts
            ai_context = ai_moderation_alerts(request)
            context.update(ai_context)
        except Exception:
            pass

    return TemplateResponse(request, 'admin/custom_index.html', context)

@staff_member_required
def logged_in_users_view(request):
    """Trang liệt kê người dùng đang đăng nhập và cho phép hủy phiên (logout)."""
    from datetime import timedelta

    # Lấy sessions chưa hết hạn
    sessions = Session.objects.filter(expire_date__gt=dj_tz.now())

    # Lọc sessions hoạt động trong 1 giờ gần nhất (có thể điều chỉnh)
    recent_threshold = dj_tz.now() - timedelta(hours=1)

    user_id_to_sessions = {}
    for s in sessions:
        try:
            data = s.get_decoded()
        except Exception:
            continue
        user_id = data.get('_auth_user_id')
        if user_id:
            # Chỉ tính sessions có last_login gần đây hoặc tất cả sessions nếu không có thông tin
            # Ở đây ta chấp nhận tất cả sessions chưa hết hạn
            user_id_str = str(user_id)
            user_id_to_sessions.setdefault(user_id_str, []).append(s)

    # Lấy users theo ID (chuyển keys về int để query)
    user_ids = [int(uid) for uid in user_id_to_sessions.keys()]
    users = User.objects.filter(id__in=user_ids).order_by('username')

    # Đếm chỉ sessions của users còn tồn tại
    valid_session_count = 0
    user_rows = []
    for u in users:
        user_id_str = str(u.id)
        sessions_for_user = user_id_to_sessions.get(user_id_str, [])
        valid_session_count += len(sessions_for_user)
        user_rows.append({
            'user': u,
            'session_count': len(sessions_for_user),
            'sessions': sessions_for_user,
            'last_login': u.last_login,
        })

    context = admin.site.each_context(request)
    context.update({
        'user_rows': user_rows,
        'total_sessions': valid_session_count,  # Chỉ đếm sessions hợp lệ
    })
    return TemplateResponse(request, 'admin/logged_in_users.html', context)

@staff_member_required
def revoke_session(request, session_key):
    """Xóa session theo key để buộc người dùng đăng xuất."""
    if request.method == 'POST':
        Session.objects.filter(session_key=session_key).delete()
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect('/admin/logged-in-users/')
    from django.http import HttpResponseRedirect
    return HttpResponseRedirect('/admin/')
def get_urls_with_dashboard(get_urls_func):
    def wrapper():
        urls = get_urls_func()
        extra = [
            path('', custom_admin_index),
            path('logged-in-users/', logged_in_users_view, name='logged_in_users'),
            path('revoke-session/<str:session_key>/', revoke_session, name='revoke_session'),
        ]
        return extra + urls
    return wrapper

admin.site.get_urls = get_urls_with_dashboard(admin.site.get_urls)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "is_published", "published_at")
    list_filter = ("is_published", "published_at")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "excerpt", "content")


@admin.register(SuggestedLink)
class SuggestedLinkAdmin(admin.ModelAdmin):
    list_display = ("title", "url", "is_active", "order")
    list_editable = ("is_active", "order")
    search_fields = ("title", "url")



# =========================
# Quản lý Ví & Giao dịch nạp tiền
# =========================
from django.contrib import messages
from .models import Wallet, RechargeTransaction, VIPSubscription


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)


# ===== VIP Subscription admin =====
@admin.register(VIPSubscription)
class VIPSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "registered_at", "expires_at")
    list_filter = ("plan", "registered_at", "expires_at")
    search_fields = ("user__username", "user__email")
    ordering = ("-registered_at",)
@admin.register(RechargeTransaction)
class RechargeTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_id',
        'user',
        'amount',
        'payment_method',
        'status_colored',
        'created_at',
        'completed_at',
    )
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('transaction_id', 'user__username')
    readonly_fields = ('transaction_id', 'created_at')

    # Hiển thị trạng thái có màu
    def status_colored(self, obj):
        colors = {
            'pending': 'orange',
            'completed': 'green',
            'failed': 'red',
            'canceled': 'gray',
        }
        return format_html(
            '<span style="color: {};">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_colored.short_description = 'Trạng thái'

    # Actions
    actions = ['approve_transactions', 'reject_transactions']

    def approve_transactions(self, request, queryset):
        """Duyệt nạp tiền: cộng tiền vào ví và chuyển completed"""
        approved = 0
        for tx in queryset.filter(status='pending'):
            wallet, _ = Wallet.objects.get_or_create(user=tx.user)
            wallet.balance += tx.amount
            wallet.save()

            tx.status = 'completed'
            from django.utils.timezone import now
            tx.completed_at = now()
            tx.save()

            approved += 1
        self.message_user(request, f"Đã duyệt {approved} giao dịch và cộng tiền vào ví.", messages.SUCCESS)

    approve_transactions.short_description = "✅ Duyệt và cộng tiền vào ví"

    def reject_transactions(self, request, queryset):
        """Từ chối giao dịch"""
        rejected = queryset.filter(status='pending').update(status='failed')
        self.message_user(request, f"Đã từ chối {rejected} giao dịch.", messages.WARNING)

    reject_transactions.short_description = "❌ Từ chối giao dịch"


@admin.register(PostReport)
class PostReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'post_link', 'reporter_name', 'reporter_phone', 'reason_display', 'status_colored', 'warning_status', 'owner_update_after_warning', 'deadline_display', 'created_at')
    list_display_links = ('id', 'post_link')
    list_filter = ('status', 'reason', 'warning_sent', 'auto_removed', 'created_at')
    search_fields = ('reporter_name', 'reporter_phone', 'post__title', 'description')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_per_page = 30
    readonly_fields = ('created_at', 'warning_sent_at', 'deadline_fix', 'removed_at')

    fieldsets = (
        ('Thông tin báo cáo', {
            'fields': ('post', 'reason', 'description', 'created_at')
        }),
        ('Người báo cáo', {
            'fields': ('reporter_name', 'reporter_phone')
        }),
        ('Xử lý', {
            'fields': ('status', 'admin_note')
        }),
        ('Cảnh báo & Xử lý tự động', {
            'fields': ('warning_sent', 'warning_sent_at', 'deadline_fix', 'auto_removed', 'removed_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['mark_reviewing', 'mark_resolved', 'mark_rejected', 'send_warning_to_owner', 'remove_violating_posts']

    def post_link(self, obj):
        return format_html(
            '<a href="/post/{id}/" target="_blank">{title}</a>',
            id=obj.post.id,
            title=obj.post.title[:60],
        )
    post_link.short_description = 'Bài đăng'

    def reason_display(self, obj):
        return obj.get_reason_display()
    reason_display.short_description = 'Lý do'

    def status_colored(self, obj):
        colors = {
            'pending': 'orange',
            'reviewing': 'blue',
            'resolved': 'green',
            'rejected': 'red',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    status_colored.short_description = 'Trạng thái'

    def warning_status(self, obj):
        if obj.auto_removed:
            return format_html('<span style="color:#dc2626;font-weight:700;">✅ Đã tự động gỡ</span>')
        elif obj.warning_sent:
            return format_html('<span style="color:#f59e0b;font-weight:700;">⚠️ Đã cảnh báo</span>')
        else:
            return format_html('<span style="color:#6b7280;">Chưa cảnh báo</span>')
    warning_status.short_description = 'Cảnh báo'

    def owner_update_after_warning(self, obj):
        """Hiển thị xem chủ nhà đã cập nhật bài sau khi nhận cảnh báo chưa."""
        try:
            if obj.warning_sent and obj.warning_sent_at:
                post_updated = getattr(obj.post, 'updated_at', None)
                if post_updated and post_updated > obj.warning_sent_at:
                    return format_html('<span style="color:#16a34a;font-weight:700;">Đã cập nhật sau cảnh báo</span>')
                return format_html('<span style="color:#6b7280;">Chưa cập nhật</span>')
        except Exception:
            pass
        return '-'
    owner_update_after_warning.short_description = 'Chủ đã cập nhật?'

    def deadline_display(self, obj):
        if obj.deadline_fix:
            from django.utils import timezone
            now = timezone.now()
            if now > obj.deadline_fix:
                return format_html('<span style="color:#dc2626;">Quá hạn</span>')
            else:
                delta = obj.deadline_fix - now
                hours = int(delta.total_seconds() // 3600)
                return format_html('<span style="color:#16a34a;">Còn {}h</span>', hours)
        return '-'
    deadline_display.short_description = 'Deadline'

    def mark_reviewing(self, request, queryset):
        updated = queryset.update(status='reviewing')
        self.message_user(request, f"Đã đánh dấu {updated} báo cáo đang xem xét.")
    mark_reviewing.short_description = "🔍 Đánh dấu đang xem xét"

    def mark_resolved(self, request, queryset):
        updated = queryset.update(status='resolved')
        self.message_user(request, f"Đã đánh dấu {updated} báo cáo đã xử lý.")
    mark_resolved.short_description = "✅ Đánh dấu đã xử lý"

    def mark_rejected(self, request, queryset):
        updated = queryset.update(status='rejected')
        self.message_user(request, f"Đã đánh dấu {updated} báo cáo bị từ chối.")
    mark_rejected.short_description = "❌ Đánh dấu từ chối"

    def send_warning_to_owner(self, request, queryset):
        """Gửi email cảnh báo đến chủ bài đăng"""
        from django.urls import reverse
        success_count = 0
        fail_count = 0

        for report in queryset:
            success, msg = report.send_warning_email()
            if success:
                success_count += 1
                # Tăng violation_count của bài đăng
                report.post.violation_count += 1
                report.post.save(update_fields=['violation_count'])

                # Tạo thông báo trên website
                try:
                    Notification.objects.create(
                        user=report.post.user,
                        type='violation_warning',
                        title=f"⚠️ Cảnh báo vi phạm: {report.post.title[:50]}",
                        message=f"Bài đăng của bạn đã bị báo cáo vi phạm: {report.get_reason_display()}. Bạn có 24 giờ để xử lý.",
                        url=f"/sua-phong/{report.post.id}/",
                        post=report.post
                    )
                except Exception:
                    pass
            else:
                fail_count += 1

        if success_count > 0:
            self.message_user(request, f"✅ Đã gửi cảnh báo đến {success_count} chủ nhà (Email + Thông báo web).", level='success')
        if fail_count > 0:
            self.message_user(request, f"⚠️ {fail_count} báo cáo không gửi được email.", level='warning')
    send_warning_to_owner.short_description = "📧 Gửi email cảnh báo chủ nhà"

    def remove_violating_posts(self, request, queryset):
        """Xóa trực tiếp các bài đăng vi phạm"""
        from django.utils import timezone
        from django.core.mail import send_mail
        from django.conf import settings
        from django.urls import reverse

        removed_count = 0
        fail_count = 0

        for report in queryset:
            try:
                post = report.post
                owner = post.user

                # Đánh dấu bài đăng đã bị admin gỡ (soft delete + bỏ duyệt)
                post.is_approved = False
                post.is_deleted = True
                post.deleted_at = timezone.now()
                post.deleted_by = request.user
                post.save(update_fields=['is_approved', 'is_deleted', 'deleted_at', 'deleted_by'])

                # Ghi log xóa
                DeletionLog.objects.create(
                    post_title=post.title,
                    post_id=post.id,
                    deleted_by=request.user,
                    deleted_user=post.user,
                    reason='violation_report',
                    details=f"Bài đăng bị xóa do vi phạm: {report.get_reason_display()}. Báo cáo #{report.id}"
                )

                # Cập nhật báo cáo
                report.auto_removed = True
                report.removed_at = timezone.now()
                report.status = 'resolved'
                report.save(update_fields=['auto_removed', 'removed_at', 'status'])

                # Tăng violation_count
                post.violation_count += 1
                post.save(update_fields=['violation_count'])

                # Gửi email thông báo xóa bài
                if owner.email:
                    try:
                        subject = f"🚨 BÀI ĐĂNG ĐÃ BỊ GỠ - {post.title}"
                        message = f"""Kính gửi {owner.username},

Bài đăng "{post.title}" của bạn đã bị gỡ khỏi website do vi phạm quy định.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 THÔNG TIN VI PHẠM:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Lý do: {report.get_reason_display()}
• Mô tả: {report.description}
• Thời gian xử lý: {timezone.now().strftime('%d/%m/%Y %H:%M')}
• Người xử lý: Admin

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ LƯU Ý:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Bài đăng đã bị gỡ vĩnh viễn
• Tổng số lần vi phạm: {post.violation_count} lần
• Vi phạm nhiều lần có thể dẫn đến khóa tài khoản
• Vui lòng tuân thủ quy định khi đăng tin mới

Trân trọng,
Đội ngũ Quản trị PhongTro.NMA
"""
                        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [owner.email], fail_silently=True)
                    except Exception:
                        pass

                # Tạo thông báo trên website
                try:
                    removed_url = f"{reverse('manage_rooms')}?status=removed"
                    Notification.objects.create(
                        user=owner,
                        type='post_removed_violation',
                        title=f"🚨 Bài đăng đã bị gỡ: {post.title[:50]}",
                        message=f"Bài đăng của bạn đã bị gỡ do vi phạm: {report.get_reason_display()}. Tổng vi phạm: {post.violation_count} lần. Click để xem bài đã bị xóa.",
                        url=removed_url,
                        post=post
                    )
                except Exception:
                    pass

                removed_count += 1
            except Exception as e:
                fail_count += 1
                self.message_user(request, f"Lỗi xóa bài #{report.id}: {str(e)}", level='error')

        if removed_count > 0:
            self.message_user(request, f"✅ Đã xóa {removed_count} bài đăng vi phạm (Email + Thông báo web).", level='success')
        if fail_count > 0:
            self.message_user(request, f"⚠️ {fail_count} báo cáo xóa thất bại.", level='warning')
    remove_violating_posts.short_description = "🗑️ Xóa bài đăng vi phạm"


@admin.register(VIPPackageConfig)
class VIPPackageConfigAdmin(admin.ModelAdmin):
    list_display = ('plan', 'price', 'posts_per_day', 'expire_days', 'title_color', 'stars', 'is_active')
    list_editable = ('price', 'posts_per_day', 'expire_days', 'title_color', 'stars', 'is_active')
    list_filter = ('is_active', 'plan', 'title_color')
    search_fields = ('name', 'plan')
    ordering = ('plan',)
    readonly_fields = ('updated_at',)

    fieldsets = (
        ('Thông tin gói VIP', {
            'fields': ('plan', 'name', 'is_active')
        }),
        ('Tính năng', {
            'fields': ('posts_per_day', 'expire_days', 'title_color', 'stars')
        }),
        ('Giá cả', {
            'fields': ('price',)
        }),
        ('Thời gian', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )

    def price_formatted(self, obj):
        price_str = '{:,.0f}'.format(float(obj.price))
        return format_html('<strong style="color: #ff5722;">{} ₫</strong>', price_str)
    price_formatted.short_description = 'Giá'

    def expire_text(self, obj):
        return obj.get_expire_text()
    expire_text.short_description = 'Thời hạn'


@admin.register(DepositBill)
class DepositBillAdmin(admin.ModelAdmin):
    list_display = ('bill_number', 'customer_link', 'owner_link', 'amount_formatted', 'payment_method', 'created_at')
    list_filter = ('payment_method', 'created_at')
    search_fields = ('bill_number', 'transaction_id', 'customer__username', 'owner__username', 'post_title')
    readonly_fields = ('rental_request', 'bill_number', 'amount', 'customer', 'owner', 'post_title', 'payment_method', 'transaction_id', 'created_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    fieldsets = (
        ('Thông tin Bill', {
            'fields': ('bill_number', 'created_at')
        }),
        ('Người liên quan', {
            'fields': ('customer', 'owner', 'post_title')
        }),
        ('Thanh toán', {
            'fields': ('amount', 'payment_method', 'transaction_id')
        }),
        ('Yêu cầu thuê', {
            'fields': ('rental_request',)
        }),
    )

    def customer_link(self, obj):
        return format_html('<a href="/admin/auth/user/{}/change/">{}</a>', obj.customer.id, obj.customer.username)
    customer_link.short_description = 'Khách hàng'

    def owner_link(self, obj):
        return format_html('<a href="/admin/auth/user/{}/change/">{}</a>', obj.owner.id, obj.owner.username)
    owner_link.short_description = 'Chủ trọ'

    def amount_formatted(self, obj):
        amount_str = '{:,}'.format(int(obj.amount))
        return format_html('<strong style="color:#10b981">{} VNĐ</strong>', amount_str)
    amount_formatted.short_description = 'Số tiền'

    def has_add_permission(self, request):
        return False  # Không cho phép tạo bill thủ công

    def has_delete_permission(self, request, obj=None):
        # Cho phép xóa qua cascade/SET_NULL khi xóa User
        # Chỉ chặn xóa trực tiếp từ DepositBill admin
        return request.user.is_superuser


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "type", "title", "is_read", "created_at")
    list_filter = ("type", "is_read", "created_at")
    search_fields = ("title", "message", "user__username")


@admin.register(PointOfInterest)
class PointOfInterestAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "poi_type", "province", "district", "is_active", "created_at")
    list_display_links = ("id", "name")
    list_filter = ("poi_type", "province", "district", "is_active", "created_at")
    search_fields = ("name", "address", "description")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 30

    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('name', 'poi_type', 'description')
        }),
        ('Vị trí', {
            'fields': ('location', 'address', 'province', 'district', 'ward'),
            'description': 'Nhập tọa độ dưới dạng POINT(longitude latitude), ví dụ: POINT(105.8542 21.0285)'
        }),
        ('Liên hệ', {
            'fields': ('phone', 'website')
        }),
        ('Trạng thái', {
            'fields': ('is_active',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def get_readonly_fields(self, request, obj=None):
        """Thêm created_at và updated_at vào readonly khi edit"""
        if obj:
            return self.readonly_fields + ('created_at', 'updated_at')
        return self.readonly_fields
