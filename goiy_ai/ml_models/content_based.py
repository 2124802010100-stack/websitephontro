"""
Content-Based Filtering - Gợi ý dựa trên nội dung
Phân tích đặc điểm bài đăng: giá, diện tích, vị trí, features
"""
import numpy as np
from django.db.models import Q
from datetime import timedelta
from django.utils import timezone
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler


class ContentBasedRecommender:
    """
    Gợi ý phòng dựa trên đặc điểm nội dung:
    - Giá cả tương tự
    - Diện tích tương tự
    - Features giống nhau
    - Khu vực gần nhau (tỉnh, quận, phường)
    """

    def __init__(self):
        self.scaler = StandardScaler()

    def get_recommendations(self, user=None, post_id=None, limit=10, context=None):
        """
        Lấy danh sách gợi ý

        Args:
            user: User object (có thể None nếu chưa đăng nhập)
            post_id: ID bài đăng để tìm bài tương tự
            limit: Số lượng gợi ý
            context: Dict chứa thông tin bổ sung (session_id, filters...)

        Returns:
            List of RentalPost objects
        """
        from website.models import RentalPost
        from goiy_ai.models import UserInteraction, SearchHistory

        # Lấy các bài đăng đang hoạt động
        active_posts = self._get_active_posts()

        if not active_posts.exists():
            return []

        # Lưu context để dùng cho các hàm con (để có user/session_id)
        self.current_context = {
            'user': user,
            'session_id': context.get('session_id') if context else None
        }

        # TH1: Gợi ý dựa trên 1 bài cụ thể
        if post_id:
            try:
                target_post = RentalPost.objects.get(id=post_id)
                return self._recommend_similar_posts(target_post, active_posts, limit)
            except RentalPost.DoesNotExist:
                pass

        # TH2: Gợi ý dựa trên lịch sử user
        if user and user.is_authenticated:
            return self._recommend_for_user(user, active_posts, limit)

        # TH3: User chưa đăng nhập - dùng session
        if context and context.get('session_id'):
            return self._recommend_for_session(context['session_id'], active_posts, limit)

        # TH4: Fallback - bài mới nhất, được xem nhiều
        return self._get_popular_posts(active_posts, limit)

    def _get_active_posts(self):
        """Lấy các bài đăng đang hoạt động"""
        from website.models import RentalPost

        now = timezone.now()
        return RentalPost.objects.filter(
            is_approved=True,
            is_deleted=False,
            is_rented=False
        ).filter(
            Q(expired_at__isnull=True) | Q(expired_at__gt=now)
        ).select_related('province', 'district', 'ward')

    def _recommend_similar_posts(self, target_post, candidate_posts, limit):
        """
        Tìm các bài tương tự với target_post
        CHIẾN LƯỢC: Ưu tiên cùng địa điểm trước (1-2 bài), sau đó lọc theo giá/diện tích/đặc điểm
        """
        candidates = candidate_posts.exclude(id=target_post.id)

        if not candidates.exists():
            return []

        # BƯỚC 1: Tìm bài CÙNG ĐỊA ĐIỂM (Province + District)
        same_location_posts = []
        if target_post.province_id:
            same_location = candidates.filter(province_id=target_post.province_id)

            # Nếu có district, ưu tiên cùng district
            if target_post.district_id:
                same_district = same_location.filter(district_id=target_post.district_id)
                if same_district.exists():
                    # Tính điểm cho các bài cùng district
                    same_district_scores = []
                    for post in same_district[:10]:  # Lấy tối đa 10 để tính
                        score = self._calculate_similarity(target_post, post)
                        same_district_scores.append((post, score))

                    # Sắp xếp và lấy TOP 2 cùng district
                    same_district_scores.sort(key=lambda x: x[1], reverse=True)
                    same_location_posts = [post for post, score in same_district_scores[:2]]

            # Nếu chưa đủ 2 bài, lấy thêm từ cùng province (khác district)
            if len(same_location_posts) < 2:
                other_province_posts = same_location.exclude(
                    id__in=[p.id for p in same_location_posts]
                )

                other_province_scores = []
                for post in other_province_posts[:10]:
                    score = self._calculate_similarity(target_post, post)
                    other_province_scores.append((post, score))

                other_province_scores.sort(key=lambda x: x[1], reverse=True)
                needed = 2 - len(same_location_posts)
                same_location_posts.extend([post for post, score in other_province_scores[:needed]])

        # BƯỚC 2: Nếu đã đủ limit bằng bài cùng địa điểm, return luôn
        if len(same_location_posts) >= limit:
            return same_location_posts[:limit]

        # BƯỚC 3: Lấy bài còn lại theo giá/diện tích/đặc điểm (KHÁC ĐỊA ĐIỂM)
        remaining_needed = limit - len(same_location_posts)

        # Loại bỏ bài đã chọn và bài cùng địa điểm
        other_candidates = candidates.exclude(
            id__in=[p.id for p in same_location_posts]
        )

        # Tính điểm similarity cho các bài còn lại
        other_scores = []
        for post in other_candidates:
            score = self._calculate_similarity(target_post, post)
            other_scores.append((post, score))

        # Sắp xếp theo điểm (giá/diện tích/features sẽ được tính trong _calculate_similarity)
        other_scores.sort(key=lambda x: x[1], reverse=True)
        other_posts = [post for post, score in other_scores[:remaining_needed]]

        # KẾT HỢP: 1-2 bài cùng địa điểm + bài khác địa điểm
        result = same_location_posts + other_posts

        return result[:limit]

    def _recommend_for_user(self, user, candidate_posts, limit):
        """Gợi ý dựa trên hành vi của user đã đăng nhập"""
        from goiy_ai.models import UserInteraction, SearchHistory
        from django.db.models import Sum

        # 1. Lấy các bài user đã tương tác gần đây (24 giờ)
        recent_interactions = UserInteraction.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).exclude(
            interaction_type='unsave'  # Loại bỏ các bài đã unsave
        ).select_related('post').order_by('-created_at')[:50]

        if not recent_interactions.exists():
            # Nếu chưa có tương tác, dùng lịch sử tìm kiếm
            return self._recommend_from_search_history(user, candidate_posts, limit)

        # 2. Xây dựng profile user
        user_profile = self._build_user_profile(recent_interactions)

        # 3. Tìm bài user tương tác NHIỀU NHẤT (save/contact có trọng số cao)
        post_weights = {}
        for interaction in recent_interactions:
            post_id = interaction.post_id
            weight = interaction.weight  # view=1, save=3, contact=5, request=8
            post_weights[post_id] = post_weights.get(post_id, 0) + weight

        # Sắp xếp theo trọng số
        top_interacted_posts = sorted(post_weights.items(), key=lambda x: x[1], reverse=True)[:3]

        # 4. CHIẾN LƯỢC MỚI:
        # - GIỮ LẠI TOP 3 bài được quan tâm NHẤT để user dễ tìm lại
        # - Loại bỏ các bài còn lại (đã xem nhưng ít quan tâm)
        keep_post_ids = set()
        if top_interacted_posts:
            # Giữ TOP 3 bài có weight cao nhất (không phân biệt weight bao nhiêu)
            # Miễn là user đã tương tác → đáng quan tâm
            for post_id, weight in top_interacted_posts:
                keep_post_ids.add(post_id)

        # Danh sách bài cần loại bỏ (đã xem nhưng không quan tâm lắm)
        interacted_post_ids = set(recent_interactions.values_list('post_id', flat=True))
        exclude_post_ids = interacted_post_ids - keep_post_ids

        # 5. Nếu có bài được save/contact nhiều, gợi ý BÀI TƯƠNG TỰ
        similar_posts = []
        top_posts_to_show = []  # Danh sách TOP bài để hiển thị trực tiếp

        if top_interacted_posts and top_interacted_posts[0][1] >= 1.0:  # Giảm từ 3.0 xuống 1.0 để dễ trigger
            from website.models import RentalPost
            import logging
            logger = logging.getLogger(__name__)

            logger.warning(f"🔍 User có {len(top_interacted_posts)} bài tương tác nhiều:")
            for post_id, weight in top_interacted_posts[:3]:
                logger.warning(f"   Post {post_id}: weight={weight}")

            # THÊM: Lấy TOP 3 bài để hiển thị trực tiếp
            for post_id, weight in top_interacted_posts[:3]:
                try:
                    target_post = RentalPost.objects.get(id=post_id)
                    # Kiểm tra xem bài còn hợp lệ không (đã duyệt, chưa thuê, chưa hết hạn)
                    if target_post in candidate_posts:
                        top_posts_to_show.append(target_post)
                        logger.warning(f"   ✅ Giữ lại bài TOP: [ID:{post_id}] {target_post.title[:30]}")
                except:
                    pass

            for post_id, weight in top_interacted_posts[:2]:  # Lấy 2 bài top
                try:
                    # Lấy bài từ DATABASE gốc, không phải từ candidate_posts (đã bị filter)
                    target_post = RentalPost.objects.get(id=post_id)
                    logger.warning(f"   → Tìm bài tương tự với Post {post_id}: {target_post.title[:30]}")

                    # Tìm bài tương tự (loại bỏ bài đã xem NHƯNG GIỮ BÀI QUAN TÂM)
                    similar = self._recommend_similar_posts(
                        target_post,
                        candidate_posts.exclude(id__in=exclude_post_ids | set([p.id for p in top_posts_to_show])),  # Loại cả TOP posts
                        limit=3
                    )

                    logger.warning(f"   → Tìm thấy {len(similar)} bài tương tự")
                    for idx, s in enumerate(similar, 1):
                        logger.warning(f"      {idx}. [ID:{s.id}] {s.title[:30]}")

                    similar_posts.extend(similar)
                except Exception as e:
                    # Debug: In lỗi nếu có
                    logger.warning(f"   ❌ Cannot find similar posts for post {post_id}: {e}")
                    pass

        # 6. Tính điểm cho các bài còn lại dựa trên user profile
        scores = []
        excluded_ids = exclude_post_ids | set([p.id for p in (similar_posts + top_posts_to_show)])
        for post in candidate_posts.exclude(id__in=excluded_ids):  # Loại bỏ bài ít quan tâm và đã có
            score = self._match_user_profile(user_profile, post)
            scores.append((post, score))

        # Sắp xếp theo điểm
        scores.sort(key=lambda x: x[1], reverse=True)
        profile_based = [post for post, score in scores]

        # 7. KẾT HỢP: TOP posts (bài user spam) + similar posts + profile-based
        # GIỚI HẠN: Tối đa 3 bài cùng tỉnh để đa dạng hóa
        # NẾU KHÔNG ĐỦ 3 bài cùng tỉnh → lấy bài tỉnh khác giống về giá/diện tích/loại
        result = []
        province_count = {}  # Đếm số bài mỗi tỉnh
        MAX_SAME_PROVINCE = 3  # Giới hạn tối đa 3 bài/tỉnh

        # Helper function để thêm bài với kiểm tra giới hạn tỉnh
        def add_post_with_limit(post):
            prov_id = post.province_id or 'none'
            current_count = province_count.get(prov_id, 0)

            if current_count < MAX_SAME_PROVINCE:
                result.append(post)
                province_count[prov_id] = current_count + 1
                return True
            return False

        # Ưu tiên: TOP bài user quan tâm (hiển thị đầu tiên)
        for post in top_posts_to_show[:2]:
            if len(result) >= limit:
                break
            add_post_with_limit(post)

        # Sau đó: Bài tương tự (ưu tiên đa dạng tỉnh)
        remaining_limit = limit - len(result)
        similar_count = int(remaining_limit * 0.6)

        for post in similar_posts:
            if len(result) >= len(top_posts_to_show[:2]) + similar_count:
                break
            if post not in result:
                add_post_with_limit(post)

        # Cuối cùng: Bài dựa trên profile
        for post in profile_based:
            if len(result) >= limit:
                break
            if post not in result:
                add_post_with_limit(post)

        # BƯỚC BỔ SUNG: Nếu vẫn chưa đủ limit, tìm bài GIỐNG VỀ GIÁ/DIỆN TÍCH ở tỉnh khác
        if len(result) < limit and top_posts_to_show:
            import logging
            logger = logging.getLogger(__name__)

            # Lấy bài TOP đầu tiên làm mẫu
            reference_post = top_posts_to_show[0]
            ref_price = float(reference_post.price)
            ref_area = reference_post.area
            ref_category = reference_post.category

            # Tìm bài tương tự về giá/diện tích/loại (không giới hạn tỉnh)
            similar_characteristics = []
            for post in candidate_posts:
                # Bỏ qua bài đã có trong result
                if post in result:
                    continue

                # Tính điểm tương đồng về giá/diện tích/loại
                score = 0.0

                # 1. Giá gần nhau (±30%)
                post_price = float(post.price)
                if ref_price > 0:
                    price_diff_ratio = abs(post_price - ref_price) / ref_price
                    if price_diff_ratio <= 0.3:
                        score += 3.0
                    elif price_diff_ratio <= 0.5:
                        score += 1.5

                # 2. Diện tích gần nhau (±30%)
                if ref_area > 0:
                    area_diff_ratio = abs(post.area - ref_area) / ref_area
                    if area_diff_ratio <= 0.3:
                        score += 2.0
                    elif area_diff_ratio <= 0.5:
                        score += 1.0

                # 3. Cùng loại phòng
                if post.category == ref_category:
                    score += 2.0

                if score > 0:
                    similar_characteristics.append((post, score))

            # Sắp xếp theo điểm tương đồng
            similar_characteristics.sort(key=lambda x: x[1], reverse=True)

            # Thêm vào kết quả (không giới hạn tỉnh nữa vì đã hết bài cùng tỉnh)
            added = 0
            for post, score in similar_characteristics:
                if len(result) >= limit:
                    break
                if post not in result:
                    result.append(post)
                    added += 1
                    logger.warning(f"   💡 Bổ sung bài tỉnh khác giống giá/DT: [ID:{post.id}] {post.title[:30]} (score={score:.1f})")

            if added > 0:
                logger.warning(f"   ✅ Đã bổ sung {added} bài tỉnh khác giống về đặc điểm")

        return result[:limit]

    def _recommend_for_session(self, session_id, candidate_posts, limit):
        """Gợi ý cho user chưa đăng nhập dựa trên session"""
        from goiy_ai.models import UserInteraction, SearchHistory

        # Lấy interactions từ session này
        recent_interactions = UserInteraction.objects.filter(
            session_id=session_id,
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).select_related('post').order_by('-created_at')[:20]

        if not recent_interactions.exists():
            # Dùng search history
            recent_searches = SearchHistory.objects.filter(
                session_id=session_id,
                searched_at__gte=timezone.now() - timedelta(hours=24)
            ).order_by('-searched_at')[:5]

            if recent_searches.exists():
                return self._recommend_from_search_list(recent_searches, candidate_posts, limit)

            return self._get_popular_posts(candidate_posts, limit)

        # Xây dựng profile từ interactions
        user_profile = self._build_user_profile(recent_interactions)
        interacted_post_ids = set(recent_interactions.values_list('post_id', flat=True))

        scores = []
        for post in candidate_posts.exclude(id__in=interacted_post_ids):
            score = self._match_user_profile(user_profile, post)
            scores.append((post, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [post for post, score in scores[:limit]]

    def _recommend_from_search_history(self, user, candidate_posts, limit):
        """Gợi ý dựa trên lịch sử tìm kiếm của user (24 giờ)"""
        from goiy_ai.models import SearchHistory

        recent_searches = SearchHistory.objects.filter(
            user=user,
            searched_at__gte=timezone.now() - timedelta(hours=24)
        ).order_by('-searched_at')[:10]

        if not recent_searches.exists():
            return self._get_popular_posts(candidate_posts, limit)

        return self._recommend_from_search_list(recent_searches, candidate_posts, limit)

    def _recommend_from_search_list(self, searches, candidate_posts, limit):
        """Gợi ý từ danh sách searches"""
        # Tạo profile từ search history
        search_profile = {
            'categories': [],
            'provinces': [],
            'districts': [],
            'price_ranges': [],
            'area_ranges': [],
            'features': set()
        }

        for search in searches:
            if search.category:
                search_profile['categories'].append(search.category)
            if search.province_id:
                search_profile['provinces'].append(search.province_id)
            if search.district_id:
                search_profile['districts'].append(search.district_id)

            if search.min_price or search.max_price:
                search_profile['price_ranges'].append({
                    'min': float(search.min_price) if search.min_price else 0,
                    'max': float(search.max_price) if search.max_price else float('inf')
                })

            if search.min_area or search.max_area:
                search_profile['area_ranges'].append({
                    'min': search.min_area if search.min_area else 0,
                    'max': search.max_area if search.max_area else float('inf')
                })

            if search.features:
                search_profile['features'].update(search.features)

        # Tính điểm cho từng bài
        scores = []
        for post in candidate_posts:
            score = self._match_search_profile(search_profile, post)
            scores.append((post, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [post for post, score in scores[:limit]]

    def _get_popular_posts(self, candidate_posts, limit):
        """
        Lấy các bài phổ biến (nhiều lượt xem, mới nhất)

        QUAN TRỌNG: Thêm randomization để mỗi user nhận được gợi ý khác nhau
        ngay cả khi chưa có interaction history
        """
        from django.db.models import Count
        import random
        import hashlib

        # Tạo seed KHÁC NHAU cho mỗi user/session
        # QUAN TRỌNG: Thêm timestamp để mỗi lần request có seed khác
        import time
        seed_string = ""
        if hasattr(self, 'current_context'):
            user = self.current_context.get('user')
            session_id = self.current_context.get('session_id')

            if user and user.is_authenticated:
                # Dùng user_id + timestamp (làm tròn 5 phút để cache 5 phút)
                time_bucket = int(time.time() / 300)  # Thay đổi mỗi 5 phút
                seed_string = f"user_{user.id}_{time_bucket}"
            elif session_id:
                # Dùng session_id + timestamp
                time_bucket = int(time.time() / 300)
                seed_string = f"session_{session_id}_{time_bucket}"

        # Nếu không có context, dùng timestamp để random
        if not seed_string:
            seed_string = str(time.time())

        # Chuyển seed_string thành số
        seed = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
        random.seed(seed)

        # Lấy pool lớn hơn để có thể random
        pool_size = limit * 10  # Tăng từ 5 lên 10 để có pool đa dạng hơn

        popular_posts = list(candidate_posts.annotate(
            view_count=Count('ai_views')
        ).order_by('-view_count', '-created_at')[:pool_size])

        if not popular_posts:
            return []

        # DIVERSIFICATION: Chia thành các nhóm theo category/location
        categorized = {}
        for post in popular_posts:
            key = f"{post.category}_{post.province_id}"
            if key not in categorized:
                categorized[key] = []
            categorized[key].append(post)

        # Lấy đa dạng từ mỗi nhóm
        result = []
        categories = list(categorized.keys())
        random.shuffle(categories)  # Random thứ tự categories (với seed khác nhau)

        # Round-robin: lấy lần lượt từ mỗi category
        idx = 0
        while len(result) < limit and idx < len(popular_posts):
            for category_key in categories:
                if len(categorized[category_key]) > 0:
                    post = categorized[category_key].pop(0)
                    if post not in result:
                        result.append(post)
                        if len(result) >= limit:
                            break
            idx += 1

        # Nếu vẫn chưa đủ, lấy random từ phần còn lại
        if len(result) < limit:
            remaining = [p for p in popular_posts if p not in result]
            random.shuffle(remaining)
            result.extend(remaining[:limit - len(result)])

        # Reset random seed về None để không ảnh hưởng code khác
        random.seed(None)

        return result[:limit]

    def _build_user_profile(self, interactions):
        """Xây dựng profile user từ các tương tác"""
        profile = {
            'categories': [],
            'provinces': [],
            'districts': [],
            'prices': [],
            'areas': [],
            'features': [],
            'weights': []
        }

        for interaction in interactions:
            post = interaction.post
            weight = interaction.weight

            profile['categories'].append(post.category)
            if post.province_id:
                profile['provinces'].append(post.province_id)
            if post.district_id:
                profile['districts'].append(post.district_id)
            profile['prices'].append(float(post.price))
            profile['areas'].append(post.area)
            if post.features:
                profile['features'].extend(list(post.features))
            profile['weights'].append(weight)

        return profile

    def _match_user_profile(self, user_profile, post):
        """Tính điểm khớp giữa user profile và post"""
        score = 0.0

        # 1. Điểm category (trọng số 2.0)
        if post.category in user_profile['categories']:
            category_freq = user_profile['categories'].count(post.category)
            score += category_freq * 2.0

        # 2. Điểm vị trí (trọng số 1.5-2.0)
        if user_profile['provinces']:
            if post.province_id in user_profile['provinces']:
                score += 1.5
            if post.district_id in user_profile['districts']:
                score += 2.0

        # 3. Điểm giá (trọng số 3.0)
        if user_profile['prices']:
            avg_price = np.mean(user_profile['prices'])
            std_price = np.std(user_profile['prices']) if len(user_profile['prices']) > 1 else avg_price * 0.3

            post_price = float(post.price)
            price_diff = abs(post_price - avg_price)

            # Điểm cao nếu trong khoảng 1 std
            if price_diff <= std_price:
                score += 3.0
            elif price_diff <= 2 * std_price:
                score += 1.5
            else:
                # Phạt nếu giá chênh lệch quá xa
                penalty = min((price_diff - 2 * std_price) / avg_price * 2, 2.0)
                score -= penalty

        # 4. Điểm diện tích (trọng số 2.0)
        if user_profile['areas']:
            avg_area = np.mean(user_profile['areas'])
            std_area = np.std(user_profile['areas']) if len(user_profile['areas']) > 1 else avg_area * 0.3

            area_diff = abs(post.area - avg_area)

            if area_diff <= std_area:
                score += 2.0
            elif area_diff <= 2 * std_area:
                score += 1.0

        # 5. Điểm features (trọng số 0.5 mỗi feature)
        if user_profile['features'] and post.features:
            post_features = set(post.features)
            user_features_set = set(user_profile['features'])
            matching_features = post_features & user_features_set
            score += len(matching_features) * 0.5

        return max(score, 0.0)  # Không cho điểm âm

    def _match_search_profile(self, search_profile, post):
        """Tính điểm khớp giữa search profile và post"""
        score = 0.0

        # 1. Category
        if search_profile['categories'] and post.category in search_profile['categories']:
            score += 3.0

        # 2. Vị trí
        if search_profile['provinces'] and post.province_id in search_profile['provinces']:
            score += 2.0
        if search_profile['districts'] and post.district_id in search_profile['districts']:
            score += 2.5

        # 3. Giá
        post_price = float(post.price)
        if search_profile['price_ranges']:
            price_match = False
            for price_range in search_profile['price_ranges']:
                if price_range['min'] <= post_price <= price_range['max']:
                    price_match = True
                    score += 3.0
                    break

            if not price_match:
                # Phạt nếu nằm ngoài tất cả các range
                score -= 1.0

        # 4. Diện tích
        if search_profile['area_ranges']:
            area_match = False
            for area_range in search_profile['area_ranges']:
                if area_range['min'] <= post.area <= area_range['max']:
                    area_match = True
                    score += 2.0
                    break

        # 5. Features
        if search_profile['features'] and post.features:
            matching_features = len(set(post.features) & search_profile['features'])
            score += matching_features * 0.5

        return max(score, 0.0)

    def _calculate_similarity(self, post1, post2):
        """Tính độ tương đồng giữa 2 bài đăng"""
        score = 0.0

        # 1. Category giống nhau
        if post1.category == post2.category:
            score += 2.5

        # 2. Vị trí (TĂNG TRỌNG SỐ ĐỂ ƯU TIÊN CÙNG KHU VỰC)
        if post1.province_id == post2.province_id:
            score += 4.0  # Tăng từ 2.0 → 4.0
            if post1.district_id == post2.district_id:
                score += 3.0  # Tăng từ 2.0 → 3.0
                if post1.ward_id == post2.ward_id:
                    score += 2.0  # Tăng từ 1.0 → 2.0

        # 3. Giá gần nhau (±30%)
        price1 = float(post1.price)
        price2 = float(post2.price)
        if price1 > 0:
            price_diff_ratio = abs(price1 - price2) / price1
            if price_diff_ratio <= 0.2:
                score += 2.5  # Giảm từ 3.0 → 2.5
            elif price_diff_ratio <= 0.3:
                score += 1.5  # Giảm từ 2.0 → 1.5
            elif price_diff_ratio <= 0.5:
                score += 0.8

        # 4. Diện tích gần nhau (±30%)
        if post1.area > 0:
            area_diff_ratio = abs(post1.area - post2.area) / post1.area
            if area_diff_ratio <= 0.2:
                score += 1.5  # Giảm từ 2.0 → 1.5
            elif area_diff_ratio <= 0.3:
                score += 1.0
            elif area_diff_ratio <= 0.5:
                score += 0.5

        # 5. Features giống nhau
        if post1.features and post2.features:
            features1 = set(post1.features)
            features2 = set(post2.features)
            common_features = features1 & features2
            score += len(common_features) * 0.6

        return score
