
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils import timezone
from .models import RentalPost, RentalPostImage, RentalVideo, CustomerProfile, Province, District, Ward, ChatThread, ChatMessage, Article, SuggestedLink, Wallet, RechargeTransaction, VIPSubscription, Notification, SavedPost, OTPCode, PostReport
from .notifications import notify
from .forms import RegisterForm, RentalPostForm, AccountProfileForm, ChangePasswordForm, RequestOTPForm, VerifyOTPForm, RechargeForm
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.db import models
from urllib.parse import urlencode

# Xóa báo cáo vi phạm của chính user
@login_required
@require_POST
def delete_report(request, report_id):
    report = get_object_or_404(PostReport, id=report_id, reporter=request.user)
    report.delete()
    messages.success(request, "Đã xóa báo cáo vi phạm.")
    return redirect('report_history')
def post_by_category(request, category_slug):
    price_range = request.GET.get('price')
    area_range = request.GET.get('area')
    has_video = request.GET.get('has_video')
    sort_newest = request.GET.get('newest')  # Tab "Mới đăng"

    posts = (RentalPost.objects.prefetch_related('images', 'videos')
             .order_by('-created_at'))
    # chỉ hiển thị bài công khai
    posts = posts.filter(is_rented=False, is_approved=True, category=category_slug)

    # Ẩn bài đã hết hạn
    from django.db import models as dj_models
    from django.utils import timezone as dj_timezone
    now_ts = dj_timezone.now()
    posts = posts.filter(dj_models.Q(expired_at__isnull=True) | dj_models.Q(expired_at__gt=now_ts))

    # lọc giá (tham số theo VNĐ như trang home)
    if price_range:
        try:
            min_price, max_price = map(float, price_range.split('-'))
            posts = posts.filter(
                price__gte=min_price / 1_000_000,
                price__lte=max_price / 1_000_000,
            )
        except ValueError:
            pass

    # lọc diện tích
    if area_range:
        try:
            min_area, max_area = map(float, area_range.split('-'))
            posts = posts.filter(area__gte=min_area, area__lte=max_area)
        except ValueError:
            pass

    # lọc bài có video
    if has_video:
        posts = posts.filter(videos__isnull=False).distinct()

    return render(
        request,
        'website/posts_by_category.html',
        {
            'posts': posts,
            'category': category_slug,
            'price_range': price_range or '',
            'area_range': area_range or '',
            'has_video': has_video,
            'sort_newest': sort_newest,
        },
    )

def home(request):
    price_range = request.GET.get('price')
    area_range = request.GET.get('area')
    has_video = request.GET.get('has_video')
    sort_newest = request.GET.get('newest')  # Tab "Mới đăng"
    province_id = request.GET.get('province')  # Filter theo tỉnh
    category = request.GET.get('category')  # Filter theo loại

    posts = RentalPost.objects.prefetch_related('images', 'videos')

    # Sắp xếp theo "Mới đăng" nếu có parameter
    if sort_newest:
        posts = posts.order_by('-created_at')  # Mới nhất trước
    else:
        posts = posts.order_by('-created_at')  # Mặc định cũng mới nhất

    # Ẩn bài đã cho thuê và chưa duyệt khỏi danh sách công khai
    posts = posts.filter(is_rented=False, is_approved=True)
    # Ẩn bài đã hết hạn (nếu có expired_at)
    from django.db import models as dj_models
    from django.utils import timezone as dj_timezone
    now_ts = dj_timezone.now()
    posts = posts.filter(dj_models.Q(expired_at__isnull=True) | dj_models.Q(expired_at__gt=now_ts))

    # lọc theo tỉnh
    if province_id:
        posts = posts.filter(province_id=province_id)

    # lọc theo category
    if category:
        posts = posts.filter(category=category)

    # lọc giá
    if price_range:
       try:
        min_price, max_price = map(float, price_range.split('-'))

        # Nếu DB đang lưu giá trị theo "triệu"
        # thì chia 1_000_000 để so với dữ liệu trong DB
        posts = posts.filter(
            price__gte=min_price / 1_000_000,
            price__lte=max_price / 1_000_000
        )
       except ValueError:
           pass


    # lọc diện tích
    if area_range:
        try:
            min_area, max_area = map(float, area_range.split('-'))
            posts = posts.filter(area__gte=min_area, area__lte=max_area)
        except ValueError:
            pass

    # lọc bài có video
    if has_video:
        posts = posts.filter(videos__isnull=False).distinct()

    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    recent_posts = posts[:5]

    # khai báo trước để tránh undefined
    saved_ids = set()

    if request.user.is_authenticated:
        saved_ids = set(
            SavedPost.objects.filter(user=request.user)
                              .values_list('post_id', flat=True)
        )

    # Lấy AI recommendations (5 bài) để hiển thị ở carousel "Tin đăng mới cập nhật"
    # NÂNG CẤP: Dùng Hybrid Recommender (ML + Content-based)
    recommended_posts = []
    if request.user.is_authenticated or request.session.session_key:
        from goiy_ai.ml_models.hybrid import HybridRecommender
        from django.db.models import Q
        from django.utils import timezone

        # Khởi tạo Hybrid Recommender (tự động load CF model nếu có)
        hybrid_recommender = HybridRecommender()

        user = request.user if request.user.is_authenticated else None
        session_id = request.session.session_key
        if not session_id:
            request.session.create()
            session_id = request.session.session_key

        # Lấy recommendations từ Hybrid AI (ML + Content-based)
        ai_recommendations = hybrid_recommender.get_recommendations(
            user=user,
            limit=20,  # Lấy nhiều hơn để đảm bảo có đủ 5 bài sau khi filter
            context={'session_id': session_id}
        )

        # Filter: chỉ lấy bài đã duyệt, chưa cho thuê, chưa hết hạn
        now = timezone.now()
        if ai_recommendations:
            # Lấy list IDs từ AI recommendations và giữ nguyên thứ tự
            rec_ids = [post.id for post in ai_recommendations]

            # Filter lại với các điều kiện
            filtered_posts = RentalPost.objects.filter(
                id__in=rec_ids,
                is_approved=True,
                is_rented=False
            ).filter(
                Q(expired_at__isnull=True) | Q(expired_at__gt=now)
            )

            # Giữ nguyên thứ tự từ AI (không sort lại)
            # Tạo dict để lookup nhanh
            posts_dict = {post.id: post for post in filtered_posts}

            # Giữ thứ tự từ AI recommendations
            recommended_posts = []
            for post_id in rec_ids:
                if post_id in posts_dict:
                    recommended_posts.append(posts_dict[post_id])
                    if len(recommended_posts) >= 6:
                        break
        else:
            recommended_posts = []

    # Lấy các tỉnh/thành phố nổi bật với số lượng tin đăng
    from django.db.models import Count
    featured_provinces = Province.objects.annotate(
        post_count=Count(
            'rentalpost',
            filter=dj_models.Q(
                rentalpost__is_approved=True,
                rentalpost__is_rented=False,
                rentalpost__is_deleted=False
            ) & (
                dj_models.Q(rentalpost__expired_at__isnull=True) |
                dj_models.Q(rentalpost__expired_at__gt=now_ts)
            )
        )
    ).filter(post_count__gt=0).order_by('-post_count')[:5]

    # Lấy ảnh cho từng tỉnh (bài đăng có nhiều views nhất)
    for province in featured_provinces:
        top_post = RentalPost.objects.filter(
            province=province,
            is_approved=True,
            is_rented=False,
            is_deleted=False,
            images__isnull=False
        ).filter(
            dj_models.Q(expired_at__isnull=True) | dj_models.Q(expired_at__gt=now_ts)
        ).order_by('-ai_views').select_related().prefetch_related('images').first()

        if top_post and top_post.images.exists():
            province.featured_image = top_post.images.first().image
        else:
            province.featured_image = None

    return render(
        request,
        'website/home.html',
        {
            'page_obj': page_obj,
            'recent_posts': recent_posts,
            'articles': Article.objects.filter(is_published=True)[:6],
            'suggested_links': SuggestedLink.objects.filter(is_active=True).order_by('order')[:6],
            'price_range': price_range,
            'area_range': area_range,
            'has_video': has_video,
            'saved_ids': saved_ids,
            'recommended_posts': recommended_posts,  # Carousel AI recommendations
            'sort_newest': sort_newest,  # Tab "Mới đăng" active
            'featured_provinces': featured_provinces,  # Tỉnh/thành phố nổi bật
        }
    )

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            CustomerProfile.objects.create(
                user=user,
                phone=form.cleaned_data.get('phone'),
                address=form.cleaned_data.get('address'),
                role=form.cleaned_data.get('role')
            )
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'website/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')

        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, 'Đăng nhập thành công!')
            return redirect('home')
        else:
            # Đăng nhập thất bại - giữ lại username
            messages.error(request, 'Tên đăng nhập hoặc mật khẩu không đúng!')
            return render(request, 'website/login.html', {
                'form': form,
                'login_failed': True,
                'username': username
            })
    else:
        form = AuthenticationForm()
    return render(request, 'website/login.html', {'form': form})


def forgot_password(request):
    """Trang gửi OTP đặt lại mật khẩu và đặt mật khẩu mới bằng OTP."""
    if request.method == 'POST':
        step = request.POST.get('step', 'send')
        email = request.POST.get('email')

        print(f"[FORGOT PASSWORD] Step: {step}, Email: {email}")  # DEBUG

        # Kiểm tra nếu là AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
        print(f"[FORGOT PASSWORD] Is AJAX: {is_ajax}")  # DEBUG

        if step == 'send':
            from django.contrib.auth.models import User
            from django.db.models import Q
            from django.http import JsonResponse
            try:
                # Tìm user theo email hoặc username (vì có thể username chính là email)
                # Ưu tiên user có email khớp chính xác, sau đó mới đến username
                user = User.objects.filter(Q(email=email) | Q(username=email)).first()
                print(f"[FORGOT PASSWORD] User found: {user}")  # DEBUG
                if not user:
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': 'Email không tồn tại'})
                    return render(request, 'website/forgot_password.html', {'error': 'Email không tồn tại'})
            except Exception as e:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Có lỗi xảy ra. Vui lòng thử lại!'})
                return render(request, 'website/forgot_password.html', {'error': 'Có lỗi xảy ra. Vui lòng thử lại!'})
            otp = OTPCode.create_for_user(user, email, purpose='account_recovery', ttl_minutes=10)
            print(f"[FORGOT PASSWORD] OTP created: {otp.code}")  # DEBUG
            try:
                send_mail('Mã đặt lại mật khẩu', f"Mã OTP của bạn là: {otp.code}", settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
            except Exception as e:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': str(e)})
                return render(request, 'website/forgot_password.html', {'error': str(e)})

            if is_ajax:
                return JsonResponse({'success': True, 'message': 'OTP đã được gửi đến email của bạn'})
            return render(request, 'website/forgot_password.html', {'email': email, 'sent': True})
        else:
            from django.contrib.auth.models import User
            from django.db.models import Q
            from django.http import JsonResponse
            otp_code = request.POST.get('otp')
            new_password = request.POST.get('new_password')
            confirm = request.POST.get('confirm_password')
            if new_password != confirm:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Mật khẩu xác nhận không khớp'})
                return render(request, 'website/forgot_password.html', {'email': email, 'sent': True, 'error': 'Mật khẩu xác nhận không khớp'})
            try:
                # Tìm user theo email hoặc username
                user = User.objects.filter(Q(email=email) | Q(username=email)).first()
                if not user:
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': 'Email không tồn tại'})
                    return render(request, 'website/forgot_password.html', {'error': 'Email không tồn tại'})
            except Exception as e:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Có lỗi xảy ra. Vui lòng thử lại!'})
                return render(request, 'website/forgot_password.html', {'error': 'Có lỗi xảy ra. Vui lòng thử lại!'})
            otp = OTPCode.objects.filter(user=user, purpose='account_recovery', is_used=False).order_by('-created_at').first()
            if not otp or not otp.is_valid(otp_code):
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'OTP không hợp lệ hoặc đã hết hạn'})
                return render(request, 'website/forgot_password.html', {'email': email, 'sent': True, 'error': 'OTP không hợp lệ hoặc đã hết hạn'})
            otp.is_used = True
            otp.save(update_fields=['is_used'])
            user.set_password(new_password)
            user.save(update_fields=['password'])

            if is_ajax:
                return JsonResponse({'success': True, 'message': 'Đặt lại mật khẩu thành công'})
            return redirect('login')
    return render(request, 'website/forgot_password.html')

def logout_view(request):
    # XÓA HOÀN TOÀN session cũ để AI recommendations reset
    request.session.flush()  # Xóa session data và tạo session key mới
    logout(request)
    return redirect('home')

@login_required(login_url='login')
def post_create(request):
    # Yêu cầu có VIP còn hạn và giới hạn số lượt đăng theo ngày
    active_vip = VIPSubscription.objects.filter(
        user=request.user,
        expires_at__gte=timezone.now()
    ).select_related('user').order_by('-expires_at').first()

    if not active_vip:
        messages.warning(request, 'Bạn cần đăng ký gói VIP để đăng tin.')
        return redirect('bang_gia_dich_vu')

    # Kiểm tra số bài đã đăng hôm nay theo giới hạn gói (dùng timezone local)
    today_local = timezone.localtime(timezone.now()).date()
    from datetime import datetime, time
    start_of_day = timezone.make_aware(datetime.combine(today_local, time.min))
    end_of_day = timezone.make_aware(datetime.combine(today_local, time.max))

    # Chỉ tính các bài đăng/gia hạn sau thời điểm bắt đầu của gói VIP hiện tại
    vip_start = active_vip.registered_at if active_vip else start_of_day
    filter_start = max(start_of_day, vip_start)

    # Tối ưu: Dùng 1 query với aggregate thay vì 2 queries riêng
    from django.db.models import Q, Count
    usage_stats = RentalPost.objects.filter(
        Q(created_at__gte=filter_start, created_at__lte=end_of_day) |
        Q(renewed_at__gte=filter_start, renewed_at__lte=end_of_day),
        user=request.user
    ).aggregate(
        posts=Count('id', filter=Q(created_at__gte=filter_start, created_at__lte=end_of_day)),
        renewals=Count('id', filter=Q(renewed_at__gte=filter_start, renewed_at__lte=end_of_day))
    )

    used_today = (usage_stats['posts'] or 0) + (usage_stats['renewals'] or 0)
    limit_per_day = active_vip.posts_per_day

    if limit_per_day and used_today >= limit_per_day:
        messages.error(
            request,
            f"Bạn đã dùng hết lượt hôm nay theo gói {active_vip.get_plan_display()} (tối đa {limit_per_day} lượt/ngày cho đăng tin hoặc gia hạn). Vui lòng quay lại vào ngày mai hoặc có thể đăng ký gói VIP khác để tiếp tục đăng tin."
        )
        return redirect('bang_gia_dich_vu')

    if request.method == 'POST':
        post_form = RentalPostForm(request.POST, request.FILES)
        images = request.FILES.getlist('image')
        video = request.FILES.get('video')

        if post_form.is_valid():
            post = post_form.save(commit=False)
            post.user = request.user

            # Nếu không nhập số điện thoại, lấy từ tài khoản
            if not post.phone_number:
                try:
                    profile = CustomerProfile.objects.get(user=request.user)
                    post.phone_number = profile.phone or ''
                except CustomerProfile.DoesNotExist:
                    post.phone_number = ''

            # Lấy object địa lý từ form
            ward = post_form.cleaned_data.get('ward')
            district = post_form.cleaned_data.get('district')
            province = post_form.cleaned_data.get('province')

            # GÁN FK vào bài đăng để còn lọc
            post.ward = ward
            post.district = district
            post.province = province

            # Dựng địa chỉ hiển thị
            house_number = (post_form.cleaned_data.get('house_number') or '').strip()
            street = post_form.cleaned_data.get('street') or ''
            parts = [
                house_number,
                street,
                getattr(ward, 'name', '') if ward else '',
                getattr(district, 'name', '') if district else '',
                getattr(province, 'name', '') if province else '',
            ]
            post.address = ', '.join([p for p in parts if p])

            # Thiết lập hạn bài dựa theo VIP (sử dụng lại active_vip đã query)
            if active_vip:
                expire_days = active_vip.post_expire_days
                if expire_days:
                    post.expired_at = timezone.now() + timezone.timedelta(days=expire_days)

            post.save()

            for img in images:
                RentalPostImage.objects.create(post=post, image=img)

            if video:
                RentalVideo.objects.create(post=post, video=video)

            return redirect('home')
        else:
            print("❌ Form lỗi:", post_form.errors)
    else:
        post_form = RentalPostForm()

    return render(request, 'website/post_form.html', {'form': post_form})

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import RentalPost, CustomerProfile, DeletionLog

@login_required
def manage_rooms(request):
    # Lấy profile (nếu có dùng để hiển thị thêm info sau này)
    profile = CustomerProfile.objects.get(user=request.user)
    status = request.GET.get("status", "all")
    search_query = request.GET.get("search", "").strip()

    # Lấy cả bài bị admin gỡ (is_deleted=True) để chủ trọ có thể xem và xóa
    base_rooms = RentalPost.objects.filter(user=profile.user)

    # Tìm kiếm theo tiêu đề hoặc ID
    if search_query:
        base_rooms = base_rooms.filter(
            models.Q(title__icontains=search_query) |
            models.Q(id__icontains=search_query)
        )

    # Điều kiện bài còn hiệu lực để hiển thị
    now = timezone.now()
    display_q = models.Q(expired_at__isnull=True) | models.Q(expired_at__gt=now)
    # Apply filter to listing only
    rooms = base_rooms
    if status == "display":
        rooms = base_rooms.filter(display_q, is_rented=False, is_approved=True, is_deleted=False)
    elif status == "vacant":
        rooms = base_rooms.filter(is_rented=False, is_approved=True, is_deleted=False)
    elif status == "pending":
        # Chỉ hiển thị bài đang chờ duyệt (chưa duyệt VÀ chưa bị từ chối), loại trừ bài đã bị admin gỡ
        rooms = base_rooms.filter(
            is_approved=False,
            is_rejected=False,
            is_deleted=False
        ).exclude(reports__auto_removed=True)
    elif status == "rented":
        # Chỉ hiển thị phòng có RentalRequest với status='confirmed'
        rooms = base_rooms.filter(
            is_deleted=False,
            rental_requests__status='confirmed'
        ).distinct()
    elif status == "expired":
        # Lọc những bài đã hết hạn
        rooms = base_rooms.filter(expired_at__isnull=False, expired_at__lte=now, is_deleted=False)
    elif status == "removed":
        # Lọc bài bị admin gỡ HOẶC từ chối: is_deleted=True, is_rejected=True, hoặc có báo cáo auto_removed
        rooms = base_rooms.filter(
            models.Q(is_deleted=True) |
            models.Q(is_rejected=True) |
            (models.Q(reports__auto_removed=True) & models.Q(is_approved=False))
        ).distinct()

    # Annotate: đánh dấu những bài từng bị auto_removed trong PostReport (để hiển thị đúng trạng thái cho dữ liệu cũ)
    from django.db.models import Exists, OuterRef
    from .models import PostReport
    rooms = rooms.annotate(
        was_auto_removed=Exists(PostReport.objects.filter(post=OuterRef('pk'), auto_removed=True))
    )

    # Thống kê
    total_count = base_rooms.filter(is_deleted=False).count()
    # Chỉ tính những tin đã được duyệt (is_approved=True)
    display_count = base_rooms.filter(display_q, is_rented=False, is_approved=True, is_deleted=False).count()
    vacant_count = base_rooms.filter(is_rented=False, is_approved=True, is_deleted=False).count()
    # Chỉ đếm tin đang chờ duyệt (chưa duyệt VÀ chưa bị từ chối)
    pending_count = base_rooms.filter(
        is_approved=False,
        is_rejected=False,
        is_deleted=False
    ).exclude(reports__auto_removed=True).count()

    # ĐẾM ĐÚNG: Số phòng có RentalRequest với status='confirmed'
    from django.db.models import Exists, OuterRef
    rented_count = base_rooms.filter(
        is_deleted=False,
        rental_requests__status='confirmed'
    ).distinct().count()

    expired_count = base_rooms.filter(expired_at__isnull=False, expired_at__lte=now, is_deleted=False).count()
    # Đếm cả tin bị admin gỡ VÀ từ chối
    removed_count = base_rooms.filter(
        models.Q(is_deleted=True) |
        models.Q(is_rejected=True) |
        (models.Q(reports__auto_removed=True) & models.Q(is_approved=False))
    ).distinct().count()

    # Lấy các yêu cầu thuê cho các bài của chủ trọ
    from .models import RentalRequest
    requests_by_post = {}
    for room in rooms:
        requests = RentalRequest.objects.filter(post=room).select_related('customer')
        requests_by_post[room.id] = list(requests)
    return render(
        request,
        "website/manage_rooms.html",
        {
            "rooms": rooms,
            "status": status,
            "profile": profile,
            "total_count": total_count,
            "display_count": display_count,
            "vacant_count": vacant_count,
            "pending_count": pending_count,
            "rented_count": rented_count,
            "expired_count": expired_count,
            "removed_count": removed_count,
            "search_query": search_query,
            "now": now,
            "rental_requests_by_post": requests_by_post,
        },
    )

@login_required
def rental_management(request):
    """Trang Quản lý thuê: hiển thị các yêu cầu thuê trọ cho từng bài đăng của chủ trọ."""
    profile = CustomerProfile.objects.get(user=request.user)
    rooms = RentalPost.objects.filter(user=profile.user).order_by('-created_at')
    from .models import RentalRequest
    requests_by_post = {}
    for room in rooms:
        reqs = RentalRequest.objects.filter(post=room).select_related('customer')
        if reqs.exists():
            requests_by_post[room.id] = list(reqs)
    return render(
        request,
        'website/rental_management.html',
        {
            'rooms': rooms,
            'rental_requests_by_post': requests_by_post,
            'profile': profile,
        }
    )

@login_required
def expired_posts(request):
    """Hiển thị danh sách bài đăng hết hạn của user"""
    profile = CustomerProfile.objects.get(user=request.user)
    now = timezone.now()

    # Lấy tất cả bài đăng hết hạn
    expired_posts = RentalPost.objects.filter(
        user=profile.user,
        expired_at__isnull=False,
        expired_at__lte=now
    ).select_related('province', 'district', 'ward').prefetch_related('images').order_by('-expired_at')

    # Thống kê
    total_expired = expired_posts.count()

    # Kiểm tra VIP hiện tại
    current_vip = VIPSubscription.objects.filter(user=request.user, expires_at__gte=now).order_by('-expires_at').first()

    return render(
        request,
        "website/expired_posts.html",
        {
            "expired_posts": expired_posts,
            "total_expired": total_expired,
            "profile": profile,
            "current_vip": current_vip,
        },
    )

@login_required
def select_posts_to_renew(request):
    """Trang chọn bài đăng để gia hạn"""
    now = timezone.now()
    current_vip = VIPSubscription.objects.filter(user=request.user, expires_at__gte=now).order_by('-expires_at').first()

    if not current_vip:
        messages.error(request, 'Bạn cần có gói VIP để gia hạn bài đăng.')
        return redirect('bang_gia_dich_vu')

    # Lấy bài đăng hết hạn và annotate xem có người đang thuê không
    from django.db.models import Exists, OuterRef

    active_rental_subquery = RentalRequest.objects.filter(
        post=OuterRef('pk'),
        status='confirmed'
    )

    expired_posts = RentalPost.objects.filter(
        user=request.user,
        expired_at__isnull=False,
        expired_at__lte=now
    ).select_related('province', 'district', 'ward').annotate(
        has_active_rental=Exists(active_rental_subquery)
    )

    if request.method == 'POST':
        selected_post_ids = request.POST.getlist('selected_posts')

        if not selected_post_ids:
            messages.error(request, 'Vui lòng chọn ít nhất một bài đăng để gia hạn.')
            return render(request, 'website/select_posts_to_renew.html', {
                'expired_posts': expired_posts,
                'current_vip': current_vip,
            })

        # Kiểm tra giới hạn theo gói VIP: chỉ tính các bài đăng/gia hạn sau thời điểm bắt đầu của gói VIP hiện tại
        today_local = timezone.localtime(timezone.now()).date()
        from datetime import datetime, time
        start_of_day = timezone.make_aware(datetime.combine(today_local, time.min))
        end_of_day = timezone.make_aware(datetime.combine(today_local, time.max))
        vip_start = current_vip.registered_at if current_vip else start_of_day
        posts_today = RentalPost.objects.filter(
            user=request.user,
            created_at__gte=max(start_of_day, vip_start),
            created_at__lte=end_of_day
        ).count()
        renewals_today = RentalPost.objects.filter(
            user=request.user,
            renewed_at__gte=max(start_of_day, vip_start),
            renewed_at__lte=end_of_day
        ).count()
        used_today = posts_today + renewals_today
        limit_per_day = current_vip.posts_per_day
        remaining = max(0, (limit_per_day or 0) - used_today)
        if limit_per_day and remaining <= 0:
            messages.error(request, f'Bạn đã dùng hết lượt hôm nay ({limit_per_day}/ngày) theo gói {current_vip.get_plan_display()}.')
            return render(request, 'website/select_posts_to_renew.html', {
                'expired_posts': expired_posts,
                'current_vip': current_vip,
            })
        if limit_per_day and len(selected_post_ids) > remaining:
            messages.error(request, f'Bạn chỉ còn {remaining} lượt gia hạn cho hôm nay. Hãy giảm số lượng bài được chọn.')
            return render(request, 'website/select_posts_to_renew.html', {
                'expired_posts': expired_posts,
                'current_vip': current_vip,
            })

        # Gia hạn các bài đăng được chọn
        post_expire_days = current_vip.post_expire_days
        renewed_count = 0
        blocked_posts = []  # Bài đang có người thuê, không cho gia hạn

        for post_id in selected_post_ids:
            try:
                post = RentalPost.objects.get(id=post_id, user=request.user, expired_at__lte=now)

                # Kiểm tra xem có RentalRequest nào đã confirm (đang thuê) không
                active_rental = RentalRequest.objects.filter(
                    post=post,
                    status='confirmed'
                ).exists()

                if active_rental:
                    blocked_posts.append(post.title[:50])
                    continue

                post.expired_at = now + timezone.timedelta(days=post_expire_days)
                post.renewed_at = now
                post.save(update_fields=['expired_at', 'renewed_at'])
                renewed_count += 1
            except RentalPost.DoesNotExist:
                continue

        if renewed_count > 0:
            messages.success(request, f'Đã gia hạn {renewed_count} bài đăng thêm {post_expire_days} ngày.')

        if blocked_posts:
            blocked_list = ', '.join(blocked_posts)
            messages.warning(request, f'⚠️ Không thể gia hạn các tin đang có người thuê: {blocked_list}. Vui lòng đợi khách trả phòng.')

        if renewed_count == 0 and not blocked_posts:
            messages.error(request, 'Không có bài đăng nào được gia hạn.')

        return redirect('expired_posts')

    return render(request, 'website/select_posts_to_renew.html', {
        'expired_posts': expired_posts,
        'current_vip': current_vip,
    })

@login_required
def edit_room(request, room_id):
    room = get_object_or_404(RentalPost, id=room_id, user=request.user)

    # Không cho sửa nếu phòng đã cho thuê
    if room.is_rented:
        messages.error(request, '🔒 Không thể chỉnh sửa phòng đã cho thuê. Vui lòng hủy phòng trước khi chỉnh sửa.')
        return redirect('manage_rooms')

    if request.method == "POST":
        form = RentalPostForm(request.POST, request.FILES, instance=room)
        if form.is_valid():
            room = form.save()

            # Xử lý upload ảnh mới
            images = request.FILES.getlist('images')
            for image in images:
                RentalPostImage.objects.create(post=room, image=image)

            messages.success(request, '✅ Đã cập nhật tin đăng thành công!')
            return redirect("manage_rooms")
    else:
        form = RentalPostForm(instance=room)
    return render(request, "website/edit_room.html", {"form": form, "room": room})

@login_required
def delete_room(request, room_id):
    room = get_object_or_404(RentalPost, id=room_id, user=request.user)

    # Không cho xóa nếu phòng đã cho thuê
    if room.is_rented:
        messages.error(request, '🔒 Không thể xóa phòng đã cho thuê. Vui lòng hủy phòng trước khi xóa.')
        return redirect('manage_rooms')

    if request.method == "POST":
        # Ghi log trước khi xóa
        try:
            DeletionLog.objects.create(
                post_title=room.title,
                post_id=room.id,
                deleted_by=request.user,
                deleted_user=request.user,
                reason='user_delete'
            )
        except Exception:
            pass
        room.delete()
        messages.success(request, '✅ Đã xóa tin đăng thành công!')
        return redirect("manage_rooms")
    return render(request, "website/delete_room.html", {"room": room})

@login_required
@require_POST
def delete_room_image(request, image_id):
    """Xóa một ảnh cụ thể của phòng"""
    try:
        image = get_object_or_404(RentalPostImage, id=image_id)

        # Kiểm tra quyền sở hữu
        if image.post.user != request.user:
            return JsonResponse({
                'success': False,
                'error': 'Bạn không có quyền xóa ảnh này'
            }, status=403)

        # Xóa file vật lý
        if image.image:
            image.image.delete(save=False)

        # Xóa record trong database
        image.delete()

        return JsonResponse({
            'success': True,
            'message': 'Đã xóa ảnh thành công'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def deletion_logs(request):
    logs = DeletionLog.objects.filter(deleted_user=request.user)
    return render(request, 'website/deletion_logs.html', {'logs': logs})

@login_required
@require_POST
def toggle_rented(request, room_id):
    room = get_object_or_404(RentalPost, id=room_id, user=request.user)

    # Không cho phép đổi trạng thái thuê với tin chưa được admin duyệt
    if not room.is_approved:
        return JsonResponse({
            'status': 'forbidden',
            'message': 'Tin chưa được admin duyệt, không thể đánh dấu đã cho thuê.'
        }, status=403)

    # Chỉ cho phép chuyển từ True → False (mở lại), không cho từ False → True
    # Vì việc đánh dấu cho thuê đã tự động khi khách xác nhận
    if room.is_rented:
        # Kiểm tra xem có yêu cầu thuê đang confirmed không
        from .models import RentalRequest
        active_rental = RentalRequest.objects.filter(post=room, status='confirmed').first()
        if active_rental:
            return JsonResponse({
                'status': 'forbidden',
                'message': 'Không thể mở lại phòng đang có người thuê. Vui lòng hủy yêu cầu thuê trước.'
            }, status=403)

        # Cho phép mở lại
        room.is_rented = False
        room.save(update_fields=['is_rented'])
        return JsonResponse({'status': 'ok', 'is_rented': False, 'message': 'Đã mở lại phòng'})
    else:
        return JsonResponse({
            'status': 'forbidden',
            'message': 'Phòng sẽ tự động đánh dấu cho thuê khi khách xác nhận thuê.'
        }, status=403)

def rental_list(request):
    province_id = request.GET.get("province") or ""
    district_id = request.GET.get("district") or ""
    ward_id = request.GET.get("ward") or ""
    price_range = request.GET.get('price')
    area_range = request.GET.get('area')
    category = request.GET.get('type')   # loại phòng (category)
    features = request.GET.getlist('features')  # nhận nhiều feature

    posts = RentalPost.objects.prefetch_related('images', 'videos') \
                              .select_related('province','district','ward') \
                              .order_by('-created_at')
    # Ẩn bài đã cho thuê và chưa duyệt khỏi danh sách công khai
    posts = posts.filter(is_rented=False, is_approved=True)
    # Ẩn bài đã hết hạn
    from django.db import models as dj_models
    from django.utils import timezone as dj_timezone
    now_ts = dj_timezone.now()
    posts = posts.filter(dj_models.Q(expired_at__isnull=True) | dj_models.Q(expired_at__gt=now_ts))

    # Location filters
    if province_id:
        posts = posts.filter(province_id=province_id)
    if district_id:
        posts = posts.filter(district_id=district_id)
    if ward_id:
        posts = posts.filter(ward_id=ward_id)

    # Category filter
    if category:
        posts = posts.filter(category=category)

    # Price filter
    # lọc giá
    if price_range:
       try:
        min_price, max_price = map(float, price_range.split('-'))

        # Nếu DB đang lưu giá trị theo "triệu"
        # thì chia 1_000_000 để so với dữ liệu trong DB
        posts = posts.filter(
            price__gte=min_price / 1_000_000,
            price__lte=max_price / 1_000_000
        )
       except ValueError:
             pass


    # Area filter
    if area_range:
        try:
            min_a, max_a = map(float, area_range.split('-'))
            posts = posts.filter(area__gte=min_a, area__lte=max_a)
        except:
            pass

    # Features filter (MultiSelectField)
    if features:
        for f in features:
            posts = posts.filter(features__contains=f)

    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    recent_posts = posts[:5]
    provinces = Province.objects.all().order_by('name')

    context = {
        'page_obj': page_obj,
        'recent_posts': recent_posts,
        'provinces': provinces,
        'province_id': province_id,
        'district_id': district_id,
        'ward_id': ward_id,
        'price_range': price_range or "",
        'area_range': area_range or "",
        'category': category or "",
        'selected_features': features,
    }
    return render(request, 'website/rental_list.html', context)


def load_districts(request):
    province_id = request.GET.get("province_id")
    districts = District.objects.filter(province_id=province_id).values("id", "name")
    return JsonResponse(list(districts), safe=False)

def load_wards(request):
    district_id = request.GET.get("district_id")
    wards = Ward.objects.filter(district_id=district_id).values("id", "name")
    return JsonResponse(list(wards), safe=False)
def load_provinces(request):
    # trả danh sách provinces để modal/JS có thể load
    provinces = Province.objects.all().order_by('name').values('id', 'name')
    return JsonResponse(list(provinces), safe=False)
def post_detail(request, pk):
    from django.utils import timezone
    post = get_object_or_404(RentalPost, pk=pk)

    # 🔥 TRACKING: Log view event for analytics
    if request.user.is_authenticated:
        from goiy_ai.models import PostView, UserInteraction
        # Track view in PostView
        PostView.objects.create(
            user=request.user,
            post=post,
            session_id=request.session.session_key or '',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        # Track interaction
        UserInteraction.objects.create(
            user=request.user,
            post=post,
            session_id=request.session.session_key or '',
            interaction_type='view',
            ip_address=request.META.get('REMOTE_ADDR')
        )

    # Nếu bài đã bị admin gỡ (soft delete bởi staff) thì chỉ chặn khách/ngoài chủ
    if post.is_deleted and post.deleted_by and post.deleted_by.is_staff:
        if not request.user.is_authenticated or request.user != post.user:
            return render(request, 'website/post_removed_admin.html', {'post': post}, status=403)

    # Kiểm tra auto_removed qua PostReport
    try:
        auto_removed = PostReport.objects.filter(post=post, auto_removed=True).exists()
    except Exception:
        auto_removed = False

    # Kiểm tra có report trạng thái chờ xử lý hoặc đang xem xét
    try:
        active_report = PostReport.objects.filter(post=post, status__in=['pending', 'reviewing']).first()
    except Exception:
        active_report = None
    images = post.images.all()
    videos = post.videos.all()
    # Check if current user already reported this post
    already_reported = False
    if request.user.is_authenticated:
        try:
            already_reported = PostReport.objects.filter(post=post, reporter=request.user).exists()
        except Exception:
            already_reported = False

    # lấy danh sách id bài đã lưu
    saved_ids = set()
    if request.user.is_authenticated:
        saved_ids = set(
            SavedPost.objects.filter(user=request.user)
                              .values_list('post_id', flat=True)
        )

    # Lấy tin đăng cùng khu vực (cùng quận/huyện)
    # Chỉ lấy bài đã duyệt, chưa hết hạn, không phải bài hiện tại
    same_area_posts = RentalPost.objects.filter(
        district=post.district,
        is_approved=True,
        is_rented=False
    ).exclude(pk=pk)

    # Lọc bài chưa hết hạn
    now = timezone.now()
    same_area_posts = same_area_posts.filter(
        models.Q(expired_at__isnull=True) | models.Q(expired_at__gt=now)
    ).order_by('-created_at')[:4]  # Lấy 4 bài

    return render(
        request,
        'website/post_detail.html',
        {
            'post': post,
            'images': images,
            'videos': videos,
            'same_area_posts': same_area_posts,
            'saved_ids': saved_ids,
            'already_reported': already_reported,
            'auto_removed': auto_removed,
            'active_report': active_report,
        }
    )


@login_required
def report_history(request):
    """Lịch sử báo cáo vi phạm của tài khoản hiện tại.
    Hỗ trợ lọc theo trạng thái qua query param ?status=...
    """
    status = (request.GET.get('status') or '').strip()
    reports = PostReport.objects.filter(reporter=request.user).select_related('post')
    if status in dict(PostReport.STATUS_CHOICES):
        reports = reports.filter(status=status)

    reports = reports.order_by('-created_at')

    # Thống kê theo trạng thái để hiển thị badge/tab
    from django.db.models import Count
    stats = (PostReport.objects
             .filter(reporter=request.user)
             .values('status')
             .annotate(total=Count('id')))
    stats_map = {row['status']: row['total'] for row in stats}

    return render(request, 'website/report_history.html', {
        'reports': reports,
        'status': status,
        'status_choices': PostReport.STATUS_CHOICES,
        'stats_map': stats_map,
    })

@login_required
def saved_posts_list(request):
    saved_posts = SavedPost.objects.filter(user=request.user).select_related('post')
    # Lấy trạng thái yêu cầu thuê cho từng bài
    requests_map = {}
    from .models import RentalRequest
    for item in saved_posts:
        req = RentalRequest.objects.filter(customer=request.user, post=item.post).first()
        requests_map[item.post.id] = req
    return render(request, 'website/saved_posts_list.html', {
        'saved_posts': saved_posts,
        'rental_requests': requests_map,
    })

@login_required
def my_rooms(request):
    """Trang Phòng của tôi - hiển thị các phòng đã xác nhận thuê"""
    from .models import RentalRequest, LandlordReview
    from django.db.models import Exists, OuterRef
    reviews_subq = LandlordReview.objects.filter(rental_request=OuterRef('pk'))
    confirmed_requests = RentalRequest.objects.filter(
        customer=request.user,
        status='confirmed'
    ).select_related('post').annotate(has_review=Exists(reviews_subq)).order_by('-updated_at')

    return render(request, 'website/my_rooms.html', {
        'confirmed_requests': confirmed_requests,
    })


# ================= LANDLORD REVIEWS =================
from .forms import LandlordReviewForm
from django.contrib.auth.models import User
from .models import LandlordReview, RentalRequest

@login_required
def submit_landlord_review(request, request_id: int):
    """Khách hàng gửi đánh giá cho chủ trọ sau khi đã xác nhận thuê.
    Mỗi RentalRequest chỉ được đánh giá một lần.
    """
    rental_request = get_object_or_404(RentalRequest, id=request_id, customer=request.user, status='confirmed')

    # Nếu đã đánh giá rồi thì chuyển đến trang reviews của landlord
    if hasattr(rental_request, 'landlord_review'):
        return redirect('landlord_reviews', user_id=rental_request.post.user.id)

    if request.method == 'POST':
        form = LandlordReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.rental_request = rental_request
            review.landlord = rental_request.post.user
            review.reviewer = request.user
            review.save()
            # Gửi thông báo cho chủ trọ
            try:
                notify(
                    user=review.landlord,
                    type_='review_received',
                    title='Bạn nhận được một đánh giá mới',
                    message=f"{request.user.username} đã đánh giá bạn {review.rating}★",
                    url=reverse('landlord_reviews', kwargs={'user_id': review.landlord.id}),
                    rental_request=rental_request,
                    post=rental_request.post
                )
            except Exception:
                pass
            messages.success(request, '✅ Đã gửi đánh giá. Cảm ơn bạn!')
            return redirect('landlord_reviews', user_id=review.landlord.id)
    else:
        form = LandlordReviewForm()

    return render(request, 'website/submit_landlord_review.html', {
        'form': form,
        'rental_request': rental_request,
    })


@login_required
def landlord_reviews(request, user_id: int):
    """Trang hiển thị danh sách các đánh giá dành cho một chủ trọ."""
    landlord = get_object_or_404(User, id=user_id)
    reviews = LandlordReview.objects.filter(landlord=landlord, is_approved=True).select_related('reviewer')
    avg, total = LandlordReview.get_summary_for(landlord)
    can_delete_reviews = (request.user == landlord) or request.user.is_staff
    return render(request, 'website/landlord_reviews.html', {
        'landlord': landlord,
        'reviews': reviews,
        'avg': avg,
        'total': total,
        'can_delete_reviews': can_delete_reviews,
    })


@login_required
@require_POST
def delete_landlord_review(request, review_id: int):
    """Xóa đánh giá của khách. Chỉ chủ trọ được đánh giá đó hoặc staff mới được phép."""
    review = get_object_or_404(LandlordReview, id=review_id)
    if (request.user != review.landlord) and (not request.user.is_staff):
        return JsonResponse({'status': 'error', 'message': 'Không có quyền xóa'}, status=403)
    review.delete()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def cancel_rental_request(request, request_id):
    """Khách hàng hủy phòng đã xác nhận thuê"""
    req = get_object_or_404(RentalRequest, id=request_id, customer=request.user)
    if req.status == 'confirmed':
        # Chuyển sang trạng thái chờ xác nhận hủy, lưu lý do
        cancel_reason = request.POST.get('cancel_reason', '').strip()
        if not cancel_reason:
            messages.error(request, "Bạn phải nhập lý do hủy phòng.")
            return redirect('my_rooms')
        req.cancel_reason = cancel_reason
        req.cancel_request_status = 'waiting'
        req.save(update_fields=['cancel_reason', 'cancel_request_status'])
        try:
            notify(user=req.post.user, type_='rental_cancel_requested',
                   title='Khách yêu cầu hủy phòng',
                   message=f"{request.user.username} đã yêu cầu hủy phòng '{req.post.title}'.",
                   url=reverse('rental_management'), rental_request=req, post=req.post)
        except Exception:
            pass
        messages.success(request, "Yêu cầu hủy phòng đã được gửi đến chủ trọ, vui lòng chờ xác nhận.")
    else:
        messages.error(request, "Chỉ có thể hủy phòng đã xác nhận thuê.")
    return redirect('my_rooms')

@login_required
@require_POST
def owner_cancel_rental_request(request, request_id):
    """Chủ trọ hủy quyền thuê của khách hàng đã xác nhận thuê"""
    req = get_object_or_404(RentalRequest, id=request_id)
    if req.post.user != request.user:
        messages.error(request, "Bạn không có quyền thực hiện thao tác này.")
        return redirect('rental_management')
    if req.status == 'confirmed':
        cancel_reason = request.POST.get('cancel_reason', '').strip()
        if not cancel_reason:
            messages.error(request, "Bạn phải nhập lý do hủy phòng.")
            return redirect('rental_management')
        req.cancel_reason = cancel_reason
        req.status = 'cancelled'
        req.cancel_request_status = 'approved'
        req.save(update_fields=['status', 'cancel_reason', 'cancel_request_status'])

        # Mở lại phòng (đánh dấu chưa cho thuê)
        post = req.post
        post.is_rented = False
        post.save(update_fields=['is_rented'])

        # Kiểm tra xem phòng còn hạn không
        now = timezone.now()
        if post.expired_at and post.expired_at <= now:
            messages.success(request, "✅ Đã hủy quyền thuê phòng. Phòng đã được mở lại nhưng đã hết hạn, vui lòng gia hạn để hiển thị trên website.")
        else:
            messages.success(request, "✅ Đã hủy quyền thuê phòng. Phòng đã được mở lại và hiển thị trên website.")
    else:
        messages.error(request, "Chỉ có thể hủy phòng đã xác nhận thuê.")
    return redirect('rental_management')


@login_required
@require_POST
def owner_confirm_cancel(request, request_id):
    """Chủ trọ xác nhận hoặc từ chối yêu cầu hủy của khách hàng"""
    req = get_object_or_404(RentalRequest, id=request_id)
    if req.post.user != request.user:
        messages.error(request, "Bạn không có quyền thực hiện thao tác này.")
        return redirect('rental_management')
    if req.cancel_request_status != 'waiting':
        messages.error(request, "Không có yêu cầu hủy cần xác nhận.")
        return redirect('rental_management')
    action = request.POST.get('action')
    if action == 'approve':
        req.status = 'cancelled'
        req.cancel_request_status = 'approved'
        req.save(update_fields=['status', 'cancel_request_status'])

        # Mở lại phòng (đánh dấu chưa cho thuê)
        post = req.post
        post.is_rented = False
        post.save(update_fields=['is_rented'])

        # Kiểm tra xem phòng còn hạn không
        now = timezone.now()
        if post.expired_at and post.expired_at <= now:
            messages.success(request, "✅ Đã xác nhận hủy phòng. Phòng đã được mở lại nhưng đã hết hạn, vui lòng gia hạn để hiển thị trên website.")
        else:
            messages.success(request, "✅ Đã xác nhận hủy phòng. Phòng đã được mở lại và hiển thị trên website.")
        try:
            notify(user=req.customer, type_='rental_request_status',
                   title='Yêu cầu hủy phòng được chấp nhận',
                   message=f"Chủ trọ đã chấp nhận hủy phòng '{req.post.title}'.",
                   url=reverse('saved_posts'), rental_request=req, post=req.post)
        except Exception:
            pass

    elif action == 'reject':
        req.cancel_request_status = 'rejected'
        req.save(update_fields=['cancel_request_status'])
        messages.success(request, "Đã từ chối yêu cầu hủy phòng của khách hàng.")
        try:
            notify(user=req.customer, type_='rental_request_status',
                   title='Yêu cầu hủy phòng bị từ chối',
                   message=f"Chủ trọ đã từ chối hủy phòng '{req.post.title}'.",
                   url=reverse('saved_posts'), rental_request=req, post=req.post)
        except Exception:
            pass
    else:
        messages.error(request, "Hành động không hợp lệ.")
    return redirect('rental_management')

@login_required
@require_POST
def delete_rental_request(request, request_id):
    """Chủ trọ xóa yêu cầu thuê (chỉ cho những yêu cầu đã hủy hoặc từ chối)"""
    req = get_object_or_404(RentalRequest, id=request_id)
    if req.post.user != request.user:
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền xóa yêu cầu này.'}, status=403)
    if req.status not in ['cancelled', 'declined']:
        return JsonResponse({'status': 'error', 'message': 'Chỉ có thể xóa yêu cầu đã hủy hoặc từ chối.'}, status=400)
    req.delete()
    return JsonResponse({'status': 'ok', 'message': 'Đã xóa yêu cầu thuê.'})

@login_required
@require_POST
def toggle_save_post(request, post_id):
    post = get_object_or_404(RentalPost, id=post_id)
    now = timezone.now()
    # Nếu bài đã hết hạn và đã cho thuê thì không cho lưu
    if post.is_rented and post.expired_at and post.expired_at <= now:
        return JsonResponse({'status': 'forbidden', 'message': 'Bài đăng đã hết hạn và đã cho thuê, không thể lưu.'}, status=403)
    saved, created = SavedPost.objects.get_or_create(user=request.user, post=post)

    # 🔥 TRACKING: Log save/unsave event for analytics
    from goiy_ai.models import UserInteraction
    if not created:
        saved.delete()
        # Track unsave
        UserInteraction.objects.create(
            user=request.user,
            post=post,
            session_id=request.session.session_key or '',
            interaction_type='unsave',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return JsonResponse({'status': 'removed'})
    else:
        # Track save
        UserInteraction.objects.create(
            user=request.user,
            post=post,
            session_id=request.session.session_key or '',
            interaction_type='save',
            ip_address=request.META.get('REMOTE_ADDR')
        )
    return JsonResponse({'status': 'saved'})


@login_required
def chat_thread(request, thread_id):
    """Hiển thị cuộc trò chuyện theo thread_id, đúng cho cả owner và guest"""
    thread = get_object_or_404(
    ChatThread,
    Q(id=thread_id) & (Q(owner=request.user) | Q(guest=request.user))
)

    # Nếu thread cũ bị sai (guest == owner) và người xem là chủ, cố gắng chuyển sang thread đúng
    if request.user == thread.owner and thread.guest == thread.owner:
        replacement = ChatThread.objects.filter(post=thread.post, owner=thread.owner).exclude(guest=thread.owner).order_by('-updated_at').first()
        if replacement:
            return redirect('chat_thread', thread_id=replacement.id)

    # Khi người dùng mở màn hình chat, tự động bỏ ẩn cho phía đó
    unhide = False
    if request.user == thread.owner and thread.hidden_for_owner:
        thread.hidden_for_owner = False
        thread.hidden_for_owner_at = None
        unhide = True
    if request.user == thread.guest and thread.hidden_for_guest:
        thread.hidden_for_guest = False
        thread.hidden_for_guest_at = None
        unhide = True
    if unhide:
        # Save full to ensure updated_at is refreshed
        thread.save()

    # Đánh dấu đã đọc các tin nhắn của đối phương
    thread.messages.filter(is_deleted=False, is_read=False).exclude(sender=request.user).update(is_read=True)

    # Lấy tin nhắn chưa xóa
    messages = thread.messages.filter(is_deleted=False).order_by('created_at')[:50]

    return render(request, 'website/chat_thread.html', {
        'thread': thread,
        'messages': messages,
        'post': thread.post
    })


@login_required
def start_chat(request, post_id):
    """Khách mở chat từ trang bài viết: tạo/lấy thread và chuyển đến chat theo thread_id"""
    post = get_object_or_404(RentalPost, id=post_id)

    # Nếu chủ tự vào từ bài viết, điều hướng về danh sách chat để chọn đúng thread với khách
    if request.user == post.user:
        return redirect('my_chats')

    thread, created = ChatThread.objects.get_or_create(
        post=post,
        owner=post.user,
        guest=request.user,
        defaults={'is_active': True}
    )

    # 🔥 TRACKING: Log contact interaction for analytics (only first time)
    if created:
        from goiy_ai.models import UserInteraction
        UserInteraction.objects.create(
            user=request.user,
            post=post,
            session_id=request.session.session_key or '',
            interaction_type='contact',
            ip_address=request.META.get('REMOTE_ADDR')
        )

    # Mở lại cuộc trò chuyện nếu phía khách đã ẩn trước đó
    changed_fields = []
    if request.user == thread.guest and thread.hidden_for_guest:
        thread.hidden_for_guest = False
        thread.hidden_for_guest_at = None
        changed_fields += ['hidden_for_guest', 'hidden_for_guest_at']
    if request.user == thread.owner and thread.hidden_for_owner:
        thread.hidden_for_owner = False
        thread.hidden_for_owner_at = None
        changed_fields += ['hidden_for_owner', 'hidden_for_owner_at']
    if changed_fields:
        thread.save(update_fields=changed_fields)

    return redirect('chat_thread', thread_id=thread.id)

@login_required
def send_chat_message(request, thread_id):
    """Send chat message with optional image via HTTP POST"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})

    thread = get_object_or_404(
        ChatThread,
        Q(id=thread_id) & (Q(owner=request.user) | Q(guest=request.user))
    )

    # Only owner or guest can send messages
    if request.user != thread.owner and request.user != thread.guest:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'})

    content = request.POST.get('content', '').strip()
    image = request.FILES.get('image')

    # Must have either content or image
    if not content and not image:
        return JsonResponse({'status': 'error', 'message': 'Message cannot be empty'})

    # Unhide thread when new message is sent
    changed_fields = []
    if thread.hidden_for_owner:
        thread.hidden_for_owner = False
        thread.hidden_for_owner_at = None
        changed_fields += ['hidden_for_owner', 'hidden_for_owner_at']
    if thread.hidden_for_guest:
        thread.hidden_for_guest = False
        thread.hidden_for_guest_at = None
        changed_fields += ['hidden_for_guest', 'hidden_for_guest_at']
    if changed_fields:
        thread.save(update_fields=changed_fields)

    # Create message
    message = ChatMessage.objects.create(
        thread=thread,
        sender=request.user,
        content=content,
        image=image
    )

    return JsonResponse({
        'status': 'success',
        'message_id': message.id
    })

@login_required
@require_POST
def delete_message(request, message_id):
    """Thu hồi tin nhắn của chính người gửi"""
    message = get_object_or_404(ChatMessage, id=message_id)
    if message.sender != request.user:
        return JsonResponse({'status': 'error', 'message': 'Không được phép'}, status=403)

    message.is_deleted = True
    message.deleted_at = timezone.now()
    message.save(update_fields=['is_deleted', 'deleted_at'])
    return JsonResponse({'status': 'success'})

@login_required
def my_chats(request):

    # Subqueries for last message content and timestamp
    last_msg_qs = ChatMessage.objects.filter(
        thread=models.OuterRef('pk'),
        is_deleted=False
    ).order_by('-created_at')

    threads = (
        ChatThread.objects.select_related('post', 'owner', 'guest')
        .filter(is_active=True)
        .exclude(owner=models.F('guest'))
        .filter(
            (Q(owner=request.user) & Q(hidden_for_owner=False))
            | (Q(guest=request.user) & Q(hidden_for_guest=False))
        )
        .annotate(
            last_message=models.Subquery(last_msg_qs.values('content')[:1]),
            last_time=models.Subquery(last_msg_qs.values('created_at')[:1]),
            unread_count=models.Count(
                'messages',
                filter=(Q(messages__is_read=False) & ~Q(messages__sender=request.user))
            ),
        )
        .distinct()
        .order_by('-updated_at')
    )

    return render(request, 'website/my_chats.html', {
        'threads': threads
    })


@login_required
@require_POST
def delete_thread(request, thread_id):
    """Ẩn cuộc trò chuyện cho riêng người xóa (bên còn lại vẫn thấy).
    - Nếu là AJAX: trả JSON {status: success}
    - Nếu là form POST bình thường: redirect về trang danh sách chat
    - Trường hợp thread tự-kỷ (owner == guest): ẩn cho cả hai phía
    """
    thread = get_object_or_404(ChatThread, id=thread_id)
    if request.user != thread.owner and request.user != thread.guest:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Không được phép'}, status=403)
        return redirect('my_chats')

    now = timezone.now()
    if thread.owner == thread.guest:
        thread.hidden_for_owner = True
        thread.hidden_for_guest = True
        thread.hidden_for_owner_at = now
        thread.hidden_for_guest_at = now
    elif request.user == thread.owner:
        thread.hidden_for_owner = True
        thread.hidden_for_owner_at = now
    else:
        thread.hidden_for_guest = True
        thread.hidden_for_guest_at = now
    thread.save(update_fields=['hidden_for_owner', 'hidden_for_guest', 'hidden_for_owner_at', 'hidden_for_guest_at'])

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.META.get('HTTP_ACCEPT', ''):
        return JsonResponse({'status': 'success'})
    return redirect('my_chats')

@login_required
@require_POST
def hard_delete_thread(request, thread_id):
    """Xóa vĩnh viễn thread khỏi DB. Chỉ cho phép admin/staff."""
    if not request.user.is_staff:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Chỉ admin mới được phép'}, status=403)
        return redirect('my_chats')

    thread = get_object_or_404(ChatThread, id=thread_id)
    thread.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.META.get('HTTP_ACCEPT', ''):
        return JsonResponse({'status': 'success'})
    return redirect('my_chats')

def article_detail(request, slug):
    article = get_object_or_404(Article, slug=slug, is_published=True)
    # Có thể lấy thêm các bài liên quan hoặc mới nhất
    latest_articles = Article.objects.filter(is_published=True).exclude(id=article.id)[:5]
    suggested_links = SuggestedLink.objects.filter(is_active=True).order_by('order')[:6]
    # Tin thuê phòng mới đăng (đã duyệt, chưa cho thuê)
    recent_posts = RentalPost.objects.filter(is_approved=True, is_rented=False).prefetch_related('images')[:5]
    return render(request, 'website/article_detail.html', {
        'article': article,
        'latest_articles': latest_articles,
        'suggested_links': suggested_links,
        'recent_posts': recent_posts,
    })


# ================= ACCOUNT SETTINGS + OTP =================
@login_required
def select_role(request):
    """Trang chọn role cho user đăng nhập bằng Google lần đầu"""
    # Đảm bảo user có CustomerProfile (nếu chưa có thì tạo)
    if not hasattr(request.user, 'customerprofile'):
        CustomerProfile.objects.create(
            user=request.user,
            role='customer',  # Mặc định là khách hàng
        )

    profile = request.user.customerprofile

    if request.method == 'POST':
        role = request.POST.get('role')
        display_name = request.POST.get('display_name', '').strip()
        phone = request.POST.get('phone', '').strip()

        # Validation
        errors = []
        if not role or role not in ['customer', 'owner']:
            errors.append('Vui lòng chọn vai trò')
        if not display_name:
            errors.append('Vui lòng nhập tên hiển thị')
        if not phone:
            errors.append('Vui lòng nhập số điện thoại')
        elif not phone.isdigit() or len(phone) < 10 or len(phone) > 11:
            errors.append('Số điện thoại phải có 10-11 chữ số')

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            # Lưu thông tin
            profile.role = role
            profile.display_name = display_name
            profile.phone = phone
            profile.save(update_fields=['role', 'display_name', 'phone'])

            # Cập nhật first_name của User để hiển thị tên này ở mọi nơi
            request.user.first_name = display_name
            request.user.save(update_fields=['first_name'])

            messages.success(request, f'Bạn đã chọn vai trò: {"Khách hàng" if role == "customer" else "Chủ trọ"}')
            # Xóa flag và đánh dấu đã hiển thị trang chọn role
            request.session.pop('show_role_selection', None)
            request.session['role_selection_shown'] = True
            request.session.save()
            return redirect('home')

    return render(request, 'website/select_role.html', {
        'current_role': profile.role,
    })


@login_required
def account_settings(request):
    """Trang quản lý tài khoản với xác nhận OTP qua email khi cập nhật."""
    user = request.user
    # Đảm bảo user có CustomerProfile (tự động tạo nếu chưa có)
    if not hasattr(user, 'customerprofile'):
        CustomerProfile.objects.create(
            user=user,
            role='customer',  # Mặc định là khách hàng
        )
    profile = user.customerprofile

    if request.method == 'POST':
        form = AccountProfileForm(request.POST, instance=profile, user=user)
        otp_form = VerifyOTPForm(request.POST)

        if form.is_valid() and otp_form.is_valid():
            code = otp_form.cleaned_data['code']
            purpose = otp_form.cleaned_data['purpose']

            otp = OTPCode.objects.filter(user=user, purpose=purpose, is_used=False).order_by('-created_at').first()
            if not otp or not otp.is_valid(code):
                return render(request, 'website/account_settings.html', {
                    'form': form,
                    'otp_error': 'Mã OTP không hợp lệ hoặc đã hết hạn',
                    'pwd_form': ChangePasswordForm(),
                })

            # Mark OTP used and apply changes
            otp.is_used = True
            otp.save(update_fields=['is_used'])
            form.apply_to_user(user)
            messages.success(request, 'Cập nhật thông tin thành công')
            return redirect('account_settings')
    else:
        form = AccountProfileForm(instance=profile, user=user)

    return render(request, 'website/account_settings.html', {
        'form': form,
        'pwd_form': ChangePasswordForm(),
    })


@login_required
@require_POST
def send_account_otp(request):
    """Tạo OTP và gửi email dùng cho việc cập nhật thông tin tài khoản."""
    user = request.user
    email = request.POST.get('email') or user.email
    if not email:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập email để nhận OTP'}, status=400)

    purpose = request.POST.get('purpose') or 'profile_update'
    otp = OTPCode.create_for_user(user, email, purpose=purpose, ttl_minutes=10)

    subject = 'Mã xác nhận tài khoản'
    message = f"Mã OTP của bạn là: {otp.code}. Mã có hiệu lực trong 10 phút."
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@require_POST
def change_password(request):
    form = ChangePasswordForm(request.POST)
    if not form.is_valid():
        # Trả chi tiết lỗi để dễ debug (validators, thiếu trường, ...)
        return JsonResponse({
            'status': 'error',
            'message': next(iter(form.errors.values()))[0] if form.errors else 'Dữ liệu không hợp lệ',
            'errors': form.errors
        }, status=400)

    user = request.user
    current = form.cleaned_data.get('current_password') or ''
    if not user.check_password(current):
        return JsonResponse({'status': 'error', 'message': 'Mật khẩu hiện tại không đúng'}, status=400)

    # BẮT BUỘC: phải có OTP hợp lệ mới cho đổi mật khẩu
    otp_code = request.POST.get('otp') or ''
    if not otp_code:
        return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập OTP để đổi mật khẩu'}, status=400)
    otp = OTPCode.objects.filter(user=request.user, purpose='account_recovery', is_used=False).order_by('-created_at').first()
    if not otp or not otp.is_valid(otp_code):
        return JsonResponse({'status': 'error', 'message': 'OTP không hợp lệ hoặc đã hết hạn'}, status=400)
    otp.is_used = True
    otp.save(update_fields=['is_used'])

    new_password = form.cleaned_data['new_password']
    user.set_password(new_password)
    user.save(update_fields=['password'])
    login(request, user)
    return JsonResponse({'status': 'ok'})

@login_required
@require_POST
def approve_post(request, post_id):
    """Duyệt tin đăng"""
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Chỉ admin/staff mới được phép'}, status=403)

    post = get_object_or_404(RentalPost, id=post_id)
    post.is_approved = True
    post.approved_at = timezone.now()
    post.approved_by = request.user
    # Sau khi đã duyệt, không còn coi là bài bị AI gắn cờ nữa
    post.ai_flagged = False
    post.ai_checked_at = timezone.now()
    post.save(update_fields=['is_approved', 'approved_at', 'approved_by', 'ai_flagged', 'ai_checked_at'])

    return JsonResponse({'status': 'success', 'message': 'Đã duyệt tin'})

@login_required
@require_POST
def reject_post(request, post_id):
    """Từ chối tin đăng"""
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Chỉ admin/staff mới được phép'}, status=403)

    post = get_object_or_404(RentalPost, id=post_id)

    # Đánh dấu tin bị từ chối
    post.is_approved = False
    post.is_rejected = True
    post.rejected_at = timezone.now()
    post.rejected_by = request.user

    # Lưu lý do từ chối (lấy từ AI reason nếu có)
    if post.ai_reason:
        post.rejection_reason = f"Tin đăng vi phạm: {post.ai_reason}"
    else:
        post.rejection_reason = "Tin đăng không đạt yêu cầu kiểm duyệt"

    # 🧠 ML LEARNING: Cho AI học từ quyết định từ chối
    if post.ai_flagged:  # Chỉ học nếu AI từng cảnh báo tin này
        try:
            from .ai_moderation.content_moderator import ContentModerator
            moderator = ContentModerator()
            moderator.learn_from_decision(post.title, post.description, is_approved=False)
        except Exception as e:
            # Không để lỗi ML làm crash chức năng chính
            print(f"⚠️ ML learning error: {e}")

    # Đã xử lý xong cảnh báo, bỏ gắn cờ để không hiện lại ở AI ALERT
    post.ai_flagged = False
    post.ai_checked_at = timezone.now()

    post.save(update_fields=[
        'is_approved', 'is_rejected', 'rejected_at', 'rejected_by',
        'rejection_reason', 'ai_flagged', 'ai_checked_at'
    ])

    # Gửi thông báo cho người đăng tin
    from .notifications import notify
    from django.urls import reverse
    notify(
        user=post.user,
        type_='post_rejected',
        title='Tin đăng bị từ chối',
        message=f'Tin đăng "{post.title}" đã bị từ chối do vi phạm quy định. Lý do: {post.rejection_reason}',
        url=reverse('manage_rooms') + '?status=pending',
        post=post
    )

    return JsonResponse({'status': 'success', 'message': 'Đã từ chối tin và thông báo cho người đăng'})

@login_required
@require_POST
def mark_all_chats_read(request):
    """Đánh dấu tất cả tin nhắn chưa đọc (của đối phương) là đã đọc cho user hiện tại."""
    # Tìm các thread mà user tham gia
    user = request.user
    user_threads = ChatThread.objects.filter(is_active=True).filter(Q(owner=user) | Q(guest=user))
    # Đánh dấu các tin nhắn trong các thread đó, do đối phương gửi, chưa đọc, chưa xóa
    ChatMessage.objects.filter(
        thread__in=user_threads,
        is_deleted=False,
        is_read=False
    ).exclude(sender=user).update(is_read=True)

    # Điều hướng về danh sách chat
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.META.get('HTTP_ACCEPT', ''):
        return JsonResponse({'status': 'success'})
    return redirect('my_chats')


# ================= WALLET & RECHARGE =================
@login_required
def wallet_view(request):
    """Trang ví tiền của người dùng"""
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    recent_transactions = RechargeTransaction.objects.filter(user=request.user)[:10]

    return render(request, 'website/wallet.html', {
        'wallet': wallet,
        'recent_transactions': recent_transactions,
    })


@login_required
def recharge_view(request):
    """Trang nạp tiền"""
    if request.method == 'POST':
        form = RechargeForm(request.POST)
        if form.is_valid():
            # Tạo mã giao dịch duy nhất
            import uuid
            transaction_id = f"RCH_{uuid.uuid4().hex[:12].upper()}"

            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.transaction_id = transaction_id
            transaction.status = 'pending'
            transaction.save()

            # If user selected MoMo, immediately initiate MoMo flow
            if transaction.payment_method == 'momo':
                success, result = _create_momo_payment(transaction, transaction.amount)
                if success:
                    return redirect(result)
                else:
                    messages.error(request, f'Không thể khởi tạo thanh toán MoMo: {result}')
                    return redirect('recharge_history')
            # If user selected VNPAY, initiate VNPAY flow (build redirect)
            if transaction.payment_method == 'vnpay':
                try:
                    redirect_url = _build_vnpay_redirect(transaction, request)
                    return redirect(redirect_url)
                except Exception as e:
                    messages.error(request, f'Không thể khởi tạo thanh toán VNPay: {e}')
                    return redirect('recharge_history')
            # ZaloPay option removed
            # ZaloPay option removed; other methods will be handled separately

            messages.success(request, f'Đã tạo yêu cầu nạp tiền thành công! Mã giao dịch: {transaction_id}')
            return redirect('recharge_history')
    else:
        form = RechargeForm()

    return render(request, 'website/recharge.html', {'form': form})


@login_required
def recharge_history(request):
    """Lịch sử nạp tiền"""
    # Chỉ lấy giao dịch nạp tiền (amount > 0), loại trừ giao dịch đặt cọc
    transactions = RechargeTransaction.objects.filter(
        user=request.user,
        amount__gt=0
    ).exclude(
        description__icontains='đặt cọc'
    )

    # Thống kê
    completed_count = transactions.filter(status='completed').count()
    pending_count = transactions.filter(status='pending').count()

    paginator = Paginator(transactions, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'website/recharge_history.html', {
        'page_obj': page_obj,
        'completed_count': completed_count,
        'pending_count': pending_count,
    })


@login_required
def recharge_transaction_detail(request, transaction_id):
    """Chi tiết giao dịch nạp tiền"""
    import json
    transaction = get_object_or_404(RechargeTransaction, transaction_id=transaction_id, user=request.user)

    # Format raw_response to pretty JSON
    formatted_response = None
    if transaction.raw_response:
        try:
            formatted_response = json.dumps(transaction.raw_response, indent=2, ensure_ascii=False)
        except:
            formatted_response = str(transaction.raw_response)

    return render(request, 'website/recharge_transaction_detail.html', {
        'transaction': transaction,
        'formatted_response': formatted_response,
    })


@login_required
def payment_history(request):
    """Lịch sử thanh toán (chi tiêu)"""
    transactions = RechargeTransaction.objects.filter(user=request.user, amount__lt=0)

    paginator = Paginator(transactions, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'website/payment_history.html', {
        'page_obj': page_obj,
    })


@login_required
def payment_transaction_detail(request, transaction_id):
    """Chi tiết giao dịch thanh toán"""
    import json
    transaction = get_object_or_404(RechargeTransaction, transaction_id=transaction_id, user=request.user)

    return render(request, 'website/payment_transaction_detail.html', {
        'transaction': transaction,
    })


@login_required
def income_history(request):
    """Lịch sử nhận tiền (cộng vào ví)"""
    # CHỈ lấy các khoản NHẬN TIỀN từ khách (đặt cọc, thanh toán,...)
    # KHÔNG lấy các khoản nạp tiền của chính user
    # Filter: transaction_id bắt đầu bằng "INC_" (income)
    transactions = RechargeTransaction.objects.filter(
        user=request.user,
        amount__gt=0,
        transaction_id__startswith='INC_'  # Chỉ lấy income từ khách
    )

    paginator = Paginator(transactions, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'website/income_history.html', {
        'page_obj': page_obj,
    })


@login_required
def income_transaction_detail(request, transaction_id):
    """Chi tiết giao dịch nhận tiền"""
    import json
    transaction = get_object_or_404(RechargeTransaction, transaction_id=transaction_id, user=request.user)

    return render(request, 'website/income_transaction_detail.html', {
        'transaction': transaction,
    })


@login_required
def get_wallet_balance(request):
    """API trả về số dư ví (dùng cho AJAX)"""
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    return JsonResponse({
        'balance': float(wallet.balance),
        'formatted_balance': f"{wallet.balance:,} VNĐ"
    })
def bang_gia_dich_vu(request):
    from .models import VIPPackageConfig
    packages = VIPPackageConfig.objects.filter(is_active=True).order_by('plan')
    return render(request, "website/banggia.html", {'packages': packages})


@login_required
def subscribe_vip(request):
    # Chỉ chủ nhà (owner) mới được đăng ký gói VIP
    try:
        role = request.user.customerprofile.role
    except Exception:
        role = None
    if role != 'owner':
        messages.error(request, 'Tài khoản của bạn là tài khoản khách thuê, không thể đăng ký gói dịch vụ. Vui lòng đăng ký tài khoản chủ cho thuê để sử dụng dịch vụ này.')
        return redirect('bang_gia_dich_vu')

    # Nếu là GET request, chuyển đến trang bảng giá
    if request.method == 'GET':
        return redirect('bang_gia_dich_vu')

    # Xử lý POST request
    plan = request.POST.get('plan')  # vip1/vip2/vip3
    if plan not in dict(VIPSubscription.PLAN_CHOICES):
        messages.error(request, 'Gói VIP không hợp lệ')
        return redirect('bang_gia_dich_vu')

    # Lấy thông tin gói VIP từ database
    from .models import VIPPackageConfig
    try:
        vip_config = VIPPackageConfig.objects.get(plan=plan, is_active=True)
    except VIPPackageConfig.DoesNotExist:
        messages.error(request, 'Gói VIP không tồn tại hoặc đã bị vô hiệu hóa')
        return redirect('bang_gia_dich_vu')

    # Nếu đã có VIP còn hạn, kiểm tra xem có phải request từ AJAX không
    current_vip = VIPSubscription.objects.filter(user=request.user, expires_at__gte=timezone.now()).order_by('-expires_at').first()
    if current_vip and not request.POST.get('confirm'):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        remaining = current_vip.expires_at - timezone.now()
        remaining_hours = int(remaining.total_seconds() // 3600)
        remaining_days = remaining.days

        # Nếu là AJAX request (có header X-Check-VIP), trả về JSON
        if request.headers.get('X-Check-VIP') == 'true':
            from django.utils.dateformat import format as date_format
            return JsonResponse({
                'has_active_vip': True,
                'current_vip': {
                    'name': current_vip.get_plan_display(),
                    'expires_at': date_format(current_vip.expires_at, 'd/m/Y H:i'),
                    'remaining': f'còn {remaining_days} ngày ~ {remaining_hours} giờ',
                    'badge_color': current_vip.badge_color,
                },
                'wallet_balance': int(wallet.balance),
                'new_plan_price': int(vip_config.price),
            })

        # Nếu không phải AJAX, render trang xác nhận (fallback cho trình duyệt cũ)
        return render(request, 'website/confirm_vip_change.html', {
            'current_vip': current_vip,
            'new_plan': plan,
            'new_plan_price': int(vip_config.price),
            'wallet_balance': int(wallet.balance),
            'remaining_days': remaining_days,
            'remaining_hours': remaining_hours,
        })

    # Nếu không có VIP hiện tại và là AJAX request, trả về JSON
    if request.headers.get('X-Check-VIP') == 'true':
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        return JsonResponse({
            'has_active_vip': False,
            'wallet_balance': int(wallet.balance),
        })

    price = int(vip_config.price)
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    if wallet.balance < price:
        messages.error(request, 'Số dư ví không đủ. Vui lòng nạp tiền trước khi đăng ký VIP.')
        return redirect('recharge')

    # Trừ tiền
    if not wallet.subtract_balance(price):
        messages.error(request, 'Không thể trừ tiền từ ví. Vui lòng thử lại.')
        return redirect('bang_gia_dich_vu')

    # Ghi lịch sử chi tiêu
    RechargeTransaction.create_spending(
        user=request.user,
        amount=price,
        description=f"Đăng ký {vip_config.name}"
    )

    # Nếu người dùng xác nhận đổi gói, kết thúc gói cũ ngay
    if current_vip and request.POST.get('confirm'):
        current_vip.expires_at = timezone.now()
        current_vip.save(update_fields=['expires_at'])

    # Kích hoạt VIP theo thời lượng gói từ database
    duration_days = vip_config.expire_days
    new_vip = VIPSubscription.create_or_renew(request.user, plan, duration_days=duration_days)

    messages.success(request, 'Đăng ký VIP thành công!')
    return redirect('bang_gia_dich_vu')





# ================= MoMo integration (sandbox) =================
import uuid, hmac, hashlib, json, time
import requests
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.http import JsonResponse


@login_required
def initiate_momo_payment(request):
    """Tạo yêu cầu thanh toán MoMo (sandbox)."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

    # Support quick MoMo form which only sends 'amount', or full RechargeForm posts.
    amount = None
    from decimal import Decimal, InvalidOperation
    if 'amount' in request.POST and not request.POST.get('payment_method'):
        # Quick path from JS button: only amount provided
        amount_str = request.POST.get('amount')
        try:
            amount = Decimal(amount_str)
        except (InvalidOperation, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Số tiền không hợp lệ'}, status=400)

        # Create a minimal RechargeTransaction for momo
        transaction = RechargeTransaction.objects.create(
            user=request.user,
            amount=amount,
            payment_method='momo',
            status='pending',
            transaction_id=f"RCH_{uuid.uuid4().hex[:12].upper()}"
        )
    else:
        # Full form path
        form = RechargeForm(request.POST)
        if not form.is_valid():
            return JsonResponse({'status': 'error', 'message': 'Dữ liệu không hợp lệ', 'errors': form.errors}, status=400)
        amount = form.cleaned_data['amount']
        transaction = form.save(commit=False)
        transaction.user = request.user
        transaction.payment_method = 'momo'
        transaction.status = 'pending'
        transaction.transaction_id = f"RCH_{uuid.uuid4().hex[:12].upper()}"
        transaction.save()

    # Use helper to create MoMo payment and redirect
    success, result = _create_momo_payment(transaction, amount)
    if success:
        return redirect(result)
    return JsonResponse({'status': 'error', 'message': 'Không lấy được payUrl', 'detail': result}, status=400)


@csrf_exempt
def momo_notify(request):
    """Webhook endpoint MoMo gọi về (IPN)."""
    try:
        payload = json.loads(request.body)
    except Exception:
        return HttpResponse(status=400)

    # Verify signature according to MoMo docs (sandbox may include 'signature' field)
    secretKey = getattr(settings, 'MOMO_SECRET_KEY', '')
    provided_sig = payload.get('signature') or request.META.get('HTTP_X_SIGNATURE', '')
    # For simplicity, verify by recomputing HMAC on canonical string if present in payload
    # NOTE: In production, follow MoMo doc exactly.
    try:
        # Recreate raw signature string if payload contains fields used in creation
        orderId = payload.get('orderId') or payload.get('orderID') or ''
        amount = payload.get('amount') or ''
        message = payload.get('message', '')
        raw = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        computed = hmac.new(secretKey.encode('utf-8'), raw, hashlib.sha256).hexdigest()
    except Exception:
        computed = ''

    # If signature provided and doesn't match, reject
    if provided_sig and provided_sig != computed:
        return HttpResponse(status=403)

    # Find transaction and update
    tx_id = payload.get('orderId') or payload.get('orderID') or ''
    try:
        tx = RechargeTransaction.objects.get(transaction_id=tx_id)
    except RechargeTransaction.DoesNotExist:
        return HttpResponse(status=404)

    tx.raw_response = payload
    result_code = int(payload.get('resultCode', -1))
    if result_code == 0:
        if tx.status != 'completed':
            tx.status = 'completed'
            tx.completed_at = timezone.now()
            tx.save(update_fields=['status', 'completed_at', 'raw_response'])
            # Add balance to wallet
            wallet, _ = Wallet.objects.get_or_create(user=tx.user)
            wallet.add_balance(int(tx.amount))
    else:
        tx.status = 'failed'
        tx.save(update_fields=['status', 'raw_response'])

    return JsonResponse({'message': 'ok'})


def _create_momo_payment(transaction, amount):
    """Helper: build and call MoMo create API for given RechargeTransaction.
    Returns (True, payUrl) on success, or (False, response_or_error) on failure.
    """
    partnerCode = getattr(settings, 'MOMO_PARTNER_CODE', '')
    accessKey = getattr(settings, 'MOMO_ACCESS_KEY', '')
    secretKey = getattr(settings, 'MOMO_SECRET_KEY', '')
    endPoint = getattr(settings, 'MOMO_ENDPOINT', 'https://test-payment.momo.vn/v2/gateway/api/create')
    ipnUrl = getattr(settings, 'MOMO_NOTIFY_URL', settings.SITE_URL + '/payments/momo/notify/')
    redirectUrl = getattr(settings, 'MOMO_RETURN_URL', settings.SITE_URL + '/payments/momo/return/')

    orderId = transaction.transaction_id
    requestId = orderId
    orderInfo = f"Nap tien {transaction.user.username} - {orderId}"
    extraData = ""
    requestType = 'captureWallet'

    raw_signature = f"accessKey={accessKey}&amount={int(amount)}&extraData={extraData}&ipnUrl={ipnUrl}&orderId={orderId}&orderInfo={orderInfo}&partnerCode={partnerCode}&redirectUrl={redirectUrl}&requestId={requestId}&requestType={requestType}"
    signature = hmac.new(secretKey.encode('utf-8'), raw_signature.encode('utf-8'), hashlib.sha256).hexdigest()

    payload = {
        'partnerCode': partnerCode,
        'accessKey': accessKey,
        'requestId': requestId,
        'amount': str(int(amount)),
        'orderId': orderId,
        'orderInfo': orderInfo,
        'redirectUrl': redirectUrl,
        'ipnUrl': ipnUrl,
        'lang': 'vi',
        'extraData': extraData,
        'requestType': requestType,
        'signature': signature,
    }

    try:
        resp = requests.post(endPoint, json=payload, timeout=10)
        data = resp.json()
    except Exception as e:
        transaction.raw_response = {'error': str(e)}
        transaction.save(update_fields=['raw_response'])
        return False, str(e)

    transaction.raw_response = data
    transaction.momo_order_id = data.get('orderId') or orderId
    transaction.save(update_fields=['raw_response', 'momo_order_id'])

    payUrl = data.get('payUrl') or data.get('checkoutUrl')
    if payUrl:
        return True, payUrl
    return False, data

def momo_return(request):
    """Return URL user is redirected to after completing payment on MoMo UI.
    MoMo sends query params; update transaction state if needed and redirect user to recharge history with message.
    """
    params = request.GET.dict()
    order_id = params.get('orderId') or params.get('orderID')
    result_code = params.get('resultCode')
    message_text = params.get('message') or ''

    if not order_id:
        messages.error(request, 'Thiếu thông tin giao dịch từ cổng thanh toán')
        return redirect('recharge_history')

    try:
        tx = RechargeTransaction.objects.get(transaction_id=order_id)
    except RechargeTransaction.DoesNotExist:
        messages.error(request, f'Giao dịch {order_id} không tìm thấy')
        return redirect('recharge_history')

    # Save raw GET params for reference
    tx.raw_response = params

    # If IPN already processed this, status may be completed. Only update if pending.
    try:
        rc = int(result_code) if result_code is not None else None
    except ValueError:
        rc = None

    if rc == 0 and tx.status != 'completed':
        tx.status = 'completed'
        tx.completed_at = timezone.now()
        tx.save(update_fields=['status', 'completed_at', 'raw_response'])
        wallet, _ = Wallet.objects.get_or_create(user=tx.user)
        wallet.add_balance(int(tx.amount))
        messages.success(request, f'Nạp tiền thành công: {tx.amount:,} VNĐ')
    else:
        # If not success, mark failed if pending
        if rc is not None and tx.status == 'pending' and rc != 0:
            tx.status = 'failed'
            tx.save(update_fields=['status', 'raw_response'])
        # Provide user-facing message
        if rc == 0:
            messages.success(request, message_text or 'Giao dịch có vẻ đã thành công')
        else:
            messages.error(request, message_text or 'Thanh toán không thành công')

    return redirect('recharge_history')
# ================= VNPay integration (sandbox) =================


from urllib.parse import urlencode
import hmac, hashlib, urllib
from decimal import Decimal
from datetime import timedelta
import datetime, json
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import RechargeTransaction, Wallet
import uuid
import pytz
import time


def initiate_vnpay_payment(request):
    """
    Tạo URL thanh toán VNPay sandbox
    """
    vnp_TmnCode = settings.VNPAY_TMN_CODE
    vnp_HashSecret = settings.VNPAY_HASH_SECRET
    vnp_Url = settings.VNPAY_PAYMENT_URL
    vnp_ReturnUrl = settings.VNPAY_RETURN_URL

    txn_ref = f"RCH_{uuid.uuid4().hex[:12].upper()}"
    amount = 10000  # test với 10,000 VND
    # VNPay expects local Vietnam time (Asia/Ho_Chi_Minh)
    vn_tz = pytz.timezone(getattr(settings, 'TIME_ZONE', 'Asia/Ho_Chi_Minh'))
    now_vn = timezone.localtime(timezone.now(), vn_tz)
    create_date = now_vn.strftime("%Y%m%d%H%M%S")
    expire_date = (now_vn + datetime.timedelta(minutes=60)).strftime("%Y%m%d%H%M%S")

    inputData = {
        "vnp_Version": "2.1.0",
        "vnp_Command": "pay",
        "vnp_TmnCode": vnp_TmnCode,
        "vnp_Amount": str(amount * 100),  # nhân 100 theo yêu cầu VNPay
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": txn_ref,
        "vnp_OrderType": "other",
        "vnp_Locale": "vn",
        "vnp_ReturnUrl": vnp_ReturnUrl,
        "vnp_IpAddr": request.META.get("REMOTE_ADDR", "127.0.0.1"),
        "vnp_CreateDate": create_date,
        "vnp_ExpireDate": expire_date,
    }

    # Sắp xếp theo key
    sortedData = sorted(inputData.items())
    queryString = urllib.parse.urlencode(sortedData)
    # VNPay expects URL-encoded key=value pairs in the signed string
    hashData = urllib.parse.urlencode(sortedData)

    # HMAC SHA512
    secureHash = hmac.new(
        vnp_HashSecret.encode("utf-8"),
        hashData.encode("utf-8"),
        hashlib.sha512
    ).hexdigest()

    paymentUrl = f"{vnp_Url}?{queryString}&vnp_SecureHash={secureHash}"

    return JsonResponse({
        "txn_ref": txn_ref,
        "redirect_url": paymentUrl,
        "sign_raw": hashData,
        "computed_hash": secureHash
    })


def _build_vnpay_redirect(transaction, request):
    """Tạo URL redirect sang VNPay với đầy đủ params + chữ ký SHA512."""
    base_url = getattr(settings, 'VNPAY_CREATE_URL')
    hash_secret = (getattr(settings, 'VNPAY_HASH_SECRET') or '').strip()

    vn_tz = pytz.timezone(getattr(settings, 'TIME_ZONE', 'Asia/Ho_Chi_Minh'))
    now_vn = timezone.localtime(timezone.now(), vn_tz)
    # try to capture real client IP (fallback to REMOTE_ADDR)
    xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
    client_ip = xff or request.META.get('REMOTE_ADDR', '') or '127.0.0.1'
    vnp_params = {
        'vnp_Version': '2.1.0',
        'vnp_Command': 'pay',
        'vnp_TmnCode': getattr(settings, 'VNPAY_TMN_CODE'),
        'vnp_Amount': str(int(Decimal(transaction.amount) * 100)),
        'vnp_CurrCode': 'VND',
        'vnp_TxnRef': transaction.transaction_id,
        'vnp_OrderInfo': transaction.transaction_id,
        'vnp_OrderType': 'other',
        'vnp_ReturnUrl': getattr(settings, 'VNPAY_RETURN_URL'),
        'vnp_IpAddr': client_ip,
        'vnp_CreateDate': now_vn.strftime('%Y%m%d%H%M%S'),
        'vnp_ExpireDate': (now_vn + timedelta(minutes=60)).strftime('%Y%m%d%H%M%S'),
        'vnp_Locale': 'vn',
        'vnp_SecureHashType': 'HmacSHA512',
    }

    # Build signature over params EXCLUDING vnp_SecureHash and vnp_SecureHashType
    sign_items = sorted([(k, v) for k, v in vnp_params.items() if k not in ['vnp_SecureHash', 'vnp_SecureHashType']])
    # VNPay expects URL-encoded key=value pairs in the signed string
    sign_data = urllib.parse.urlencode(sign_items)

    secure_hash = hmac.new(
        hash_secret.encode('utf-8'),
        sign_data.encode('utf-8'),
        hashlib.sha512
    ).hexdigest()

    # Attach hash type and signature after computing
    vnp_params['vnp_SecureHashType'] = 'HmacSHA512'
    vnp_params['vnp_SecureHash'] = secure_hash

    transaction.raw_response = {
        '_request': vnp_params.copy(),
        'debug': {
            'sign_data': sign_data,
            'computed_hash': secure_hash,
        }
    }
    transaction.save(update_fields=['raw_response'])

    return f"{base_url}?{urlencode(vnp_params)}"


@csrf_exempt
def vnpay_notify(request):
    """VNPay gọi IPN để xác nhận giao dịch."""
    params = request.GET.dict() if request.method == 'GET' else request.POST.dict()
    if not params:
        try:
            params = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            params = {}

    provided_hash = params.pop('vnp_SecureHash', '')
    params.pop('vnp_SecureHashType', None)

    sorted_items = sorted(params.items())
    sign_data = '&'.join([f"{k}={v}" for k, v in sorted_items])

    hash_secret = (getattr(settings, 'VNPAY_HASH_SECRET') or '').strip()
    calc_hash = hmac.new(
        hash_secret.encode('utf-8'),
        sign_data.encode('utf-8'),
        hashlib.sha512
    ).hexdigest()

    order_ref = params.get('vnp_TxnRef') or params.get('vnp_OrderInfo')
    if not order_ref:
        return HttpResponse('VNPAY_NO_ORDER', status=400)

    try:
        tx = RechargeTransaction.objects.get(transaction_id=order_ref)
    except RechargeTransaction.DoesNotExist:
        return HttpResponse('VNPAY_ORDER_NOT_FOUND', status=404)

    # Lưu log IPN
    existing = tx.raw_response or {}
    existing.setdefault('ipn', {})
    existing['ipn'].update({
        'received_params': params.copy(),
        'sign_data': sign_data,
        'computed_hash': calc_hash,
        'provided_hash': provided_hash,
    })
    tx.raw_response = existing
    tx.save(update_fields=['raw_response'])

    if calc_hash.lower() != (provided_hash or '').lower():
        return HttpResponse('VNPAY_INVALID_SIGNATURE', status=400)

    if params.get('vnp_ResponseCode') == '00':
        if tx.status != 'completed':
            tx.status = 'completed'
            tx.completed_at = timezone.now()
            tx.save(update_fields=['status', 'completed_at', 'raw_response'])
            wallet, _ = Wallet.objects.get_or_create(user=tx.user)
            wallet.add_balance(int(tx.amount))
        return HttpResponse('OK')
    else:
        tx.status = 'failed'
        tx.save(update_fields=['status', 'raw_response'])
        return HttpResponse('FAILED')


@login_required
def vnpay_diag(request):
    """API debug: so sánh computed hash với VNPay hash."""
    tx = RechargeTransaction.objects.filter(payment_method='vnpay').order_by('-created_at').first()
    if not tx:
        return JsonResponse({'error': 'No vnpay transaction found'})

    req = (tx.raw_response or {}).get('_request') or {}
    if not req:
        return JsonResponse({'error': 'Transaction has no _request saved', 'tx_id': tx.transaction_id})

    items_sorted = sorted([(k, v) for k, v in req.items() if k not in ['vnp_SecureHash', 'vnp_SecureHashType']])
    sign_raw = '&'.join([f"{k}={v}" for k, v in items_sorted])

    hash_secret = getattr(settings, 'VNPAY_HASH_SECRET')
    computed_hash = hmac.new(
        hash_secret.encode("utf-8"),
        sign_raw.encode("utf-8"),
        hashlib.sha512
    ).hexdigest()

    redirect_url = getattr(settings, 'VNPAY_CREATE_URL') + '?' + urlencode(req)

    return JsonResponse({
        'tx_id': tx.transaction_id,
        'sign_raw': sign_raw,
        'computed_hash': computed_hash,
        'provided_hash': req.get('vnp_SecureHash'),
        'redirect_url': redirect_url,
        '_request': req,
    })


def vnpay_return(request):
    """User quay lại từ VNPay (dùng để hiện message, kết quả chuẩn xác dựa IPN)."""
    params = request.GET.dict()
    order_ref = params.get('vnp_TxnRef') or params.get('vnp_OrderInfo')

    if not order_ref:
        messages.error(request, 'Thiếu thông tin giao dịch VNPAY')
        return redirect('recharge_history')

    try:
        tx = RechargeTransaction.objects.get(transaction_id=order_ref)
    except RechargeTransaction.DoesNotExist:
        messages.error(request, f'Giao dịch {order_ref} không tìm thấy')
        return redirect('recharge_history')

    # Fallback credit on return page (useful on localhost when IPN cannot reach)
    try:
        provided_hash = params.pop('vnp_SecureHash', '')
        params.pop('vnp_SecureHashType', None)
        sign_items = sorted(params.items())
        sign_raw = urllib.parse.urlencode(sign_items)
        hash_secret = (getattr(settings, 'VNPAY_HASH_SECRET') or '').strip()
        computed = hmac.new(hash_secret.encode('utf-8'), sign_raw.encode('utf-8'), hashlib.sha512).hexdigest()
        is_valid = computed.lower() == (provided_hash or '').lower()
    except Exception:
        is_valid = False

    if params.get('vnp_ResponseCode') == '00' and is_valid:
        if tx.status != 'completed':
            tx.status = 'completed'
            tx.completed_at = timezone.now()
            tx.save(update_fields=['status', 'completed_at'])
            wallet, _ = Wallet.objects.get_or_create(user=tx.user)
            wallet.add_balance(int(tx.amount))
        messages.success(request, 'Thanh toán VNPay thành công')
    else:
        # Keep pending to wait IPN if invalid or failed
        messages.error(request, 'Giao dịch VNPAY không thành công hoặc sai chữ ký')

    return redirect('recharge_history')

from django.views.decorators.http import require_POST
from .models import RentalRequest, RentalPost
from .models import ChatThread, ChatMessage, Wallet, RechargeTransaction

@login_required
@require_POST
def send_rental_request(request, post_id):
    post = get_object_or_404(RentalPost, id=post_id)
    # Chỉ khách hàng mới được gửi yêu cầu
    if not hasattr(request.user, 'customerprofile') or not request.user.customerprofile.is_customer():
        return redirect('saved_posts')
    # Kiểm tra yêu cầu gần nhất
    last_request = RentalRequest.objects.filter(customer=request.user, post=post).order_by('-created_at').first()
    if last_request:
        if last_request.status in ['pending', 'accepted', 'confirmed']:
            return redirect('saved_posts')
        # Nếu bị hủy hoặc từ chối thì cho gửi lại
    req = RentalRequest.objects.create(customer=request.user, post=post, status='pending')

    # 🔥 TRACKING: Log rental request for analytics
    from goiy_ai.models import UserInteraction
    UserInteraction.objects.create(
        user=request.user,
        post=post,
        session_id=request.session.session_key or '',
        interaction_type='request',
        ip_address=request.META.get('REMOTE_ADDR')
    )
    # Notify owner về yêu cầu thuê mới
    try:
        notify(
            user=post.user,
            type_='rental_request_new',
            title='Yêu cầu thuê mới',
            message=f"{request.user.username} đã gửi yêu cầu thuê phòng '{post.title}'.",
            url=reverse('rental_management'),
            rental_request=req,
            post=post,
        )
    except Exception:
        pass
    return redirect('saved_posts')

@login_required
@require_POST
def confirm_rental_request(request, request_id):
    req = get_object_or_404(RentalRequest, id=request_id, customer=request.user)
    if req.status == 'accepted':
        req.status = 'confirmed'
        req.save(update_fields=['status'])

        # Tự động đánh dấu phòng đã cho thuê
        post = req.post
        post.is_rented = True
        post.save(update_fields=['is_rented'])

        messages.success(request, "✅ Bạn đã xác nhận thuê phòng. Phòng này đã được đánh dấu là đã cho thuê.")
        # Notify both sides
        try:
            notify(user=req.post.user, type_='rental_confirmed',
                   title='Khách đã xác nhận thuê',
                   message=f"{request.user.username} đã xác nhận thuê phòng '{post.title}'.",
                   url=reverse('rental_management'), rental_request=req, post=post)
            notify(user=request.user, type_='rental_confirmed',
                   title='Bạn đã xác nhận thuê phòng',
                   message=f"Phòng '{post.title}' đã được đánh dấu đã thuê.",
                   url=reverse('my_rooms'), rental_request=req, post=post)
        except Exception:
            pass
        # Sau khi xác nhận, chuyển sang trang đánh giá chủ trọ
        return redirect('submit_landlord_review', request_id=req.id)
    return redirect('saved_posts')


# ====== Landlord Reviews ======
from .models import LandlordReview
from .forms import LandlordReviewForm

@login_required
def submit_landlord_review(request, request_id):
    """Trang/biểu mẫu để khách hàng đánh giá chủ trọ sau khi đã xác nhận thuê."""
    rr = get_object_or_404(RentalRequest, id=request_id, customer=request.user)
    if rr.status != 'confirmed':
        messages.info(request, "Bạn chỉ có thể đánh giá sau khi đã xác nhận thuê.")
        return redirect('saved_posts')

    # Nếu đã có review thì quay về my_rooms
    if hasattr(rr, 'landlord_review'):
        messages.info(request, "Bạn đã gửi đánh giá cho yêu cầu này.")
        return redirect('my_rooms')

    # Chỉ chấp nhận POST request (từ modal), không cho truy cập trực tiếp
    if request.method != 'POST':
        messages.info(request, "Vui lòng đánh giá từ trang 'Phòng của tôi'.")
        return redirect('my_rooms')

    if request.method == 'POST':
        form = LandlordReviewForm(request.POST)
        if form.is_valid():
            review: LandlordReview = form.save(commit=False)
            review.rental_request = rr
            review.landlord = rr.post.user
            review.reviewer = request.user
            review.save()
            # Notify landlord về đánh giá mới
            try:
                notify(user=review.landlord, type_='review_received',
                       title='Bạn nhận được đánh giá mới',
                       message=f"{request.user.username} đã đánh giá bạn {review.rating}/5 sao.",
                       url=reverse('landlord_reviews', args=[review.landlord.id]),
                       rental_request=rr, post=rr.post)
            except Exception:
                pass
            messages.success(request, "Cảm ơn bạn đã đánh giá chủ trọ!")
            return redirect('my_rooms')
        else:
            messages.error(request, "Vui lòng chọn số sao và nhập nhận xét.")
            return redirect('my_rooms')


def landlord_reviews(request, user_id):
    """Danh sách đánh giá cho một chủ trọ"""
    from django.contrib.auth.models import User
    landlord = get_object_or_404(User, id=user_id)
    reviews = LandlordReview.objects.filter(landlord=landlord, is_approved=True).select_related('reviewer', 'rental_request').order_by('-created_at')
    # Tính trung bình
    from django.db.models import Avg, Count
    summary = reviews.aggregate(avg=Avg('rating'), total=Count('id'))
    avg = round(summary['avg'] or 0, 1)
    total = summary['total'] or 0
    return render(request, 'website/landlord_reviews.html', {
        'landlord': landlord,
        'reviews': reviews,
        'avg': avg,
        'total': total,
        'can_delete_reviews': request.user.is_authenticated and (request.user == landlord or request.user.is_staff),
    })


@login_required
@require_POST
def delete_landlord_review(request, review_id):
    """Xóa một đánh giá. Chỉ landlord của đánh giá hoặc staff được phép.
    Trả về JSON để dùng với AJAX."""
    review = get_object_or_404(LandlordReview, id=review_id)
    if not (request.user == review.landlord or request.user.is_staff):
        return JsonResponse({'status': 'error', 'message': 'Không có quyền xóa đánh giá này.'}, status=403)
    review.delete()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def accept_rental_request(request, request_id):
    rental_request = get_object_or_404(RentalRequest, id=request_id)
    # Chỉ chủ trọ của bài đăng mới được chấp nhận
    if rental_request.post.user != request.user:
        messages.error(request, "Bạn không có quyền thực hiện thao tác này.")
        return redirect('rental_management')
    if rental_request.status != 'pending':
        messages.info(request, "Yêu cầu đã được xử lý.")
        return redirect('rental_management')
    rental_request.status = 'accepted'
    rental_request.save(update_fields=['status'])
    # Notify customer: accepted
    try:
        notify(user=rental_request.customer, type_='rental_request_status',
               title='Yêu cầu thuê đã được chấp nhận',
               message=f"Chủ trọ đã chấp nhận yêu cầu thuê phòng '{rental_request.post.title}'.",
               url=reverse('saved_posts'), rental_request=rental_request, post=rental_request.post)
    except Exception:
        pass
    messages.success(request, "Đã chấp nhận yêu cầu thuê phòng.")
    return redirect('rental_management')

@login_required
@require_POST
def decline_rental_request(request, request_id):
    rental_request = get_object_or_404(RentalRequest, id=request_id)
    # Chỉ chủ trọ của bài đăng mới được từ chối
    if rental_request.post.user != request.user:
        messages.error(request, "Bạn không có quyền thực hiện thao tác này.")
        return redirect('rental_management')
    if rental_request.status != 'pending':
        messages.info(request, "Yêu cầu đã được xử lý.")
        return redirect('rental_management')
    rental_request.status = 'declined'
    rental_request.save(update_fields=['status'])
    # Notify customer: declined
    try:
        notify(user=rental_request.customer, type_='rental_request_status',
               title='Yêu cầu thuê bị từ chối',
               message=f"Chủ trọ đã từ chối yêu cầu thuê phòng '{rental_request.post.title}'.",
               url=reverse('saved_posts'), rental_request=rental_request, post=rental_request.post)
    except Exception:
        pass
    messages.success(request, "Đã từ chối yêu cầu thuê phòng.")
    return redirect('rental_management')


# ====== Deposit workflow ======
@login_required
@require_POST
def owner_request_deposit(request, request_id):
    """Chủ trọ yêu cầu đặt cọc - Tạo QR MoMo ngay lập tức"""
    rr = get_object_or_404(RentalRequest, id=request_id)
    if rr.post.user != request.user:
        messages.error(request, "Bạn không có quyền thực hiện thao tác này.")
        return redirect('rental_management')
    if rr.status not in ['pending', 'accepted']:
        messages.info(request, "Yêu cầu không ở trạng thái phù hợp để yêu cầu đặt cọc.")
        return redirect('rental_management')
    try:
        amount = int(str(request.POST.get('deposit_amount', '0')).replace('.', '').replace(',', ''))
    except Exception:
        amount = 0
    if amount <= 0:
        messages.error(request, "Số tiền đặt cọc không hợp lệ.")
        return redirect('rental_management')

    # Tạo transaction ID unique
    import uuid
    tx_id = f"DEPOSIT_{request_id}_{uuid.uuid4().hex[:8]}"

    # Tạo RechargeTransaction để track việc nạp tiền
    tx = RechargeTransaction.objects.create(
        user=rr.customer,
        amount=amount,
        payment_method='momo',
        transaction_id=tx_id,
        status='pending',
        description=f"Nạp tiền để đặt cọc phòng: {rr.post.title}"
    )

    # Tạo MoMo payment URL
    success, result = _create_deposit_momo_payment(tx, amount, rr)

    if not success:
        messages.error(request, f"Lỗi tạo thanh toán MoMo: {result}")
        tx.delete()
        return redirect('manage_rooms')

    # result is payUrl from MoMo
    payment_url = result

    # Lưu trạng thái deposit
    rr.deposit_status = 'requested'
    rr.deposit_amount = amount
    rr.deposit_requested_at = timezone.now()
    rr.deposit_transaction_id = tx_id
    rr.deposit_payment_method = 'momo'
    rr.deposit_payment_url = payment_url  # Lưu QR link
    rr.save(update_fields=['deposit_status', 'deposit_amount', 'deposit_requested_at',
                           'deposit_transaction_id', 'deposit_payment_method', 'deposit_payment_url'])

    # Gửi QR link cho khách qua chat
    thread, _ = ChatThread.objects.get_or_create(post=rr.post, guest=rr.customer, owner=rr.post.user)
    ChatMessage.objects.create(
        thread=thread,
        sender=request.user,
        content=f"💰 Yêu cầu đặt cọc {amount:,} VNĐ cho phòng '{rr.post.title}'\n\n"
                f"📱 Vui lòng quét mã QR để thanh toán:\n{payment_url}\n\n"
                f"⚠️ Sau khi thanh toán, {amount:,} VNĐ sẽ được trừ từ ví của bạn và chuyển cho chủ trọ."
    )

    messages.success(request, f"✅ Đã tạo yêu cầu đặt cọc {amount:,} VNĐ và gửi mã QR cho khách hàng.")
    # Notify customer about deposit request (acts as 'thông báo đặt cọc')
    try:
        notify(user=rr.customer, type_='deposit_success',  # reuse customer bucket
               title='Yêu cầu đặt cọc',
               message=f"Chủ trọ yêu cầu bạn đặt cọc {amount:,} VNĐ cho '{rr.post.title}'.",
               url=reverse('saved_posts'), rental_request=rr, post=rr.post)
    except Exception:
        pass
    return redirect('rental_management')


@login_required
@require_POST
def owner_waive_deposit(request, request_id):
    rr = get_object_or_404(RentalRequest, id=request_id)
    if rr.post.user != request.user:
        messages.error(request, "Bạn không có quyền thực hiện thao tác này.")
        return redirect('rental_management')
    if rr.status not in ['pending', 'accepted']:
        messages.info(request, "Yêu cầu không ở trạng thái phù hợp để bỏ đặt cọc.")
        return redirect('rental_management')
    rr.deposit_status = 'waived'
    rr.save(update_fields=['deposit_status'])

    thread, _ = ChatThread.objects.get_or_create(post=rr.post, guest=rr.customer, owner=rr.post.user)
    ChatMessage.objects.create(thread=thread, sender=request.user,
                               content=f"Chủ trọ xác nhận không cần đặt cọc cho phòng '{rr.post.title}'.")
    messages.success(request, "Đã đánh dấu không cần đặt cọc.")
    return redirect('rental_management')


@login_required
@require_POST
@login_required
@require_POST
def customer_pay_deposit(request, request_id):
    rr = get_object_or_404(RentalRequest, id=request_id, customer=request.user)
    if rr.deposit_status != 'requested' or not rr.deposit_amount:
        messages.error(request, "Không có yêu cầu đặt cọc hợp lệ.")
        return redirect('saved_posts')

    # Bỏ hoàn toàn phương thức ví đối với khách hàng: luôn dùng cổng thanh toán
    payment_method = request.POST.get('payment_method', 'momo')
    if payment_method not in ['momo', 'vnpay']:
        payment_method = 'momo'
    return redirect('deposit_payment_gateway', request_id=request_id, method=payment_method)


@login_required
@require_POST
def customer_cancel_deposit(request, request_id):
    rr = get_object_or_404(RentalRequest, id=request_id, customer=request.user)
    if rr.deposit_status != 'requested':
        messages.error(request, "Không có yêu cầu đặt cọc để hủy.")
        return redirect('saved_posts')

    # Reset về trạng thái 'none' để chủ trọ có thể gửi lại yêu cầu đặt cọc
    rr.deposit_status = 'none'
    rr.deposit_cancelled_at = timezone.now()
    rr.deposit_amount = None
    rr.deposit_payment_url = ''
    rr.deposit_transaction_id = ''
    rr.save(update_fields=['deposit_status', 'deposit_cancelled_at', 'deposit_amount',
                           'deposit_payment_url', 'deposit_transaction_id'])

    # Notify owner
    thread, _ = ChatThread.objects.get_or_create(post=rr.post, guest=rr.customer, owner=rr.post.user)
    ChatMessage.objects.create(thread=thread, sender=request.user,
                               content=f"Khách hàng đã hủy yêu cầu đặt cọc cho phòng '{rr.post.title}'.")
    messages.success(request, "Bạn đã hủy đặt cọc.")
    try:
        notify(user=rr.post.user, type_='deposit_paid',  # reuse bucket
               title='Khách đã hủy đặt cọc',
               message=f"{request.user.username} đã hủy yêu cầu đặt cọc phòng '{rr.post.title}'.",
               url=reverse('rental_management'), rental_request=rr, post=rr.post)
    except Exception:
        pass
    return redirect('saved_posts')


@login_required
def deposit_payment_gateway(request, request_id, method):
    """Tạo QR payment cho đặt cọc qua MoMo/VNPay"""
    rr = get_object_or_404(RentalRequest, id=request_id, customer=request.user)

    if rr.deposit_status != 'requested' or not rr.deposit_amount:
        messages.error(request, "Không có yêu cầu đặt cọc hợp lệ.")
        return redirect('saved_posts')

    amount = int(rr.deposit_amount)

    # Tạo transaction ID unique
    import uuid
    tx_id = f"DEPOSIT_{request_id}_{uuid.uuid4().hex[:8]}"

    # Lưu trạng thái pending
    rr.deposit_status = 'pending_payment'
    rr.deposit_transaction_id = tx_id
    rr.deposit_payment_method = method
    rr.save(update_fields=['deposit_status', 'deposit_transaction_id', 'deposit_payment_method'])

    # Tạo RechargeTransaction để track
    tx = RechargeTransaction.objects.create(
        user=request.user,
        amount=amount,
        payment_method=method,
        transaction_id=tx_id,
        status='pending',
        description=f"Đặt cọc phòng: {rr.post.title}"
    )

    if method == 'momo':
        success, result = _create_deposit_momo_payment(tx, amount, rr)
        if success:
            return redirect(result)  # result is payUrl
        else:
            messages.error(request, f"Lỗi tạo thanh toán MoMo: {result}")
            rr.deposit_status = 'requested'
            rr.save(update_fields=['deposit_status'])
            return redirect('saved_posts')

    else:
        messages.error(request, "Phương thức thanh toán không hợp lệ.")
        return redirect('saved_posts')


@login_required
def deposit_momo_return(request):
    """Xử lý callback từ MoMo sau khi quét QR nạp tiền đặt cọc"""
    result_code = request.GET.get('resultCode')
    order_id = request.GET.get('orderId')

    if not order_id:
        messages.error(request, "Không tìm thấy mã giao dịch.")
        return redirect('saved_posts')

    try:
        tx = RechargeTransaction.objects.get(transaction_id=order_id)
        rr = RentalRequest.objects.get(deposit_transaction_id=order_id)
    except (RechargeTransaction.DoesNotExist, RentalRequest.DoesNotExist):
        messages.error(request, "Không tìm thấy yêu cầu đặt cọc.")
        return redirect('saved_posts')

    # Kiểm tra nếu đã xử lý rồi thì không xử lý lại
    if tx.status == 'completed' and rr.deposit_status == 'paid':
        messages.info(request, f"Giao dịch đã được xử lý trước đó. Số tiền: {rr.deposit_amount:,} VNĐ")
        return redirect('saved_posts')

    if result_code == '0':  # Thanh toán MoMo thành công
        # Ghi nhận giao dịch hoàn tất (không nạp ví khách)
        tx.status = 'completed'
        tx.completed_at = timezone.now()
        tx.save(update_fields=['status', 'completed_at'])

        amount = int(rr.deposit_amount)
        owner = rr.post.user

        # Cộng trực tiếp vào ví chủ trọ và log thu
        owner_wallet, _ = Wallet.objects.get_or_create(user=owner)
        owner_wallet.add_balance(amount)
        RechargeTransaction.create_income(
            user=owner,
            amount=amount,
            description=f"Nhận tiền đặt cọc từ {rr.customer.username} - {rr.post.title}",
            payment_method='momo'  # Đặt cọc qua MoMo
        )

        # Cập nhật trạng thái đặt cọc
        rr.deposit_status = 'paid'
        rr.deposit_paid_at = timezone.now()
        rr.save(update_fields=['deposit_status', 'deposit_paid_at'])

        # Tạo bill
        from website.models import DepositBill
        bill_number = f"BILL{timezone.now().strftime('%Y%m%d%H%M%S')}{rr.id}"
        DepositBill.objects.create(
            rental_request=rr,
            bill_number=bill_number,
            amount=amount,
            customer=rr.customer,
            owner=owner,
            post_title=rr.post.title,
            payment_method='MoMo',
            transaction_id=order_id
        )

        # Nhắn chat
        thread, _ = ChatThread.objects.get_or_create(post=rr.post, guest=rr.customer, owner=owner)
        ChatMessage.objects.create(
            thread=thread,
            sender=rr.customer,
            content=(
                "✅ ĐÃ THANH TOÁN ĐẶT CỌC\n\n"
                f"💰 Số tiền: {amount:,} VNĐ\n"
                f"🏠 Phòng: {rr.post.title}\n"
                f"🧾 Số Bill: {bill_number}\n"
                f"💳 Phương thức: MoMo\n"
                f"💳 Mã GD: {order_id}\n"
                f"⏰ Thời gian: {timezone.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                "Bill đã được tạo. Click vào nút 'Bill' để xem chi tiết!"
            )
        )

        # Thông báo (thêm phương thức)
        try:
            notify(user=owner, type_='deposit_paid',
                   title='Khách đã đặt cọc',
                   message=f"{rr.customer.username} đã đặt cọc {amount:,} VNĐ qua MoMo cho '{rr.post.title}'.",
                   url=reverse('rental_management'), rental_request=rr, post=rr.post)
            notify(user=rr.customer, type_='deposit_success',
                   title='Đặt cọc thành công',
                   message=f"Bạn đã đặt cọc {amount:,} VNĐ qua MoMo cho '{rr.post.title}'.",
                   url=reverse('saved_posts'), rental_request=rr, post=rr.post)
        except Exception:
            pass

        messages.success(request, f"✅ Đã thanh toán đặt cọc {amount:,} VNĐ thành công!")
    else:
        tx.status = 'failed'
        tx.save(update_fields=['status'])

        rr.deposit_status = 'requested'
        rr.save(update_fields=['deposit_status'])

        messages.error(request, "❌ Thanh toán thất bại. Vui lòng thử lại.")

    return redirect('saved_posts')




@login_required
@require_POST
def owner_confirm_deposit(request, request_id):
    """Chủ trọ xác nhận đã nhận tiền đặt cọc"""
    rr = get_object_or_404(RentalRequest, id=request_id, post__user=request.user)

    if rr.deposit_status != 'paid':
        messages.error(request, "Khách chưa thanh toán đặt cọc.")
        return redirect('saved_posts')

    if rr.deposit_confirmed_by_owner:
        messages.info(request, "Bạn đã xác nhận đặt cọc này rồi.")
        return redirect('saved_posts')

    rr.deposit_confirmed_by_owner = True
    rr.deposit_confirmed_at = timezone.now()
    rr.deposit_status = 'confirmed_by_owner'
    rr.save(update_fields=['deposit_confirmed_by_owner', 'deposit_confirmed_at', 'deposit_status'])
    try:
        notify(user=rr.customer, type_='deposit_confirmed',
               title='Chủ trọ xác nhận đặt cọc',
               message=f"Chủ trọ đã xác nhận nhận {int(rr.deposit_amount):,} VNĐ cho '{rr.post.title}'.",
               url=reverse('saved_posts'), rental_request=rr, post=rr.post)
    except Exception:
        pass
    messages.success(request, "✅ Đã xác nhận nhận tiền đặt cọc!")
    return redirect('rental_management')


# ===== Notifications UI =====
@login_required
def notifications_center(request):
    items = Notification.objects.filter(user=request.user).order_by('-created_at')[:50]
    return render(request, 'website/notifications.html', {'items': items})


@login_required
def notification_go(request, notif_id):
    notif = get_object_or_404(Notification, id=notif_id, user=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=['is_read'])
    # Điều chỉnh đích tới động cho các loại thông báo quan trọng
    if notif.type == 'post_removed_violation':
        from django.urls import reverse
        target = f"{reverse('manage_rooms')}?status=removed"
    else:
        target = notif.url or '/'
    return redirect(target)


@login_required
def notifications_mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('notifications_center')


@login_required
def notification_delete(request, notif_id):
    """Xóa một thông báo của chính người dùng."""
    notif = get_object_or_404(Notification, id=notif_id, user=request.user)
    if request.method == 'POST':
        notif.delete()
        messages.success(request, 'Đã xóa thông báo.')
    return redirect('notifications_center')


@login_required
def notifications_delete_all(request):
    """Xóa tất cả thông báo của người dùng hiện tại."""
    if request.method == 'POST':
        Notification.objects.filter(user=request.user).delete()
        messages.success(request, 'Đã xóa tất cả thông báo.')
    return redirect('notifications_center')


@login_required
def view_deposit_bill(request, request_id):
    """Xem chi tiết hóa đơn đặt cọc"""
    from website.models import DepositBill

    rr = get_object_or_404(RentalRequest, id=request_id)

    # Kiểm tra quyền: chỉ khách hàng hoặc chủ trọ mới xem được
    if request.user != rr.customer and request.user != rr.post.user:
        messages.error(request, "Bạn không có quyền xem bill này.")
        return redirect('index')

    # Lấy bill
    try:
        bill = DepositBill.objects.get(rental_request=rr)
    except DepositBill.DoesNotExist:
        messages.error(request, "Chưa có bill cho yêu cầu này.")
        return redirect('manage_rooms' if request.user == rr.post.user else 'saved_posts')

    context = {
        'bill': bill,
        'rental_request': rr,
    }
    return render(request, 'website/deposit_bill.html', context)

    # Thông báo cho khách
    thread, _ = ChatThread.objects.get_or_create(
        post=rr.post,
        guest=rr.customer,
        owner=rr.post.user
    )
    ChatMessage.objects.create(
        thread=thread,
        sender=request.user,
        content=f"✅ Chủ trọ đã xác nhận nhận tiền đặt cọc {rr.deposit_amount:,} VNĐ.\n\n" +
                f"Phòng đã được giữ chỗ cho bạn!"
    )

    messages.success(request, "✅ Đã xác nhận nhận tiền đặt cọc!")
    return redirect('saved_posts')


@login_required
@require_POST
def submit_report(request, post_id):
    """Xử lý báo cáo vi phạm bài đăng"""
    from .models import PostReport
    post = get_object_or_404(RentalPost, id=post_id)

    # Mỗi tài khoản chỉ được báo cáo một lần cho mỗi bài (bắt buộc đăng nhập)
    if PostReport.objects.filter(post=post, reporter=request.user).exists():
        messages.error(request, "Bạn đã báo cáo bài đăng này rồi. Không thể báo cáo thêm.")
        return redirect('post_detail', pk=post_id)

    # Đã bắt buộc đăng nhập: tự động lấy thông tin từ tài khoản
    reporter = request.user
    reporter_name = request.user.get_full_name() or request.user.username
    try:
        reporter_phone = request.user.customerprofile.phone or 'Chưa cập nhật'
    except:
        reporter_phone = 'Chưa cập nhật'

    reason = request.POST.get('reason', '')
    description = request.POST.get('description', '').strip()

    if not reason:
        messages.error(request, "Vui lòng chọn lý do phản ánh.")
        return redirect('post_detail', pk=post_id)

    PostReport.objects.create(
        post=post,
        reporter=reporter,
        reporter_name=reporter_name,
        reporter_phone=reporter_phone,
        reason=reason,
        description=description
    )

    messages.success(request, "✅ Bạn đã phản ánh thành công! Chúng tôi sẽ xem xét và xử lý trong thời gian sớm nhất.")
    return redirect('post_detail', pk=post_id)


# ================= Helper functions cho Deposit Payment =================

def _create_deposit_momo_payment(transaction, amount, rental_request):
    """Tạo MoMo payment cho đặt cọc"""
    partnerCode = getattr(settings, 'MOMO_PARTNER_CODE', '')
    accessKey = getattr(settings, 'MOMO_ACCESS_KEY', '')
    secretKey = getattr(settings, 'MOMO_SECRET_KEY', '')
    endPoint = getattr(settings, 'MOMO_ENDPOINT', 'https://test-payment.momo.vn/v2/gateway/api/create')
    ipnUrl = settings.SITE_URL + '/payments/deposit/momo/notify/'
    redirectUrl = settings.SITE_URL + '/payments/deposit/momo/return/'

    orderId = transaction.transaction_id
    requestId = orderId
    orderInfo = f"Dat coc phong {rental_request.post.title}"
    extraData = f"rental_request_id={rental_request.id}"
    requestType = 'captureWallet'

    raw_signature = f"accessKey={accessKey}&amount={int(amount)}&extraData={extraData}&ipnUrl={ipnUrl}&orderId={orderId}&orderInfo={orderInfo}&partnerCode={partnerCode}&redirectUrl={redirectUrl}&requestId={requestId}&requestType={requestType}"
    signature = hmac.new(secretKey.encode('utf-8'), raw_signature.encode('utf-8'), hashlib.sha256).hexdigest()

    payload = {
        'partnerCode': partnerCode,
        'accessKey': accessKey,
        'requestId': requestId,
        'amount': int(amount),
        'orderId': orderId,
        'orderInfo': orderInfo,
        'redirectUrl': redirectUrl,
        'ipnUrl': ipnUrl,
        'requestType': requestType,
        'extraData': extraData,
        'signature': signature,
        'lang': 'vi'
    }

    try:
        import requests
        response = requests.post(endPoint, json=payload, timeout=10)
        data = response.json()
        if data.get('resultCode') == 0 and data.get('payUrl'):
            return (True, data['payUrl'])
        else:
            return (False, data.get('message', 'Unknown error'))
    except Exception as e:
        return (False, str(e))