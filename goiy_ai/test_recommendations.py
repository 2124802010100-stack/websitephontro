"""
Script test nhanh hệ thống gợi ý AI
Chạy: python goiy_ai/test_recommendations.py
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PhongTro.settings')
django.setup()

from django.contrib.auth.models import User
from website.models import RentalPost
from goiy_ai.models import UserInteraction, PostView, SearchHistory
from goiy_ai.ml_models.hybrid import HybridRecommender


def test_recommendations():
    print("=" * 60)
    print("TEST HỆ THỐNG GỢI Ý AI")
    print("=" * 60)

    # 1. Kiểm tra dữ liệu
    print("\n1. Kiểm tra dữ liệu:")
    print(f"   - Số bài đăng: {RentalPost.objects.filter(is_approved=True).count()}")
    print(f"   - Số lượt xem: {PostView.objects.count()}")
    print(f"   - Số tương tác: {UserInteraction.objects.count()}")
    print(f"   - Số lịch sử tìm kiếm: {SearchHistory.objects.count()}")

    # 2. Test recommender
    print("\n2. Test Hybrid Recommender:")
    recommender = HybridRecommender()

    # Test cho anonymous user
    print("\n   a) Gợi ý cho anonymous user:")
    recommendations = recommender.get_recommendations(
        user=None,
        limit=5,
        context={'session_id': 'test_session_123'},
        strategy='weighted'
    )
    print(f"      - Số gợi ý: {len(recommendations)}")
    for i, post in enumerate(recommendations[:3], 1):
        print(f"      {i}. {post.title[:50]} - {post.price} VNĐ")

    # Test cho user đã đăng nhập
    print("\n   b) Gợi ý cho user đã đăng nhập:")
    try:
        test_user = User.objects.first()
        if test_user:
            recommendations = recommender.get_recommendations(
                user=test_user,
                limit=5,
                strategy='switching'
            )
            print(f"      - User: {test_user.username}")
            print(f"      - Số gợi ý: {len(recommendations)}")
            for i, post in enumerate(recommendations[:3], 1):
                print(f"      {i}. {post.title[:50]} - {post.price} VNĐ")
        else:
            print("      - Không có user nào trong DB")
    except Exception as e:
        print(f"      - Lỗi: {e}")

    # 3. Test similar posts
    print("\n3. Test tìm bài tương tự:")
    try:
        sample_post = RentalPost.objects.filter(is_approved=True).first()
        if sample_post:
            similar = recommender.get_similar_posts(
                post_id=sample_post.id,
                limit=3
            )
            print(f"   - Bài gốc: {sample_post.title[:50]}")
            print(f"   - Số bài tương tự: {len(similar)}")
            for i, post in enumerate(similar, 1):
                print(f"     {i}. {post.title[:50]} - {post.price} VNĐ")
        else:
            print("   - Không có bài đăng nào")
    except Exception as e:
        print(f"   - Lỗi: {e}")

    # 4. Test các strategies
    print("\n4. Test các strategies:")
    strategies = ['weighted', 'switching', 'mixed']
    for strategy in strategies:
        try:
            recs = recommender.get_recommendations(
                user=None,
                limit=3,
                context={'session_id': 'test'},
                strategy=strategy
            )
            print(f"   - {strategy}: {len(recs)} gợi ý")
        except Exception as e:
            print(f"   - {strategy}: Lỗi - {e}")

    print("\n" + "=" * 60)
    print("TEST HOÀN TẤT!")
    print("=" * 60)
    print("\nGợi ý:")
    print("1. Truy cập http://127.0.0.1:8000/ để xem gợi ý trên trang chủ")
    print("2. Click vào các bài đăng để tạo tracking data")
    print("3. Thực hiện tìm kiếm để tạo search history")
    print("4. Lưu một số bài để tạo interactions")
    print("5. Sau đó gợi ý sẽ chính xác hơn!")
    print()


if __name__ == '__main__':
    test_recommendations()
