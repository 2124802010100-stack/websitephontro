"""
Collaborative Filtering với ALS (Alternating Least Squares)
ĐÂY LÀ MACHINE LEARNING THẬT SỰ - có huấn luyện mô hình
"""
import os
import pickle
import numpy as np
from scipy.sparse import csr_matrix
from datetime import timedelta
from django.utils import timezone
from django.conf import settings


class ALSRecommender:
    """
    Collaborative Filtering với ALS (implicit feedback)
    - Xây ma trận user×item từ UserInteraction
    - Huấn luyện ALS model (thư viện implicit)
    - Dự đoán top-N cho user
    """

    def __init__(self, model_path=None):
        self.model = None
        self.user_mapping = {}  # user_id -> matrix_index
        self.item_mapping = {}  # post_id -> matrix_index
        self.reverse_item_mapping = {}  # matrix_index -> post_id
        self.user_item_matrix = None

        if model_path and os.path.exists(model_path):
            self.load_model(model_path)

    def build_interaction_matrix(self, days=90):
        """
        Xây ma trận user×item từ UserInteraction

        Returns:
            user_item_matrix: sparse CSR matrix shape (n_users, n_items)
        """
        from goiy_ai.models import UserInteraction

        cutoff = timezone.now() - timedelta(days=days)
        interactions = UserInteraction.objects.filter(
            created_at__gte=cutoff,
            user__isnull=False  # Chỉ lấy user đã đăng nhập
        ).exclude(
            interaction_type='unsave'
        ).select_related('user', 'post')

        print(f"📊 Đang xây ma trận từ {interactions.count()} interactions...")

        # Collect unique users & items
        users = set()
        items = set()
        for inter in interactions:
            users.add(inter.user_id)
            items.add(inter.post_id)

        # Build mappings
        self.user_mapping = {uid: idx for idx, uid in enumerate(sorted(users))}
        self.item_mapping = {iid: idx for idx, iid in enumerate(sorted(items))}
        self.reverse_item_mapping = {idx: iid for iid, idx in self.item_mapping.items()}

        print(f"   Users: {len(users)}, Items: {len(items)}")

        # Build sparse matrix
        row_ind = []
        col_ind = []
        data = []

        for inter in interactions:
            u_idx = self.user_mapping.get(inter.user_id)
            i_idx = self.item_mapping.get(inter.post_id)
            if u_idx is not None and i_idx is not None:
                row_ind.append(u_idx)
                col_ind.append(i_idx)
                # Dùng weight (view=1, save=3, contact=5, request=8)
                data.append(inter.weight)

        n_users = len(self.user_mapping)
        n_items = len(self.item_mapping)

        self.user_item_matrix = csr_matrix(
            (data, (row_ind, col_ind)),
            shape=(n_users, n_items),
            dtype=np.float32
        )

        print(f"✅ Ma trận: {self.user_item_matrix.shape}, density: {self.user_item_matrix.nnz / (n_users * n_items):.4%}")
        return self.user_item_matrix

    def train(self, factors=64, regularization=0.01, iterations=20, alpha=40):
        """
        Huấn luyện ALS model

        Args:
            factors: số chiều latent (default 64)
            regularization: L2 regularization
            iterations: số vòng lặp
            alpha: confidence weight cho implicit feedback
        """
        try:
            from implicit.als import AlternatingLeastSquares
        except ImportError:
            raise ImportError(
                "❌ Cần cài đặt thư viện 'implicit':\n"
                "   pip install implicit\n"
                "Hoặc nếu lỗi C++ compiler trên Windows:\n"
                "   pip install implicit --only-binary :all:"
            )

        if self.user_item_matrix is None:
            raise ValueError("Chưa có ma trận. Gọi build_interaction_matrix() trước.")

        print(f"\n🚀 Bắt đầu huấn luyện ALS:")
        print(f"   - Factors: {factors}")
        print(f"   - Regularization: {regularization}")
        print(f"   - Iterations: {iterations}")
        print(f"   - Alpha (confidence): {alpha}\n")

        # Initialize ALS
        self.model = AlternatingLeastSquares(
            factors=factors,
            regularization=regularization,
            iterations=iterations,
            calculate_training_loss=True,
            random_state=42
        )

        # ALS expects item×user matrix (transpose của user×item)
        item_user_matrix = self.user_item_matrix.T.tocsr()

        # Apply confidence scaling: C = 1 + alpha * R
        confidence_matrix = item_user_matrix.copy()
        confidence_matrix.data = 1.0 + alpha * confidence_matrix.data

        # Train
        self.model.fit(confidence_matrix, show_progress=True)

        print("✅ Huấn luyện hoàn tất!")

    def get_recommendations(self, user=None, user_id=None, limit=10, filter_interacted=True):
        """
        Lấy gợi ý cho user

        Returns:
            List[RentalPost]
        """
        if self.model is None:
            raise ValueError("Model chưa được train/load.")

        uid = user.id if user else user_id
        if not uid:
            return []

        u_idx = self.user_mapping.get(uid)
        if u_idx is None:
            # Cold start: user mới
            return self._cold_start_recommendations(limit)

        # Recommend
        item_indices, scores = self.model.recommend(
            userid=u_idx,
            user_items=self.user_item_matrix[u_idx],
            N=limit * 2,  # Lấy nhiều để filter
            filter_already_liked_items=filter_interacted,
            recalculate_user=True  # Tính vector user từ dữ liệu hiện tại để tránh lỗi chỉ số
        )

        # Convert indices → post_ids
        post_ids = [
            self.reverse_item_mapping[idx]
            for idx in item_indices
            if idx in self.reverse_item_mapping
        ]

        # Fetch active posts
        from website.models import RentalPost
        from django.db.models import Q

        now = timezone.now()
        posts = RentalPost.objects.filter(
            id__in=post_ids,
            is_approved=True,
            is_rented=False
        ).filter(
            Q(expired_at__isnull=True) | Q(expired_at__gt=now)
        )

        # Preserve order
        posts_dict = {p.id: p for p in posts}
        result = [posts_dict[pid] for pid in post_ids if pid in posts_dict]

        return result[:limit]

    def recommend_on_demand_24h(self, user=None, user_id=None, limit=10, filter_interacted=True):
        """Cố gắng lấy gợi ý CF an toàn cho 1 user.

        Quy trình:
        1) Thử dùng model đang load (nếu có). Nếu thành công → trả về.
        2) Nếu lỗi/chưa đủ dữ liệu hoặc user không có trong mapping →
           xây lại ma trận từ 24 giờ gần nhất và huấn luyện nhanh trong bộ nhớ,
           sau đó thử recommend lần nữa.
        3) Nếu vẫn lỗi hoặc dữ liệu quá ít → trả về [] để layer Hybrid fallback.
        """
        try:
            recs = self.get_recommendations(
                user=user,
                user_id=user_id,
                limit=limit,
                filter_interacted=filter_interacted,
            )
            # Nếu có kết quả, trả luôn
            if recs:
                return recs
        except Exception as e:
            # Tiếp tục thử on-demand
            print(f"⚠️  CF recommend lỗi (model hiện tại): {e}. Thử train on-demand 24h...")

        # On-demand rebuild 24h
        try:
            # Xây ma trận 24h
            matrix = self.build_interaction_matrix(days=1)
            # Kiểm tra dữ liệu tối thiểu
            if matrix.nnz < 10 or matrix.shape[0] < 2 or matrix.shape[1] < 2:
                print("⚠️  CF on-demand: dữ liệu 24h quá ít, bỏ qua CF")
                return []

            # Huấn luyện nhanh để giảm độ trễ
            self.train(factors=16, regularization=0.05, iterations=8, alpha=40)

            # Thử recommend lại bằng cách tính user vector trực tiếp để tránh lệch chỉ số
            recs = self._recommend_from_user_row(
                target_user=user,
                limit=limit,
                filter_interacted=filter_interacted,
            )
            if recs:
                return recs
            # Nếu không xây được hàng user phù hợp → trả [] để Hybrid fallback
            print("⚠️  CF on-demand: không tạo được user-row phù hợp, bỏ qua CF")
            return []
        except Exception as e:
            print(f"⚠️  CF on-demand cũng lỗi: {e}. Sẽ fallback sang Content-based")
            return []

    def _recommend_from_user_row(self, target_user, limit=10, filter_interacted=True):
        """Tạo 1 hàng ma trận cho user từ DB (24h) dựa trên item_mapping hiện tại
        và gọi recommend(recalculate_user=True) với userid giả lập để tránh phụ thuộc index.
        """
        if self.model is None or not self.item_mapping:
            return []

        # Lấy interactions 24h của user
        from goiy_ai.models import UserInteraction
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(days=1)
        interactions = UserInteraction.objects.filter(
            user=target_user,
            created_at__gte=cutoff
        ).exclude(interaction_type='unsave')

        if not interactions.exists():
            return []

        # Xây CSR row (1, n_items) dùng item_mapping hiện tại
        n_items = len(self.item_mapping)
        cols = []
        data = []
        for inter in interactions:
            i_idx = self.item_mapping.get(inter.post_id)
            if i_idx is not None:
                cols.append(i_idx)
                data.append(float(inter.weight))

        if not cols:
            return []

        from scipy.sparse import csr_matrix
        user_row = csr_matrix((data, ([0]*len(cols), cols)), shape=(1, n_items), dtype=np.float32)

        try:
            item_indices, scores = self.model.recommend(
                userid=0,  # userid giả lập, không dùng khi recalculate_user=True
                user_items=user_row,
                N=limit * 2,
                filter_already_liked_items=filter_interacted,
                recalculate_user=True,
            )
        except Exception:
            return []

        post_ids = [
            self.reverse_item_mapping[idx]
            for idx in item_indices
            if idx in self.reverse_item_mapping
        ]

        from website.models import RentalPost
        from django.db.models import Q
        now = timezone.now()
        posts = RentalPost.objects.filter(
            id__in=post_ids,
            is_approved=True,
            is_rented=False
        ).filter(
            Q(expired_at__isnull=True) | Q(expired_at__gt=now)
        )

        posts_dict = {p.id: p for p in posts}
        result = [posts_dict[pid] for pid in post_ids if pid in posts_dict]
        return result[:limit]

    def _cold_start_recommendations(self, limit):
        """Gợi ý cho user mới (chưa có trong ma trận)"""
        from website.models import RentalPost
        from django.db.models import Count, Q

        now = timezone.now()
        # Lấy bài phổ biến nhất
        popular = RentalPost.objects.filter(
            is_approved=True,
            is_rented=False
        ).filter(
            Q(expired_at__isnull=True) | Q(expired_at__gt=now)
        ).annotate(
            interaction_count=Count('ai_interactions')
        ).order_by('-interaction_count', '-created_at')[:limit]

        return list(popular)

    def get_similar_items(self, post_id, limit=10):
        """Tìm items tương tự post_id (theo learned embeddings)"""
        if self.model is None:
            raise ValueError("Model chưa được train/load.")

        i_idx = self.item_mapping.get(post_id)
        if i_idx is None:
            return []

        # Similar items
        similar_indices, scores = self.model.similar_items(
            itemid=i_idx,
            N=limit + 1
        )

        # Loại bỏ chính nó
        post_ids = [
            self.reverse_item_mapping[idx]
            for idx in similar_indices
            if idx != i_idx and idx in self.reverse_item_mapping
        ][:limit]

        # Fetch
        from website.models import RentalPost
        from django.db.models import Q

        now = timezone.now()
        posts = RentalPost.objects.filter(
            id__in=post_ids,
            is_approved=True,
            is_rented=False
        ).filter(
            Q(expired_at__isnull=True) | Q(expired_at__gt=now)
        )

        posts_dict = {p.id: p for p in posts}
        return [posts_dict[pid] for pid in post_ids if pid in posts_dict]

    def save_model(self, filepath):
        """Lưu model + mappings"""
        if self.model is None:
            raise ValueError("Không có model để lưu")

        data = {
            'model': self.model,
            'user_mapping': self.user_mapping,
            'item_mapping': self.item_mapping,
            'reverse_item_mapping': self.reverse_item_mapping,
            'user_item_matrix': self.user_item_matrix
        }

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)

        print(f"💾 Đã lưu model: {filepath}")

    def load_model(self, filepath):
        """Load model từ file"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Không tìm thấy: {filepath}")

        with open(filepath, 'rb') as f:
            data = pickle.load(f)

        self.model = data['model']
        self.user_mapping = data['user_mapping']
        self.item_mapping = data['item_mapping']
        self.reverse_item_mapping = data['reverse_item_mapping']
        self.user_item_matrix = data['user_item_matrix']

        print(f"📂 Đã load model: {filepath}")
        print(f"   Users: {len(self.user_mapping)}, Items: {len(self.item_mapping)}")
