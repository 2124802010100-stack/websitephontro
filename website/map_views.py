"""
Views cho chức năng bản đồ tương tác
"""
from django.shortcuts import render
from django.http import JsonResponse
# from django.contrib.gis.geos import Point  # Tạm tắt vì chưa có GDAL
# from django.contrib.gis.measure import D
# from django.contrib.gis.db.models.functions import Distance
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Min, Max
from django.utils import timezone
from decimal import Decimal
import json
import math

from .models import RentalPost, PointOfInterest


def map_view(request):
    """Render trang bản đồ tương tác"""
    # Lấy thống kê giá để setup color coding
    price_stats = RentalPost.objects.filter(
        is_approved=True,
        is_deleted=False,
        latitude__isnull=False,
        longitude__isnull=False
    ).aggregate(
        min_price=Min('price'),
        max_price=Max('price')
    )

    context = {
        'min_price': float(price_stats['min_price'] or 0),
        'max_price': float(price_stats['max_price'] or 10000000),
    }

    return render(request, 'website/map_interactive.html', context)


@require_http_methods(["GET"])
def map_data_api(request):
    """
    API trả về dữ liệu phòng trọ dưới dạng GeoJSON

    Query params:
        - min_price: Giá tối thiểu
        - max_price: Giá tối đa
        - lat, lng: Tọa độ trung tâm tìm kiếm
        - radius: Bán kính tìm kiếm (km)
        - poi_types: Các loại POI (phân cách bằng dấu phẩy)
        - category: Loại phòng
    """
    # Lấy tất cả bài đăng hợp lệ có tọa độ
    now = timezone.now()
    posts = RentalPost.objects.filter(
        is_approved=True,          # Đã duyệt
        is_deleted=False,          # Chưa xóa
        is_rented=False,           # Chưa cho thuê
        latitude__isnull=False,    # Có tọa độ
        longitude__isnull=False
    ).exclude(
        expired_at__lt=now         # Loại bỏ bài hết hạn
    ).select_related('province', 'district', 'ward', 'user')

    # Filter theo giá
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    if min_price:
        posts = posts.filter(price__gte=Decimal(min_price))
    if max_price:
        posts = posts.filter(price__lte=Decimal(max_price))

    # Filter theo category
    category = request.GET.get('category')
    if category:
        posts = posts.filter(category=category)

    # Filter theo bán kính (sử dụng Haversine formula)
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    radius = request.GET.get('radius', 5)  # Default 5km

    if lat and lng:
        try:
            center_lat = float(lat)
            center_lng = float(lng)
            radius_km = float(radius)

            # Lọc theo bounding box trước để giảm số lượng tính toán
            # Khoảng 1 độ ≈ 111km
            lat_range = radius_km / 111.0
            lng_range = radius_km / (111.0 * math.cos(math.radians(center_lat)))

            posts = posts.filter(
                latitude__range=(center_lat - lat_range, center_lat + lat_range),
                longitude__range=(center_lng - lng_range, center_lng + lng_range)
            )

            # Lọc chính xác bằng Haversine
            filtered_posts = []
            for post in posts:
                distance = _calculate_distance(
                    center_lat, center_lng,
                    post.latitude, post.longitude
                )
                if distance <= radius_km:
                    post.distance_km = distance
                    filtered_posts.append(post)

            # Sort theo distance
            filtered_posts.sort(key=lambda x: x.distance_km)
            posts = filtered_posts
        except (ValueError, TypeError):
            pass

    # Tạo GeoJSON
    features = []
    for post in posts[:500]:  # Giới hạn 500 kết quả
        # Tính màu sắc dựa trên giá
        price_float = float(post.price)

        # Format giá - price trong DB đã là triệu đồng
        if price_float >= 1000000:
            # Trường hợp giá lưu bằng VNĐ (lớn)
            price_display = f'{price_float/1000000:.1f} triệu'.replace('.0 ', ' ')
        elif price_float >= 1000:
            # Trường hợp giá lưu bằng nghìn đồng
            price_display = f'{price_float/1000:.1f} triệu'.replace('.0 ', ' ')
        else:
            # Trường hợp giá lưu bằng triệu đồng (5, 7, 12...)
            price_display = f'{price_float:.1f} triệu'.replace('.0 ', ' ')

        # Chuẩn hóa giá về triệu đồng cho color coding
        if price_float >= 1000000:
            price_millions = price_float / 1000000
        elif price_float >= 1000:
            price_millions = price_float / 1000
        else:
            price_millions = price_float

        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [post.longitude, post.latitude]
            },
            'properties': {
                'id': post.id,
                'title': post.title,
                'price': price_millions,  # Giá chuẩn hóa thành triệu đồng
                'price_formatted': price_display,
                'area': post.area,
                'address': post.address or '',
                'province': post.province.name if post.province else '',
                'district': post.district.name if post.district else '',
                'ward': post.ward.name if post.ward else '',
                'category': post.get_category_display(),
                'category_code': post.category,
                'phone': post.phone_number or '',
                'image': post.image.url if post.image else '',
                'url': f'/post/{post.id}/',
                'created_at': post.created_at.strftime('%Y-%m-%d'),
                'features': post.features_list,
            }
        }
        features.append(feature)

    geojson = {
        'type': 'FeatureCollection',
        'features': features
    }

    return JsonResponse(geojson)


@require_http_methods(["GET"])
def poi_data_api(request):
    """
    API trả về dữ liệu POI dưới dạng GeoJSON (DISABLED)
    """
    # POI feature removed from frontend - return empty
    return JsonResponse({
        'type': 'FeatureCollection',
        'features': []
    })


@require_http_methods(["GET"])
def nearby_pois_api_disabled(request, post_id):
    """
    API POI nearby (DISABLED)
    """
    return JsonResponse({'pois': []})


@require_http_methods(["GET"])
def nearby_pois_api(request, post_id):
    # POI feature disabled - return empty
    return JsonResponse({'pois': []})


def _calculate_distance(lat1, lon1, lat2, lon2):
    # Calculate distance between two points using Haversine formula (km)
    R = 6371  # Bán kính Trái Đất (km)

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))

    return R * c
