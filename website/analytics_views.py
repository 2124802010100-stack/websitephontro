"""
Dashboard Analytics cho Chủ Trọ
Hiển thị thống kê chi tiết về hiệu quả bài đăng
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Count, Q, Avg, Sum
from django.db import models
from django.utils import timezone
from datetime import timedelta
from website.models import RentalPost, RentalRequest, SavedPost, ChatMessage

# Import goiy_ai models if available (may be disabled in production)
try:
    from goiy_ai.models import PostView, UserInteraction
    GOIY_AI_AVAILABLE = True
except (ImportError, RuntimeError):
    GOIY_AI_AVAILABLE = False
    PostView = None
    UserInteraction = None

import json


@login_required
def owner_dashboard(request):
    """
    Dashboard chính cho chủ trọ
    """
    user = request.user

    # Debug log
    print(f"🔍 Analytics view called by user: {user.username}")

    # Kiểm tra xem user có phải chủ trọ không
    if not hasattr(user, 'customerprofile') or user.customerprofile.role != 'owner':
        print(f"❌ User {user.username} không phải chủ trọ")
        return render(request, 'website/analytics/no_permission.html')

    print(f"✅ User {user.username} là chủ trọ, rendering dashboard...")

    # Lấy tất cả bài đăng của chủ trọ
    posts = RentalPost.objects.filter(user=user, is_deleted=False)

    # Thống kê tổng quan
    total_posts = posts.count()
    active_posts = posts.filter(is_approved=True, expired_at__gt=timezone.now()).count()
    rented_posts = posts.filter(is_rented=True).count()
    pending_posts = posts.filter(is_approved=False).count()

    print(f"📊 Stats: {total_posts} posts total, {active_posts} active")

    context = {
        'total_posts': total_posts,
        'active_posts': active_posts,
        'rented_posts': rented_posts,
        'pending_posts': pending_posts,
    }

    return render(request, 'website/analytics/dashboard.html', context)


@login_required
def analytics_revenue_api(request):
    """
    API trả về doanh thu theo ngày/tuần/tháng/năm
    """
    user = request.user

    if not hasattr(user, 'customerprofile') or user.customerprofile.role != 'owner':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    period = request.GET.get('period', 'month')  # day, week, month, year

    # Lấy tất cả giao dịch đặt cọc đã thanh toán thành công của các phòng của user
    from .models import DepositBill
    user_posts = RentalPost.objects.filter(user=user, is_deleted=False)

    now = timezone.now()
    labels = []
    data = []

    if period == 'day':
        # 24 giờ gần nhất - tính doanh thu theo giờ
        for i in range(23, -1, -1):
            hour = now - timedelta(hours=i)
            labels.append(hour.strftime('%H:%M'))
            # Tính tổng tiền đặt cọc đã thanh toán trong giờ
            hourly_revenue = DepositBill.objects.filter(
                rental_request__post__in=user_posts,
                rental_request__deposit_status__in=['paid', 'confirmed_by_owner'],
                created_at__gte=hour.replace(minute=0, second=0, microsecond=0),
                created_at__lt=(hour + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            ).aggregate(total=Sum('amount'))['total'] or 0
            data.append(float(hourly_revenue) / 1000000)  # Convert to triệu đồng

    elif period == 'week':
        # 7 ngày gần nhất - tính doanh thu theo ngày
        for i in range(6, -1, -1):
            date = now - timedelta(days=i)
            labels.append(date.strftime('%d/%m'))
            # Tính tổng tiền đặt cọc đã thanh toán trong ngày
            daily_revenue = DepositBill.objects.filter(
                rental_request__post__in=user_posts,
                rental_request__deposit_status__in=['paid', 'confirmed_by_owner'],
                created_at__date=date.date()
            ).aggregate(total=Sum('amount'))['total'] or 0
            data.append(float(daily_revenue) / 1000000)  # Convert to triệu đồng

    elif period == 'month':
        # 30 ngày gần nhất
        for i in range(29, -1, -1):
            date = now - timedelta(days=i)
            labels.append(date.strftime('%d/%m'))
            # Tổng tiền đặt cọc đã thanh toán trong ngày
            daily_revenue = DepositBill.objects.filter(
                rental_request__post__in=user_posts,
                rental_request__deposit_status__in=['paid', 'confirmed_by_owner'],
                created_at__date=date.date()
            ).aggregate(total=Sum('amount'))['total'] or 0
            data.append(float(daily_revenue) / 1000000)

    else:  # year
        # 12 tháng gần nhất
        for i in range(11, -1, -1):
            date = now - timedelta(days=i*30)
            labels.append(date.strftime('%m/%Y'))
            month_start = date.replace(day=1)
            if i == 0:
                month_end = now
            else:
                month_end = (now - timedelta(days=(i-1)*30)).replace(day=1) - timedelta(days=1)
            # Tổng tiền đặt cọc đã thanh toán trong tháng
            monthly_revenue = DepositBill.objects.filter(
                rental_request__post__in=user_posts,
                rental_request__deposit_status__in=['paid', 'confirmed_by_owner'],
                created_at__date__gte=month_start.date(),
                created_at__date__lte=month_end.date()
            ).aggregate(total=Sum('amount'))['total'] or 0
            data.append(float(monthly_revenue) / 1000000)

    return JsonResponse({
        'labels': labels,
        'data': data,
        'total': round(sum(data), 2)
    })


@login_required
def analytics_pie_chart_api(request):
    """
    API trả về dữ liệu biểu đồ tròn: phòng trống vs đã thuê
    """
    user = request.user

    if not hasattr(user, 'customerprofile') or user.customerprofile.role != 'owner':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    posts = RentalPost.objects.filter(user=user, is_deleted=False, is_approved=True)

    rented = posts.filter(is_rented=True).count()
    available = posts.filter(is_rented=False).count()

    return JsonResponse({
        'labels': ['Đã cho thuê', 'Còn trống'],
        'data': [rented, available],
        'colors': ['#10b981', '#3b82f6']
    })


@login_required
def analytics_overview_api(request):
    """
    API trả về thống kê tổng quan (30 ngày gần nhất)
    """
    user = request.user

    if not hasattr(user, 'customerprofile') or user.customerprofile.role != 'owner':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    # Lấy bài đăng của user
    post_ids = list(RentalPost.objects.filter(user=user, is_deleted=False).values_list('id', flat=True))

    # Thống kê 30 ngày gần nhất
    thirty_days_ago = timezone.now() - timedelta(days=30)

    # Lượt xem
    total_views = PostView.objects.filter(post_id__in=post_ids, viewed_at__gte=thirty_days_ago).count()

    # Lượt lưu (từ SavedPost model)
    total_saves = SavedPost.objects.filter(
        post_id__in=post_ids,
        saved_at__gte=thirty_days_ago
    ).count()

    # Lượt liên hệ (bao gồm cả UserInteraction và RentalRequest)
    contact_interactions = UserInteraction.objects.filter(
        post_id__in=post_ids,
        interaction_type='contact',
        created_at__gte=thirty_days_ago
    ).count()

    # Yêu cầu thuê
    total_requests = RentalRequest.objects.filter(
        post_id__in=post_ids,
        created_at__gte=thirty_days_ago
    ).count()

    # Tổng lượt liên hệ = contact interactions + rental requests
    total_contacts = contact_interactions + total_requests

    # Tỷ lệ chuyển đổi
    conversion_rate = (total_requests / total_views * 100) if total_views > 0 else 0

    return JsonResponse({
        'total_views': total_views,
        'total_saves': total_saves,
        'total_contacts': total_contacts,
        'total_requests': total_requests,
        'conversion_rate': round(conversion_rate, 2)
    })


@login_required
def analytics_chart_data_api(request):
    """
    API trả về dữ liệu cho biểu đồ (30 ngày gần nhất, group by day)
    """
    user = request.user

    if not hasattr(user, 'customerprofile') or user.customerprofile.role != 'owner':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    post_ids = list(RentalPost.objects.filter(user=user, is_deleted=False).values_list('id', flat=True))

    # Lấy dữ liệu 30 ngày
    thirty_days_ago = timezone.now() - timedelta(days=30)

    # Chuẩn bị labels (30 ngày)
    labels = []
    dates = []
    for i in range(29, -1, -1):
        date = timezone.now() - timedelta(days=i)
        labels.append(date.strftime('%d/%m'))
        dates.append(date.date())

    # Lượt xem theo ngày
    views_by_day = {}
    views = PostView.objects.filter(
        post_id__in=post_ids,
        viewed_at__gte=thirty_days_ago
    ).extra(select={'day': 'DATE(viewed_at)'}).values('day').annotate(count=Count('id'))

    for item in views:
        views_by_day[str(item['day'])] = item['count']

    views_data = [views_by_day.get(str(date), 0) for date in dates]

    # Lượt lưu theo ngày
    saves_by_day = {}
    saves = UserInteraction.objects.filter(
        post_id__in=post_ids,
        interaction_type='save',
        created_at__gte=thirty_days_ago
    ).extra(select={'day': 'DATE(created_at)'}).values('day').annotate(count=Count('id'))

    for item in saves:
        saves_by_day[str(item['day'])] = item['count']

    saves_data = [saves_by_day.get(str(date), 0) for date in dates]

    # Yêu cầu thuê theo ngày
    requests_by_day = {}
    requests = RentalRequest.objects.filter(
        post_id__in=post_ids,
        created_at__gte=thirty_days_ago
    ).extra(select={'day': 'DATE(created_at)'}).values('day').annotate(count=Count('id'))

    for item in requests:
        requests_by_day[str(item['day'])] = item['count']

    requests_data = [requests_by_day.get(str(date), 0) for date in dates]

    return JsonResponse({
        'labels': labels,
        'datasets': [
            {
                'label': 'Lượt xem',
                'data': views_data,
                'borderColor': 'rgb(75, 192, 192)',
                'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                'tension': 0.4
            },
            {
                'label': 'Lượt lưu',
                'data': saves_data,
                'borderColor': 'rgb(255, 159, 64)',
                'backgroundColor': 'rgba(255, 159, 64, 0.2)',
                'tension': 0.4
            },
            {
                'label': 'Yêu cầu thuê',
                'data': requests_data,
                'borderColor': 'rgb(54, 162, 235)',
                'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                'tension': 0.4
            }
        ]
    })


@login_required
def analytics_top_posts_api(request):
    """
    API trả về top 5 phòng có hiệu suất tốt nhất
    """
    user = request.user

    if not hasattr(user, 'customerprofile') or user.customerprofile.role != 'owner':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    posts = RentalPost.objects.filter(user=user, is_deleted=False)

    thirty_days_ago = timezone.now() - timedelta(days=30)

    top_posts = []

    for post in posts:
        # Đếm views
        views = PostView.objects.filter(post=post, viewed_at__gte=thirty_days_ago).count()

        # Đếm saves
        saves = UserInteraction.objects.filter(
            post=post,
            interaction_type='save',
            created_at__gte=thirty_days_ago
        ).count()

        # Đếm requests
        requests = RentalRequest.objects.filter(post=post, created_at__gte=thirty_days_ago).count()

        # Tính điểm (weighted score)
        score = views * 1 + saves * 3 + requests * 10

        top_posts.append({
            'id': post.id,
            'title': post.title,
            'price': float(post.price),
            'area': post.area,
            'views': views,
            'saves': saves,
            'requests': requests,
            'score': score,
            'image_url': post.image.url if post.image else None,
            'is_rented': post.is_rented,
            'province': post.province.name if post.province else None
        })

    # Sắp xếp theo score
    top_posts.sort(key=lambda x: x['score'], reverse=True)

    return JsonResponse({'posts': top_posts[:5]})


@login_required
def analytics_post_detail_api(request, post_id):
    """
    API chi tiết analytics cho 1 bài đăng cụ thể
    """
    user = request.user

    try:
        post = RentalPost.objects.get(id=post_id, user=user, is_deleted=False)
    except RentalPost.DoesNotExist:
        return JsonResponse({'error': 'Post not found'}, status=404)

    thirty_days_ago = timezone.now() - timedelta(days=30)

    # Thống kê chi tiết
    total_views = PostView.objects.filter(post=post, viewed_at__gte=thirty_days_ago).count()
    total_saves = SavedPost.objects.filter(post=post, saved_at__gte=thirty_days_ago).count()

    # Lượt liên hệ (UserInteraction + RentalRequest)
    contact_interactions = UserInteraction.objects.filter(
        post=post,
        interaction_type='contact',
        created_at__gte=thirty_days_ago
    ).count()
    total_requests = RentalRequest.objects.filter(post=post, created_at__gte=thirty_days_ago).count()
    total_contacts = contact_interactions + total_requests

    # Unique visitors
    unique_visitors = PostView.objects.filter(
        post=post,
        viewed_at__gte=thirty_days_ago
    ).values('user', 'session_id').distinct().count()

    # Average view duration
    avg_duration = PostView.objects.filter(
        post=post,
        viewed_at__gte=thirty_days_ago
    ).aggregate(avg=Avg('duration'))['avg'] or 0

    return JsonResponse({
        'post_id': post.id,
        'title': post.title,
        'total_views': total_views,
        'unique_visitors': unique_visitors,
        'total_saves': total_saves,
        'total_contacts': total_contacts,
        'total_requests': total_requests,
        'avg_duration': round(avg_duration, 2),
        'conversion_rate': round((total_requests / total_views * 100) if total_views > 0 else 0, 2)
    })


@login_required
def analytics_insights_api(request):
    """
    API trả về insights và gợi ý cải thiện
    """
    user = request.user

    if not hasattr(user, 'customerprofile') or user.customerprofile.role != 'owner':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    posts = RentalPost.objects.filter(user=user, is_deleted=False, is_approved=True)

    if posts.count() == 0:
        return JsonResponse({'insights': []})

    thirty_days_ago = timezone.now() - timedelta(days=30)

    insights = []

    # Insight 1: Phòng có lượt xem thấp
    for post in posts:
        views = PostView.objects.filter(post=post, viewed_at__gte=thirty_days_ago).count()
        if views < 10:
            insights.append({
                'type': 'warning',
                'icon': '⚠️',
                'title': f'Phòng "{post.title[:30]}..." có lượt xem thấp',
                'message': f'Chỉ có {views} lượt xem trong 30 ngày. Gợi ý: Cập nhật ảnh đẹp hơn, giảm giá 5-10% hoặc thêm tiện nghi.',
                'post_id': post.id
            })

    # Insight 2: Tỷ lệ chuyển đổi cao
    for post in posts:
        views = PostView.objects.filter(post=post, viewed_at__gte=thirty_days_ago).count()
        requests = RentalRequest.objects.filter(post=post, created_at__gte=thirty_days_ago).count()
        if views > 20 and requests / views > 0.1:  # > 10% conversion
            insights.append({
                'type': 'success',
                'icon': '🎉',
                'title': f'Phòng "{post.title[:30]}..." đang rất hot!',
                'message': f'Tỷ lệ chuyển đổi {requests/views*100:.1f}% (rất cao). Bạn có thể tăng giá nhẹ 5-10% để tối ưu doanh thu.',
                'post_id': post.id
            })

    # Insight 3: Giá so với trung bình
    avg_price_by_province = {}
    for post in posts:
        if post.province:
            if post.province.id not in avg_price_by_province:
                avg = RentalPost.objects.filter(
                    province=post.province,
                    is_approved=True,
                    is_deleted=False
                ).aggregate(Avg('price'))['price__avg']
                avg_price_by_province[post.province.id] = avg or 0

            avg_price = avg_price_by_province[post.province.id]
            if post.price > avg_price * 1.3:  # Cao hơn 30%
                insights.append({
                    'type': 'info',
                    'icon': '💡',
                    'title': f'Giá phòng "{post.title[:30]}..." cao hơn trung bình',
                    'message': f'Giá của bạn ({post.price:,.0f}đ) cao hơn 30% so với khu vực ({avg_price:,.0f}đ). Nếu lâu không cho thuê được, hãy xem xét giảm giá.',
                    'post_id': post.id
                })

    # Insight 4: Tổng quan chung
    total_views = PostView.objects.filter(
        post__in=posts,
        viewed_at__gte=thirty_days_ago
    ).count()

    if total_views > 100:
        insights.insert(0, {
            'type': 'success',
            'icon': '📈',
            'title': 'Hiệu suất tuyệt vời!',
            'message': f'Các bài đăng của bạn đã có {total_views} lượt xem trong 30 ngày qua. Tiếp tục duy trì!',
            'post_id': None
        })

    return JsonResponse({'insights': insights[:10]})  # Giới hạn 10 insights


@login_required
def analytics_views_detail_api(request):
    """
    API trả về chi tiết lượt xem theo từng bài đăng
    """
    user = request.user

    if not hasattr(user, 'customerprofile') or user.customerprofile.role != 'owner':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    posts = RentalPost.objects.filter(user=user, is_deleted=False, is_approved=True)
    thirty_days_ago = timezone.now() - timedelta(days=30)

    views_data = []
    for post in posts:
        view_count = PostView.objects.filter(post=post, viewed_at__gte=thirty_days_ago).count()
        if view_count > 0:
            image_url = post.images.first().image.url if post.images.exists() else None
            views_data.append({
                'id': post.id,
                'title': post.title,
                'view_count': view_count,
                'image': image_url,
                'price': float(post.price) if post.price else 0,
                'province': post.province.name if post.province else 'N/A'
            })

    # Sắp xếp theo lượt xem giảm dần
    views_data.sort(key=lambda x: x['view_count'], reverse=True)

    return JsonResponse({
        'views': views_data[:20]  # Top 20 bài nhiều view nhất
    })


@login_required
def analytics_saves_detail_api(request):
    """
    API trả về chi tiết lượt lưu tin theo từng bài đăng
    """
    user = request.user

    if not hasattr(user, 'customerprofile') or user.customerprofile.role != 'owner':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    posts = RentalPost.objects.filter(user=user, is_deleted=False, is_approved=True)

    saves_data = []
    for post in posts:
        saved_by = SavedPost.objects.filter(post=post).select_related('user')
        save_count = saved_by.count()
        if save_count > 0:
            image_url = post.images.first().image.url if post.images.exists() else None
            users = [sp.user.username for sp in saved_by[:10]]  # Lấy 10 người đầu
            if save_count > 10:
                users.append(f'và {save_count - 10} người khác')

            saves_data.append({
                'id': post.id,
                'title': post.title,
                'save_count': save_count,
                'image': image_url,
                'price': float(post.price) if post.price else 0,
                'province': post.province.name if post.province else 'N/A',
                'users': users
            })

    # Sắp xếp theo lượt lưu giảm dần
    saves_data.sort(key=lambda x: x['save_count'], reverse=True)

    return JsonResponse({
        'saves': saves_data[:20]  # Top 20 bài nhiều lượt lưu nhất
    })


@login_required
def analytics_contacts_detail_api(request):
    """
    API trả về chi tiết lượt liên hệ theo từng bài đăng
    """
    user = request.user

    if not hasattr(user, 'customerprofile') or user.customerprofile.role != 'owner':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    posts = RentalPost.objects.filter(user=user, is_deleted=False, is_approved=True)

    contacts_data = []
    for post in posts:
        # Đếm lượt liên hệ từ UserInteraction
        contact_interactions = UserInteraction.objects.filter(
            post=post,
            interaction_type='contact'
        ).select_related('user')

        # Đếm lượt request
        rental_requests = RentalRequest.objects.filter(post=post).select_related('customer')

        total_contacts = contact_interactions.count() + rental_requests.count()

        if total_contacts > 0:
            image_url = post.images.first().image.url if post.images.exists() else None

            # Lấy danh sách user đã liên hệ
            contact_users = set()
            for ci in contact_interactions[:5]:
                contact_users.add(ci.user.username)
            for rr in rental_requests[:5]:
                contact_users.add(rr.customer.username)

            users_list = list(contact_users)
            if total_contacts > len(users_list):
                users_list.append(f'và {total_contacts - len(users_list)} người khác')

            contacts_data.append({
                'id': post.id,
                'title': post.title,
                'contact_count': total_contacts,
                'image': image_url,
                'price': float(post.price) if post.price else 0,
                'province': post.province.name if post.province else 'N/A',
                'users': users_list
            })

    # Sắp xếp theo lượt liên hệ giảm dần
    contacts_data.sort(key=lambda x: x['contact_count'], reverse=True)

    return JsonResponse({
        'contacts': contacts_data[:20]  # Top 20 bài nhiều lượt liên hệ nhất
    })
