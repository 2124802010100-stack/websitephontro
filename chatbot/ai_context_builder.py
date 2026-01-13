"""
AI Context Builder - Xây dựng context từ database thực tế
Module này lấy dữ liệu từ DB và format thành context cho chatbot AI (Grop)
"""

from django.db.models import Q, Count, Avg
from django.utils import timezone
from datetime import timedelta
from website.models import RentalPost, CustomerProfile, RentalRequest
from goiy_ai.models import SearchHistory, UserInteraction
import logging

logger = logging.getLogger(__name__)


class AIContextBuilder:
    """Xây dựng context thông minh cho chatbot AI từ database"""

    def __init__(self, user=None, session_key=None, session=None):
        self.user = user
        self.session_key = session_key
        self.session = session
        self.context = []

    def build_context(self, query: str) -> str:
        """Xây dựng context đầy đủ dựa trên câu hỏi của user"""

        # 1. Thông tin về database hiện tại
        self._add_database_stats()

        # 1.1 RAG: thêm các trích đoạn liên quan từ tài liệu & DB (nhẹ, không phụ thuộc lớn)
        try:
            from chatbot.performance_optimizer import lazy_rag_loader, FastResponseOptimizer
            from chatbot.views import normalize_text

            # Skip RAG for simple queries to speed up
            if FastResponseOptimizer.should_skip_rag(query):
                rag_hits = []
            else:
                rag_hits = lazy_rag_loader.query(query, k=5)
            if rag_hits:
                # Nếu người dùng có nêu tỉnh/thành, chỉ giữ lại các POST trùng tỉnh (DOC/MD vẫn giữ)
                province = self.get_province_from_query(query)
                if province:
                    prov_norm = normalize_text(province.name)
                    filtered = []
                    for h in rag_hits:
                        if h.get('kind') == 'md':
                            filtered.append(h)
                            continue
                        # kind == 'post' → kiểm tra tỉnh trong tiêu đề/snippet/text ngắn
                        txt = f"{h.get('title','')} {h.get('snippet','')} {h.get('url','')}"
                        if prov_norm in normalize_text(txt):
                            filtered.append(h)
                    rag_hits = filtered

                if rag_hits:
                    lines = ["## 📚 TRÍCH ĐOẠN LIÊN QUAN (RAG):\n"]
                    for h in rag_hits:
                        prefix = "[DOC]" if h.get('kind') == 'md' else "[POST]"
                        lines.append(f"- {prefix} {h.get('title','')} → {h.get('url','')}")
                        snippet = (h.get('snippet') or '').strip().replace('\n', ' ')
                        if snippet:
                            lines.append(f"   > {snippet[:220]}")
                    self.context.append("\n".join(lines))
        except Exception:
            pass

        # 1.5. Check if we already have post context from conversation
        has_post_context = self._add_conversation_post_context(query)

        # 2. Phân tích query để lấy dữ liệu liên quan
        # Skip search if already have post context to avoid location parsing conflicts
        if self._is_search_query(query) and not has_post_context:
            self._add_search_results(query)

        # 2.1. Thêm top phòng giá rẻ (skip if already showing a specific post)
        if not has_post_context:
            self._add_cheapest_section(query)

        # 3. Lịch sử tìm kiếm của user (nếu có)
        if self.user or self.session_key:
            self._add_user_history()

        # 4. Top phòng hot (24h gần đây)
        self._add_trending_posts()

        return "\n\n".join(self.context)

    def _add_conversation_post_context(self, query: str) -> bool:
        """
        Thêm thông tin chi tiết về phòng từ lịch sử hội thoại
        Giúp chatbot nhớ phòng đang được hỏi

        Returns:
            True nếu đã tìm thấy và thêm post context, False nếu không
        """
        if not self.session:
            return False

        # Check if this is a follow-up question about features or referencing current post
        follow_up_patterns = [
            # Questions
            'có', 'không', 'thế nào', 'như thế nào', 'ra sao',
            # Specific features
            'máy lạnh', 'wifi', 'gác lửng', 'wc', 'toilet', 'bếp',
            'thang máy', 'ban công', 'sân phơi', 'giường', 'bàn ghế',
            'tủ lạnh', 'máy giặt', 'nước nóng', 'hầm', 'bảo vệ',
            # References to current post
            'căn hộ này', 'phòng này', 'nhà này', 'nó', 'đó',
            'can ho nay', 'phong nay', 'nha nay',
            # Direct ID reference
            'id', 'mã số',
        ]

        query_lower = query.lower()
        is_follow_up = any(pattern in query_lower for pattern in follow_up_patterns)

        if not is_follow_up:
            return False

        # Extract last mentioned post from conversation history
        try:
            from chatbot.vietnamese_parser import ConversationMemory
            history = ConversationMemory.get_history(self.session)

            if not history:
                logger.debug("[PostContext] No conversation history available")
                return False

            logger.info(f"[PostContext] Scanning {len(history)} exchanges for post ID...")
            # Look for post ID in recent responses (scan more exchanges to avoid forgetting)
            import re
            for i, exchange in enumerate(reversed(history[-10:])):  # Last 10 exchanges (was 3)
                bot_response = exchange.get('bot', '')
                logger.debug(f"[PostContext] Exchange {i+1} bot response: {bot_response[:100]}")

                # Try to extract post ID from response
                # Pattern 1: /post/123/
                post_id_match = re.search(r'/post/(\d+)/', bot_response)
                if not post_id_match:
                    # Pattern 2: ID: 123
                    post_id_match = re.search(r'ID:\s*(\d+)', bot_response)

                if post_id_match:
                    post_id = int(post_id_match.group(1))
                    logger.info(f"[PostContext] Found post ID: {post_id}")

                    # Get post details from database
                    try:
                        post = RentalPost.objects.get(id=post_id)
                        logger.info(f"[PostContext] Successfully loaded post {post_id}: {post.title[:50]}")

                        # Build detailed context about this post
                        features_list = []
                        if post.features:
                            # Use FEATURE_CHOICES from models for accurate mapping
                            from website.models import FEATURE_CHOICES
                            feature_names = dict(FEATURE_CHOICES)
                            for feat in post.features:
                                vn_name = feature_names.get(feat, feat)
                                features_list.append(vn_name)

                        post_context = f"""
## 🏠 PHÒNG ĐANG ĐƯỢC HỎI (từ câu trước):

**{post.title}**
- 💰 Giá: {self._format_price_million(post.price)}/tháng
- 📐 Diện tích: {post.area} m²
- 📍 Địa chỉ: {post.address}, {post.ward.name if post.ward else ''}, {post.district.name if post.district else ''}, {post.province.name}
- 🏷️ Loại: {post.get_category_display()}
- 🎯 Tiện ích: {', '.join(features_list) if features_list else 'Không có thông tin'}
- 📝 Mô tả: {post.description[:200] if post.description else 'Không có mô tả'}
- 🔗 Link: /post/{post.id}/

**LƯU Ý:** Đây là phòng mà người dùng đang hỏi thêm thông tin. Hãy trả lời dựa trên dữ liệu thực tế ở trên.
"""
                        self.context.append(post_context)
                        return True  # Found post, stop searching

                    except RentalPost.DoesNotExist:
                        continue
                    except Exception as e:
                        logger.error(f"Error loading post {post_id}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Error adding conversation post context: {e}")
            return False

    def _format_price_million(self, price) -> str:
        """Format giá hiển thị theo đơn vị 'triệu/tháng' dựa trên DB (triệu hoặc VND)."""
        try:
            # Dùng helper có sẵn để quy về VND trước
            from chatbot.views import resolve_price_vnd
            vnd = resolve_price_vnd(price)
            millions = vnd / 1_000_000.0
            # Nếu là số nguyên, hiển thị không phần thập phân
            if abs(millions - int(millions)) < 1e-6:
                return f"{int(millions)} triệu"
            # Ngược lại hiển thị 1 chữ số thập phân
            return f"{millions:.1f} triệu"
        except Exception:
            # Fallback: hiển thị VND
            try:
                vnd = int(price)
                return f"{vnd:,.0f} VNĐ".replace(',', '.')
            except Exception:
                return str(price)

    def _add_database_stats(self):
        """Thống kê tổng quan về database"""
        total_posts = self._visible_posts().count()
        total_requests = RentalRequest.objects.count()

        # Thống kê theo loại
        categories = self._visible_posts().values('category').annotate(
            count=Count('id')
        )

        # Thống kê theo tỉnh
        provinces = self._visible_posts().values('province').annotate(
            count=Count('id')
        ).order_by('-count')[:10]

        stats = f"""
## DỮ LIỆU THỰC TẾ WEBSITE (Cập nhật: {timezone.now().strftime('%d/%m/%Y %H:%M')})

📊 **Tổng quan:**
- Tổng số phòng đang cho thuê: {total_posts} phòng
- Tổng số yêu cầu thuê: {total_requests} yêu cầu

📁 **Phân loại phòng:**
{self._format_category_stats(categories)}

🗺️ **Top 10 khu vực có nhiều phòng:**
{self._format_province_stats(provinces)}
"""
        self.context.append(stats)

    def _format_category_stats(self, categories):
        """Format thống kê loại phòng"""
        if not categories:
            return "- Chưa có dữ liệu"

        lines = []
        for cat in categories:
            category_name = cat['category'] or 'Khác'
            count = cat['count']
            lines.append(f"- {category_name}: {count} phòng")
        return "\n".join(lines)

    def _format_province_stats(self, provinces):
        """Format thống kê tỉnh thành"""
        if not provinces:
            return "- Chưa có dữ liệu"

        lines = []
        for prov in provinces:
            province_name = prov['province'] or 'Không xác định'
            count = prov['count']
            lines.append(f"- {province_name}: {count} phòng")
        return "\n".join(lines)

    def _is_search_query(self, query: str) -> bool:
        """Kiểm tra xem có phải câu hỏi tìm phòng không"""
        keywords = ['tìm', 'tìm kiếm', 'có phòng', 'có trọ', 'còn phòng', 'phòng nào', 'thuê', 'cho thuê', 'gần', 'trọ']
        return any(kw in query.lower() for kw in keywords)

    def _add_search_results(self, query: str):
        """Thêm kết quả tìm kiếm thực tế từ DB"""
        try:
            # Tìm kiếm phòng trực tiếp từ DB
            from chatbot.views import (
                parse_price_from_text, parse_area_from_text,
                find_province_in_text, detect_category_from_text
            )

            # Parse tiêu chí từ câu hỏi HIỆN TẠI (ưu tiên cao nhất)
            min_price, max_price, exact_price = parse_price_from_text(query)
            min_area, max_area, exact_area = parse_area_from_text(query)
            province = find_province_in_text(query)
            category = detect_category_from_text(query)

            # Log để debug
            logger.info(f"[SearchContext] Query: {query[:100]}")
            logger.info(f"[SearchContext] Detected - Province: {province.name if province else None}, Category: {category}, Price: {exact_price or (min_price, max_price)}, Area: {exact_area or (min_area, max_area)}")

            # Xây dựng query
            qs = self._visible_posts()

            if province:
                qs = qs.filter(province=province)
                logger.info(f"[SearchContext] Filtering by province: {province.name}")
            if category:
                qs = qs.filter(category=category)

            # Filter giá - xử lý cả VND và triệu (DB có thể lưu cả 2 format)
            if exact_price:
                # Giá yêu cầu ở dạng VND
                near_low = int(exact_price * 0.95)
                near_high = int(exact_price * 1.05)
                # Chuyển sang triệu để so sánh nếu DB lưu dạng triệu
                near_low_million = near_low // 1_000_000
                near_high_million = near_high // 1_000_000
                # Filter: Hoặc khớp VND hoặc khớp triệu
                qs = qs.filter(
                    Q(price__gte=near_low, price__lte=near_high) |  # Format VND
                    Q(price__gte=near_low_million, price__lte=near_high_million)  # Format triệu
                )
                logger.info(f"[SearchContext] Price filter: {near_low:,} - {near_high:,} VND or {near_low_million} - {near_high_million} triệu")
            elif min_price or max_price:
                price_filters = Q()
                if min_price:
                    min_million = min_price // 1_000_000
                    price_filters &= (Q(price__gte=min_price) | Q(price__gte=min_million))
                if max_price:
                    max_million = max_price // 1_000_000
                    price_filters &= (Q(price__lte=max_price) | Q(price__lte=max_million))
                qs = qs.filter(price_filters)
                logger.info(f"[SearchContext] Price range filter: {min_price or 'any'} - {max_price or 'any'} VND")

            # Filter diện tích
            if exact_area:
                near_low = int(exact_area * 0.9)
                near_high = int(exact_area * 1.1)
                qs = qs.filter(area__gte=near_low, area__lte=near_high)
                logger.info(f"[SearchContext] Area filter: {near_low} - {near_high} m²")
            elif min_area or max_area:
                if min_area:
                    qs = qs.filter(area__gte=min_area)
                    logger.info(f"[SearchContext] Area min filter: >= {min_area} m²")
                if max_area:
                    qs = qs.filter(area__lte=max_area)
                    logger.info(f"[SearchContext] Area max filter: <= {max_area} m²")

            # Học sở thích người dùng gần đây để cá nhân hóa thứ tự
            prefs = self._get_user_preferences()

            # Lấy nhiều kết quả hơn sau đó re-rank theo sở thích + độ gần giá/diện tích + độ mới
            candidates = list(qs.order_by('-created_at')[:30])

            def _score(post: RentalPost) -> float:
                score = 0.0
                # Ưu tiên phù hợp sở thích (category/province)
                try:
                    if post.category and post.category in prefs.get('fav_categories', set()):
                        score += 2.0
                    prov_name = post.province.name if post.province else None
                    if prov_name and prov_name in prefs.get('fav_provinces', set()):
                        score += 1.2
                except Exception:
                    pass

                # Ưu tiên bài mới hơn (giảm dần theo thời gian)
                try:
                    import math
                    delta = (timezone.now() - post.created_at).total_seconds() / 3600.0  # giờ
                    recency_bonus = max(0.0, 2.0 - math.log1p(max(0.0, delta)))  # ~2 → 0 theo thời gian
                    score += recency_bonus
                except Exception:
                    pass

                # Bonus nếu bài có nhiều tương tác gần đây
                try:
                    recent_weight = prefs.get('recent_interactions', {}).get(post.id, 0.0)
                    score += min(3.0, recent_weight)
                except Exception:
                    pass

                return score

            # Re-rank và cắt top 10
            if candidates:
                candidates.sort(key=_score, reverse=True)
            results = candidates[:10]

            if results:
                context = f"\n## KẾT QUẢ TÌM KIẾM THỰC TẾ (Top {len(results)} phòng):\n\n"

                for idx, post in enumerate(results, 1):
                    price_txt = self._format_price_million(post.price)
                    province_name = post.province.name if post.province else 'N/A'
                    district_name = post.district.name if post.district else ''

                    context += f"""
{idx}. **{post.title}**
   - Địa chỉ: {post.address}, {district_name}, {province_name}
   - Giá: {price_txt}/tháng
   - Diện tích: {post.area} m²
   - Loại: {post.category or 'Phòng trọ'}
   - ID: {post.id}
"""

                self.context.append(context)
            else:
                self.context.append("\n⚠️ KHÔNG TÌM THẤY phòng phù hợp với yêu cầu.\n")

        except Exception as e:
            print(f"❌ Error in _add_search_results: {e}")

    def _get_user_preferences(self) -> dict:
        """Học nhanh sở thích từ lịch sử 7 ngày: category, province và các tương tác gần đây.
        Trả về dict với các tập ưu tiên và trọng số tương tác theo post.
        """
        prefs = {
            'fav_categories': set(),
            'fav_provinces': set(),
            'recent_interactions': {},  # post_id -> weight
        }

        try:
            since = timezone.now() - timedelta(days=7)

            # 1) Lấy lịch sử tìm kiếm → count theo category, province
            q_hist = {}
            if self.user:
                q_hist = {'user': self.user, 'searched_at__gte': since}
            elif self.session_key:
                q_hist = {'session_id': self.session_key, 'searched_at__gte': since}
            if q_hist:
                histories = SearchHistory.objects.filter(**q_hist).order_by('-searched_at')[:100]
                cat_count = {}
                prov_count = {}
                for h in histories:
                    if h.category:
                        cat_count[h.category] = cat_count.get(h.category, 0) + 1
                    if h.province:
                        name = h.province.name
                        prov_count[name] = prov_count.get(name, 0) + 1
                # Chọn top 3 mỗi loại làm sở thích
                fav_cats = sorted(cat_count.items(), key=lambda x: x[1], reverse=True)[:3]
                fav_provs = sorted(prov_count.items(), key=lambda x: x[1], reverse=True)[:3]
                prefs['fav_categories'] = set([c for c, _ in fav_cats])
                prefs['fav_provinces'] = set([p for p, _ in fav_provs])

            # 2) Lấy tương tác gần đây → gộp trọng số theo post
            q_inter = {}
            if self.user:
                q_inter = {'user': self.user, 'created_at__gte': since}
            elif self.session_key:
                q_inter = {'session_id': self.session_key, 'created_at__gte': since}
            if q_inter:
                inters = UserInteraction.objects.filter(**q_inter).order_by('-created_at')[:200]
                weight_map = {}
                for it in inters:
                    w = getattr(it, 'weight', 1.0)
                    weight_map[it.post_id] = weight_map.get(it.post_id, 0.0) + w
                prefs['recent_interactions'] = weight_map
        except Exception:
            # Không làm gián đoạn nếu lỗi
            pass

        return prefs

    def _add_user_history(self):
        """Thêm lịch sử tìm kiếm của user"""
        try:
            # Lấy lịch sử 24h gần đây
            time_threshold = timezone.now() - timedelta(hours=24)

            if self.user:
                history = SearchHistory.objects.filter(
                    user=self.user,
                    searched_at__gte=time_threshold
                ).order_by('-searched_at')[:5]
            elif self.session_key:
                history = SearchHistory.objects.filter(
                    session_id=self.session_key,
                    searched_at__gte=time_threshold
                ).order_by('-searched_at')[:5]
            else:
                return

            if history:
                context = "\n## LỊCH SỬ TÌM KIẾM GẦN ĐÂY (24h):\n\n"
                for h in history:
                    context += f"- {h.query} (lúc {h.searched_at.strftime('%H:%M %d/%m')})\n"

                self.context.append(context)

        except Exception as e:
            print(f"❌ Error in _add_user_history: {e}")

    def _add_trending_posts(self):
        """Thêm top phòng hot (nhiều view/request nhất 24h)"""
        try:
            time_threshold = timezone.now() - timedelta(hours=24)

            # Top phòng có nhiều request nhất
            # Fix: dùng 'rental_requests' thay vì 'rentalrequest'
            trending = self._visible_posts().annotate(
                request_count=Count('rental_requests', filter=Q(
                    rental_requests__created_at__gte=time_threshold
                ))
            ).filter(request_count__gt=0).order_by('-request_count')[:5]

            if trending:
                context = "\n## 🔥 TOP PHÒNG HOT (24h gần đây):\n\n"
                for idx, post in enumerate(trending, 1):
                    province_name = post.province.name if post.province else 'N/A'
                    context += f"{idx}. {post.title} - {province_name} ({post.request_count} yêu cầu)\n"

                self.context.append(context)

        except Exception as e:
            print(f"❌ Error in _add_trending_posts: {e}")

    def _add_cheapest_section(self, query: str):
        """Thêm mục 'giá rẻ nhất' vào context.
        - Nếu người dùng nêu rõ tỉnh/thành: chỉ hiển thị trong tỉnh đó. Nếu không có, thêm ghi chú và KHÔNG gợi ý toàn hệ thống (tránh gây nhiễu).
        - Nếu không nêu tỉnh: hiển thị top rẻ toàn hệ thống.
        """
        try:
            # Ưu tiên location trong câu hỏi HIỆN TẠI
            province = self.get_province_from_query(query)
            qs = self._visible_posts()

            if province:
                logger.info(f"[CheapestSection] Using province from current query: {province.name}")
                # Chỉ hiển thị trong tỉnh người dùng yêu cầu
                cheapest_local = qs.filter(province=province).order_by('price')[:3]
                if cheapest_local:
                    context = "\n## 💸 TOP PHÒNG GIÁ RẺ (trong khu vực yêu cầu):\n\n"
                    for idx, post in enumerate(cheapest_local, 1):
                        prov_name = post.province.name if post.province else 'N/A'
                        dist_name = post.district.name if getattr(post, 'district', None) else ''
                        price_txt = self._format_price_million(post.price)
                        context += f"{idx}. {post.title} - {price_txt}/tháng - {dist_name}, {prov_name}\n"
                    self.context.append(context)
                else:
                    # Không có phòng rẻ ở tỉnh đã yêu cầu → không gợi ý toàn hệ thống để tránh sai lệch
                    self.context.append("\n⚠️ Hiện chưa có phòng giá rẻ trong khu vực bạn yêu cầu. Hãy thử mở rộng khu vực hoặc điều chỉnh mức giá.\n")
            else:
                # Không chỉ định tỉnh → cho phép gợi ý toàn hệ thống
                cheapest_global = qs.order_by('price')[:3]
                if cheapest_global:
                    context = "\n## 💰 TOP PHÒNG GIÁ RẺ (toàn hệ thống):\n\n"
                    for idx, post in enumerate(cheapest_global, 1):
                        prov_name = post.province.name if post.province else 'N/A'
                        dist_name = post.district.name if getattr(post, 'district', None) else ''
                        price_txt = self._format_price_million(post.price)
                        context += f"{idx}. {post.title} - {price_txt}/tháng - {dist_name}, {prov_name}\n"
                    self.context.append(context)
        except Exception as e:
            print(f"❌ Error in _add_cheapest_section: {e}")

    # ==== Common filters to ensure only visible posts are used ====
    def _visible_posts(self):
        """Bài đang hiển thị trên website: đã duyệt, không xóa, chưa thuê, chưa hết hạn."""
        from django.db.models import Q
        now = timezone.now()
        return (RentalPost.objects
                .filter(is_approved=True, is_deleted=False, is_rented=False)
                .filter(Q(expired_at__isnull=True) | Q(expired_at__gt=now)))

    def get_price_range_from_query(self, query: str):
        """Parse giá từ câu hỏi"""
        # Sử dụng hàm có sẵn
        from chatbot.views import parse_price_from_text
        return parse_price_from_text(query)

    def get_area_from_query(self, query: str):
        """Parse diện tích từ câu hỏi"""
        from chatbot.views import parse_area_from_text
        return parse_area_from_text(query)

    def get_province_from_query(self, query: str):
        """Parse tỉnh/thành từ câu hỏi"""
        from chatbot.views import find_province_in_text
        return find_province_in_text(query)
