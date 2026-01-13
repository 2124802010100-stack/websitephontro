from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User

from .models import (
    RentalPost,
    ChatMessage,
    VIPSubscription,
    RechargeTransaction,
    VIPPackageConfig,
    RentalRequest,
    CustomerProfile,
    RentalPostImage,
    RentalVideo,
)
from .notifications import notify
from django.urls import reverse
from .ai_moderation.content_moderator import ContentModerator

@receiver(post_save, sender=RentalPost)
def check_content_on_save(sender, instance, created, **kwargs):
    """Kiểm tra nội dung tự động khi tạo tin mới"""
    if created and not instance.is_approved:
        try:
            # Khởi tạo AI moderator
            moderator = ContentModerator()

            # Kiểm tra nội dung
            result = moderator.check_content(instance.title, instance.description)

            # Cập nhật thông tin AI
            instance.ai_flagged = result['is_flagged']
            instance.ai_confidence = result['confidence']
            instance.ai_reason = result['reason']
            instance.ai_checked_at = timezone.now()
            instance.ai_rule_score = result['rule_result']['rule_score']
            instance.ai_ml_prediction = result['ml_result']['prediction']
            instance.ai_ml_confidence = result['ml_result']['confidence']

            # LOGIC MỚI: Tự động duyệt nếu AI không cảnh báo
            if result['is_flagged']:
                # AI phát hiện vấn đề → Giữ lại chờ admin duyệt thủ công
                RentalPost.objects.filter(pk=instance.pk).update(
                    ai_flagged=True,
                    ai_confidence=instance.ai_confidence,
                    ai_reason=instance.ai_reason,
                    ai_checked_at=instance.ai_checked_at,
                    ai_rule_score=instance.ai_rule_score,
                    ai_ml_prediction=instance.ai_ml_prediction,
                    ai_ml_confidence=instance.ai_ml_confidence,
                    is_approved=False,  # Vẫn chưa duyệt, chờ admin
                )

                # Gửi thông báo cho admin
                if result['confidence'] > 0.6:
                    send_admin_alert(instance, result)
            else:
                # AI không phát hiện vấn đề → TỰ ĐỘNG DUYỆT
                RentalPost.objects.filter(pk=instance.pk).update(
                    ai_flagged=False,
                    ai_confidence=instance.ai_confidence,
                    ai_reason=instance.ai_reason,
                    ai_checked_at=instance.ai_checked_at,
                    ai_rule_score=instance.ai_rule_score,
                    ai_ml_prediction=instance.ai_ml_prediction,
                    ai_ml_confidence=instance.ai_ml_confidence,
                    is_approved=True,  # ✅ Tự động duyệt luôn
                    approved_at=timezone.now(),
                    # approved_by để None vì do AI duyệt tự động
                )

        except Exception as e:
            print(f"Error in AI content check: {e}")
            # Log error nhưng không làm crash app
            pass

def send_admin_alert(post, ai_result):
    """Gửi thông báo cho admin khi có tin đáng ngờ"""
    try:
        # Lấy danh sách admin
        admin_users = User.objects.filter(is_staff=True, is_active=True)

        if admin_users.exists():
            subject = f"🚨 Tin đăng đáng ngờ cần kiểm tra - #{post.id}"
            message = f"""
Tin đăng mới cần kiểm tra:

ID: {post.id}
Tiêu đề: {post.title}
Người đăng: {post.user.username}
Thời gian: {post.created_at}

Kết quả AI:
- Đã gắn cờ: {'Có' if ai_result['is_flagged'] else 'Không'}
- Độ tin cậy: {ai_result['confidence']:.2f}
- Lý do: {ai_result['reason']}

Chi tiết:
- Từ nhạy cảm: {ai_result['rule_result']['sensitive_count']}
- Từ cần xem xét: {ai_result['rule_result']['context_count']}
- Điểm rule: {ai_result['rule_result']['rule_score']:.2f}
- ML prediction: {ai_result['ml_result']['prediction']}
- ML confidence: {ai_result['ml_result']['confidence']:.2f}

Link admin: {settings.SITE_URL}/admin/website/rentalpost/{post.id}/change/
            """

            # Gửi email cho tất cả admin
            admin_emails = [user.email for user in admin_users if user.email]
            if admin_emails:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    admin_emails,
                    fail_silently=True,
                )

    except Exception as e:
        print(f"Error sending admin alert: {e}")
# ===== Bump post.updated_at when media changes =====
@receiver([post_save, post_delete], sender=RentalPostImage)
def bump_updated_on_image_change(sender, instance, **kwargs):
    try:
        RentalPost.objects.filter(pk=instance.post_id).update(updated_at=timezone.now())
    except Exception:
        pass

@receiver([post_save, post_delete], sender=RentalVideo)
def bump_updated_on_video_change(sender, instance, **kwargs):
    try:
        RentalPost.objects.filter(pk=instance.post_id).update(updated_at=timezone.now())
    except Exception:
        pass


# ===== Notifications via signals =====
@receiver(post_save, sender=ChatMessage)
def notify_new_chat_message(sender, instance: ChatMessage, created, **kwargs):
    if not created or instance.is_deleted:
        return
    try:
        thread = instance.thread
        # Determine recipient: the other side in the thread
        recipient = thread.owner if instance.sender != thread.owner else thread.guest
        if recipient and recipient != instance.sender:
            notify(
                user=recipient,
                type_='chat_new',
                title='Tin nhắn mới',
                message=(instance.content or '')[:120],
                url=reverse('chat_thread', args=[thread.id])
            )
    except Exception:
        pass


@receiver(post_save, sender=VIPSubscription)
def notify_vip_subscription(sender, instance: VIPSubscription, created, **kwargs):
    try:
        if created:
            notify(
                user=instance.user,
                type_='vip_payment_success',
                title='Thanh toán VIP thành công',
                message=f'Bạn đã đăng ký {instance.get_plan_display()} đến {instance.expires_at:%d/%m/%Y}.',
                url=reverse('manage_rooms') if hasattr(instance.user, 'customerprofile') and instance.user.customerprofile.is_owner() else reverse('home')
            )
    except Exception:
        pass


@receiver(post_save, sender=RechargeTransaction)
def notify_wallet_topup(sender, instance: RechargeTransaction, created, **kwargs):
    """Chỉ thông báo nạp ví cho CHỦ TRỌ khi nạp trực tiếp, không phải luồng đặt cọc."""
    try:
        # Chỉ khi giao dịch hoàn tất và số tiền dương
        if not (instance.status == 'completed' and instance.amount and instance.amount > 0):
            return
        # Bỏ qua các mô tả liên quan đến đặt cọc
        desc = (instance.description or '').lower()
        if 'đặt cọc' in desc or 'dat coc' in desc or 'deposit' in desc:
            return
        # Chỉ thông báo cho chủ trọ (không thông báo phía khách hàng)
        profile = getattr(instance.user, 'customerprofile', None)
        if not profile or not profile.is_owner():
            return
        notify(
            user=instance.user,
            type_='wallet_topup_success',
            title='Nạp tiền vào ví thành công',
            message=f'Bạn đã nạp {int(instance.amount):,} VNĐ vào ví.',
            url=reverse('wallet')
        )
    except Exception:
        pass


# ===== Email notifications for landlords =====
@receiver(post_save, sender=RentalRequest)
def notify_owner_new_rental_request(sender, instance: RentalRequest, created, **kwargs):
    """Gửi email cho chủ trọ khi có người yêu cầu thuê trọ"""
    if not created or instance.status != 'pending':
        return

    try:
        owner = instance.post.user
        if not owner or not owner.email:
            return

        # Kiểm tra xem chủ trọ có phải là owner không
        if hasattr(owner, 'customerprofile') and not owner.customerprofile.is_owner():
            return

        customer = instance.customer
        post = instance.post

        subject = f"📧 Có người yêu cầu thuê phòng - {post.title[:50]}"
        message = f"""
Xin chào {owner.username},

Bạn có một yêu cầu thuê phòng mới:

📋 Thông tin yêu cầu:
- Khách hàng: {customer.username}
- Phòng: {post.title}
- Địa chỉ: {post.address or 'Chưa cập nhật'}
- Giá: {int(post.price):,} VNĐ/tháng
- Diện tích: {post.area} m²

💬 Lời nhắn từ khách:
{instance.message if instance.message else 'Không có lời nhắn'}

⏰ Thời gian: {instance.created_at.strftime('%d/%m/%Y %H:%M')}

🔗 Xem chi tiết và phản hồi: {settings.SITE_URL}{reverse('manage_rooms')}

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
        print(f"✅ Đã gửi email thông báo yêu cầu thuê cho chủ trọ: {owner.email}")

    except Exception as e:
        print(f"❌ Lỗi gửi email thông báo yêu cầu thuê: {e}")


# Lưu ý: Email thông báo bài đăng hết hạn được xử lý bởi management command
# `python manage.py check_expired_posts` - chạy định kỳ (ví dụ: mỗi giờ)
# Signal không phù hợp vì chỉ chạy khi post được save, không phát hiện được bài đã hết hạn


# ===== Auto-create CustomerProfile for social login users =====
from allauth.account.signals import user_signed_up
from allauth.socialaccount.signals import pre_social_login, socialaccount_signup
from django.dispatch import receiver

@receiver(user_signed_up)
def create_customer_profile_for_social_user(sender, request, user, **kwargs):
    """Tự động tạo CustomerProfile khi user đăng ký bằng Google lần đầu"""
    try:
        # Kiểm tra xem user đã có profile chưa
        if not hasattr(user, 'customerprofile'):
            CustomerProfile.objects.create(
                user=user,
                role='customer',  # Mặc định là khách hàng, có thể đổi sau
            )
            print(f"✅ Đã tạo CustomerProfile cho user {user.username} (đăng ký bằng Google)")
            # Lưu flag để redirect đến trang chọn role
            if request:
                request.session['show_role_selection'] = True
                request.session.save()  # Đảm bảo session được lưu
    except Exception as e:
        print(f"❌ Lỗi tạo CustomerProfile cho social user: {e}")

@receiver(socialaccount_signup)
def check_customer_profile_on_social_signup(sender, request, user, **kwargs):
    """Kiểm tra và tạo CustomerProfile khi user đăng ký bằng Google (signal chạy sau khi user được lưu)"""
    try:
        # Kiểm tra xem user đã có profile chưa
        if not hasattr(user, 'customerprofile'):
            CustomerProfile.objects.create(
                user=user,
                role='customer',  # Mặc định là khách hàng, có thể đổi sau
            )
            print(f"✅ Đã tạo CustomerProfile cho user {user.username} (đăng ký bằng Google)")
            # Lưu flag để redirect đến trang chọn role
            if request:
                request.session['show_role_selection'] = True
                request.session.save()  # Đảm bảo session được lưu
    except Exception as e:
        print(f"❌ Lỗi tạo CustomerProfile khi đăng ký Google: {e}")

@receiver(pre_social_login)
def check_customer_profile_on_social_login(sender, request, sociallogin, **kwargs):
    """Kiểm tra CustomerProfile khi user đăng nhập bằng Google (kể cả user đã tồn tại)"""
    try:
        user = sociallogin.user
        # Đảm bảo username được tạo trước khi lưu user - dùng toàn bộ email làm username
        if user and not user.username:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            email = user.email or ''
            if email:
                # Dùng toàn bộ email làm username (ví dụ: abc@gmail.com)
                username = email
                # Đảm bảo username không trùng (nếu trùng thì thêm số)
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    # Nếu trùng, thêm số vào trước @ (ví dụ: abc1@gmail.com)
                    if '@' in base_username:
                        local_part, domain = base_username.split('@', 1)
                        username = f"{local_part}{counter}@{domain}"
                    else:
                        username = f"{base_username}{counter}"
                    counter += 1
                user.username = username
            else:
                # Nếu không có email, dùng random
                import random
                username = f"user_{random.randint(100000, 999999)}"
                while User.objects.filter(username=username).exists():
                    username = f"user_{random.randint(100000, 999999)}"
                user.username = username
            print(f"✅ Đã tạo username: {user.username} cho user email: {email}")

        # Chỉ xử lý khi user đã được xác thực và có pk (đã tồn tại trong DB)
        if user and user.pk:
            # Kiểm tra xem user đã có profile chưa
            if not hasattr(user, 'customerprofile'):
                from website.models import CustomerProfile
                CustomerProfile.objects.create(
                    user=user,
                    role='customer',  # Mặc định là khách hàng
                )
                print(f"✅ Đã tạo CustomerProfile cho user {user.username} (đăng nhập Google - user đã tồn tại)")
                # Lưu flag để redirect đến trang chọn role
                if request:
                    request.session['show_role_selection'] = True
                    request.session.save()  # Đảm bảo session được lưu
            else:
                # User đã có profile, nhưng nếu chưa có display_name thì cũng redirect
                profile = user.customerprofile
                if not profile.display_name and not user.first_name:
                    if request:
                        request.session['show_role_selection'] = True
                        request.session.save()
    except Exception as e:
        print(f"❌ Lỗi kiểm tra CustomerProfile khi đăng nhập Google: {e}")


# ===== Auto rebuild RAG when VIP pricing changes =====
@receiver([post_save, post_delete], sender=VIPPackageConfig)
def rebuild_rag_on_vip_change(sender, instance: VIPPackageConfig, **kwargs):
    """Khi thay đổi bảng giá VIP → rebuild RAG index và reload cache để RAG có doc VIP mới.
    Lưu ý: trả lời trực tiếp về bảng giá vẫn lấy từ DB ngay lập tức; rebuild nhằm cập nhật RAG context.
    """
    try:
        from django.core.management import call_command
        # Build nhanh TF-IDF + embeddings (nếu có), tự động reload cache
        call_command('build_rag_index')
    except Exception as e:
        print(f"Warning: auto RAG rebuild failed on VIP change: {e}")



















































