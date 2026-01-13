"""
Views cho hệ thống gợi ý AI
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import timedelta

from .models import PostView, SearchHistory, UserInteraction, RecommendationLog
from .ml_models.hybrid import HybridRecommender
from website.models import RentalPost


# Khởi tạo recommender
recommender = HybridRecommender()


def get_recommendations_view(request):
    """
    API để lấy danh sách phòng gợi ý

    Query params:
    - limit: số lượng gợi ý (default: 10)
    - strategy: 'weighted', 'switching', 'mixed' (default: 'weighted')
    - post_id: ID bài để tìm similar (optional)
    """
    limit = int(request.GET.get('limit', 10))
    strategy = request.GET.get('strategy', 'weighted')
    post_id = request.GET.get('post_id', None)

    user = request.user if request.user.is_authenticated else None
    session_id = request.session.session_key

    # Tạo session key nếu chưa có
    if not session_id:
        request.session.create()
        session_id = request.session.session_key

    context = {
        'session_id': session_id,
    }

    # Lấy recommendations
    if post_id:
        recommended_posts = recommender.get_similar_posts(post_id=post_id, limit=limit)
        algorithm = 'similar_posts'
    else:
        recommended_posts = recommender.get_recommendations(
            user=user,
            post_id=None,
            limit=limit,
            context=context,
            strategy=strategy
        )
        algorithm = f'hybrid_{strategy}'

    # Log recommendation
    _log_recommendation(user, session_id, recommended_posts, algorithm)

    # Chuyển đổi sang JSON
    results = []
    for post in recommended_posts:
        results.append({
            'id': post.id,
            'title': post.title,
            'price': float(post.price),
            'area': post.area,
            'address': post.address or '',
            'province': post.province.name if post.province else '',
            'district': post.district.name if post.district else '',
            'category': post.get_category_display(),
            'image_url': post.image.url if post.image else None,
            'created_at': post.created_at.isoformat(),
        })

    return JsonResponse({
        'success': True,
        'count': len(results),
        'recommendations': results,
        'algorithm': algorithm,
    })


def track_view(request, post_id):
    """
    Track khi user xem chi tiết bài đăng

    POST /goiy-ai/track/view/<post_id>/
    Body: { "duration": 30 }  # Thời gian xem (giây)
    """
    import json

    try:
        post = RentalPost.objects.get(id=post_id)
    except RentalPost.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    user = request.user if request.user.is_authenticated else None
    session_id = request.session.session_key or ''

    # Lấy IP address
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')

    # Lấy duration từ request body
    duration = 0
    if request.method == 'POST' and request.body:
        try:
            data = json.loads(request.body)
            duration = int(data.get('duration', 0))
        except:
            pass

    # Tạo PostView record
    PostView.objects.create(
        user=user,
        post=post,
        session_id=session_id,
        ip_address=ip_address,
        duration=duration
    )

    # Tạo UserInteraction
    UserInteraction.objects.create(
        user=user,
        post=post,
        session_id=session_id,
        interaction_type='view',
        ip_address=ip_address,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
    )

    return JsonResponse({'success': True})


def track_save(request, post_id):
    """
    Track khi user lưu tin

    POST /goiy-ai/track/save/<post_id>/
    """
    try:
        post = RentalPost.objects.get(id=post_id)
    except RentalPost.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    user = request.user if request.user.is_authenticated else None
    session_id = request.session.session_key or ''

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')

    # Tạo UserInteraction
    UserInteraction.objects.create(
        user=user,
        post=post,
        session_id=session_id,
        interaction_type='save',
        ip_address=ip_address,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
    )

    return JsonResponse({'success': True})


def track_unsave(request, post_id):
    """Track khi user bỏ lưu tin"""
    try:
        post = RentalPost.objects.get(id=post_id)
    except RentalPost.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    user = request.user if request.user.is_authenticated else None
    session_id = request.session.session_key or ''

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')

    UserInteraction.objects.create(
        user=user,
        post=post,
        session_id=session_id,
        interaction_type='unsave',
        ip_address=ip_address,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
    )

    return JsonResponse({'success': True})


def track_contact(request, post_id):
    """Track khi user liên hệ/chat"""
    try:
        post = RentalPost.objects.get(id=post_id)
    except RentalPost.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    user = request.user if request.user.is_authenticated else None
    session_id = request.session.session_key or ''

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')

    UserInteraction.objects.create(
        user=user,
        post=post,
        session_id=session_id,
        interaction_type='contact',
        ip_address=ip_address,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
    )

    return JsonResponse({'success': True})


def track_request(request, post_id):
    """Track khi user gửi yêu cầu thuê"""
    try:
        post = RentalPost.objects.get(id=post_id)
    except RentalPost.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)

    user = request.user if request.user.is_authenticated else None
    session_id = request.session.session_key or ''

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')

    UserInteraction.objects.create(
        user=user,
        post=post,
        session_id=session_id,
        interaction_type='request',
        ip_address=ip_address,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
    )

    return JsonResponse({'success': True})


def track_search(request):
    """
    Track lịch sử tìm kiếm

    POST /goiy-ai/track/search/
    Body: {
        "query": "...",
        "category": "...",
        "province_id": 1,
        "district_id": 2,
        "min_price": 1000000,
        "max_price": 5000000,
        "min_area": 20,
        "max_area": 50,
        "features": ["wifi", "parking"],
        "results_count": 15
    }
    """
    import json

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    user = request.user if request.user.is_authenticated else None
    session_id = request.session.session_key or ''

    # Tạo session key nếu chưa có
    if not session_id:
        request.session.create()
        session_id = request.session.session_key

    # Tạo SearchHistory record
    SearchHistory.objects.create(
        user=user,
        session_id=session_id,
        query=data.get('query', ''),
        category=data.get('category', ''),
        province_id=data.get('province_id'),
        district_id=data.get('district_id'),
        min_price=data.get('min_price'),
        max_price=data.get('max_price'),
        min_area=data.get('min_area'),
        max_area=data.get('max_area'),
        features=data.get('features', []),
        results_count=data.get('results_count', 0)
    )

    return JsonResponse({'success': True})


def _log_recommendation(user, session_id, posts, algorithm):
    """Log recommendation để phân tích hiệu quả sau này"""
    post_ids = [post.id for post in posts]

    RecommendationLog.objects.create(
        user=user,
        session_id=session_id,
        recommended_posts=post_ids,
        algorithm_used=algorithm
    )


@login_required
def my_recommendations_page(request):
    """
    Trang hiển thị gợi ý cá nhân hóa cho user
    """
    # Lấy gợi ý
    recommended_posts = recommender.get_personalized_recommendations(
        user=request.user,
        limit=20
    )

    context = {
        'recommended_posts': recommended_posts,
        'page_title': 'Gợi ý cho bạn',
    }

    return render(request, 'goiy_ai/recommendations.html', context)


def analytics_view(request):
    """
    Trang thống kê hiệu quả recommendation system (admin only)
    """
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Thống kê cơ bản
    total_views = PostView.objects.count()
    total_interactions = UserInteraction.objects.count()
    total_searches = SearchHistory.objects.count()

    # Thống kê theo loại interaction
    from django.db.models import Count
    interaction_stats = UserInteraction.objects.values('interaction_type').annotate(
        count=Count('id')
    ).order_by('-count')

    # Top bài được xem nhiều nhất (7 ngày qua)
    top_viewed_posts = PostView.objects.filter(
        viewed_at__gte=timezone.now() - timedelta(days=7)
    ).values('post__title').annotate(
        view_count=Count('id')
    ).order_by('-view_count')[:10]

    context = {
        'total_views': total_views,
        'total_interactions': total_interactions,
        'total_searches': total_searches,
        'interaction_stats': list(interaction_stats),
        'top_viewed_posts': list(top_viewed_posts),
    }

    return JsonResponse(context)
