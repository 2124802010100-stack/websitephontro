"""
Hybrid Recommender - Kết hợp Collaborative Filtering + Content-based
ĐÂY LÀ HỆ THỐNG HYBRID (ML + HEURISTIC)
"""
import os
from django.conf import settings


class HybridRecommender:
    """
    Hybrid Recommendation System
    Trộn điểm từ:
    - Collaborative Filtering (ALS) - ML model đã train
    - Content-based Filtering - rule-based similarity

    Weight: 50% CF + 50% Content-based (có thể điều chỉnh)
    """

    def __init__(self, cf_model_path=None, cf_weight=0.5, content_weight=0.5):
        """
        Args:
            cf_model_path: đường dẫn model CF (ALS). Nếu None, dùng default path
            cf_weight: trọng số cho CF (default 0.6)
            content_weight: trọng số cho Content-based (default 0.4)
        """
        self.cf_weight = cf_weight
        self.content_weight = content_weight

    # Initialize Content-based recommender
        from goiy_ai.ml_models.content_based import ContentBasedRecommender
        self.content_recommender = ContentBasedRecommender()

        # Initialize CF recommender (ALS)
        from goiy_ai.ml_models.cf_als import ALSRecommender

        if cf_model_path is None:
            # Default path
            cf_model_path = os.path.join(
                settings.BASE_DIR,
                'goiy_ai',
                'ml_models',
                'trained_models',
                'cf_als_model.pkl'
            )

        # Nếu cấu hình yêu cầu chỉ dùng Content-based → tắt CF hoàn toàn
        if getattr(settings, 'AI_FORCE_CONTENT_ONLY', False):
            self.cf_recommender = None
            # print("Hybrid: AI_FORCE_CONTENT_ONLY=True -> chi dung Content-based")
            return

        # Load CF model nếu có
        self.cf_recommender = None
        if os.path.exists(cf_model_path):
            try:
                self.cf_recommender = ALSRecommender(model_path=cf_model_path)
                print(f"✅ Hybrid: Đã load CF model từ {cf_model_path}")
            except Exception as e:
                print(f"⚠️  Hybrid: Không load được CF model: {e}")
                print(f"   Sẽ chỉ dùng Content-based")
        else:
            print(f"⚠️  Hybrid: Không tìm thấy CF model tại {cf_model_path}")
            print(f"   Sẽ chỉ dùng Content-based")

    def get_recommendations(self, user=None, post_id=None, limit=10, context=None):
        """
        Lấy gợi ý hybrid

        Args:
            user: User object
            post_id: nếu có, tìm similar posts
            limit: số lượng gợi ý
            context: dict chứa session_id, filters...

        Returns:
            List[RentalPost]
        """
        # Nếu không có CF model, fallback sang Content-based
        if self.cf_recommender is None:
            return self.content_recommender.get_recommendations(
                user=user,
                post_id=post_id,
                limit=limit,
                context=context
            )

        # Nếu có post_id (tìm similar), ưu tiên Content-based
        if post_id:
            return self.content_recommender.get_recommendations(
                user=user,
                post_id=post_id,
                limit=limit,
                context=context
            )

        # Nếu user chưa đăng nhập, dùng Content-based
        if not user or not user.is_authenticated:
            return self.content_recommender.get_recommendations(
                user=user,
                post_id=post_id,
                limit=limit,
                context=context
            )

        # HYBRID: Trộn CF + Content-based
        return self._hybrid_recommendations(user, limit, context)

    def _hybrid_recommendations(self, user, limit, context):
        """
        Trộn kết quả từ CF và Content-based
        """
        # 1. Lấy CF recommendations
        try:
            # Dùng đường an toàn: nếu model hiện tại lỗi sẽ train on-demand 24h
            cf_posts = self.cf_recommender.recommend_on_demand_24h(
                user=user,
                limit=limit * 3,  # Lấy nhiều hơn để trộn
                filter_interacted=True,
            )
        except Exception as e:
            print(f"⚠️  CF error: {e}, fallback sang Content-based")
            cf_posts = []

        # 2. Lấy Content-based recommendations
        content_posts = self.content_recommender.get_recommendations(
            user=user,
            limit=limit * 3,
            context=context
        )

        # 3. Nếu một trong hai rỗng, dùng cái còn lại
        if not cf_posts:
            return content_posts[:limit]
        if not content_posts:
            return cf_posts[:limit]

        # 4. Trộn theo tỷ lệ
        cf_count = int(limit * self.cf_weight)
        content_count = limit - cf_count

        # Lấy từ CF trước
        result = []
        cf_ids_used = set()

        for post in cf_posts[:cf_count]:
            result.append(post)
            cf_ids_used.add(post.id)

        # Lấy từ Content-based (không trùng)
        for post in content_posts:
            if post.id not in cf_ids_used:
                result.append(post)
                if len(result) >= limit:
                    break

        # Nếu vẫn chưa đủ, lấy thêm từ CF
        if len(result) < limit:
            for post in cf_posts[cf_count:]:
                if post.id not in [p.id for p in result]:
                    result.append(post)
                    if len(result) >= limit:
                        break

        return result[:limit]

    def adjust_weights(self, cf_weight, content_weight):
        """
        Điều chỉnh trọng số động

        Args:
            cf_weight: trọng số mới cho CF (0.0 - 1.0)
            content_weight: trọng số mới cho Content-based (0.0 - 1.0)
        """
        total = cf_weight + content_weight
        if total == 0:
            raise ValueError("Tổng trọng số phải > 0")

        # Normalize
        self.cf_weight = cf_weight / total
        self.content_weight = content_weight / total

        print(f"⚙️  Đã cập nhật weights: CF={self.cf_weight:.2f}, Content={self.content_weight:.2f}")
