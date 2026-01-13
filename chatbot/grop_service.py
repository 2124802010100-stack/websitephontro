"""
Grop (Groq) AI Service - VIP Pro Chatbot
Tích hợp Groq API để trả lời chính xác dựa trên dữ liệu thực tế
"""

from groq import Groq
from django.core.cache import cache
from django.conf import settings
import time
from urllib.parse import urlencode
import logging
import unicodedata
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Count

from .grop_config import (
    GROP_API_KEY, GROP_MODEL, SYSTEM_INSTRUCTION,
    MAX_RETRIES, RETRY_DELAY, ENABLE_CACHE,
    CACHE_TIMEOUT, CACHE_VERSION, TEMPERATURE, MAX_OUTPUT_TOKENS
)
from .knowledge_base import WEBSITE_KNOWLEDGE, FAQ, PRICING_FALLBACK
from .ai_context_builder import AIContextBuilder
from .vietnamese_parser import (
    VietnameseNumberParser, ConversationMemory, TypoTolerance
)
from website.models import RentalPost, Province, FEATURE_CHOICES

logger = logging.getLogger(__name__)


# Circuit breaker globals (module-level to persist across requests)
_LAST_QUOTA_EXHAUSTED_AT = None
_QUOTA_COOLDOWN_SECONDS = 300  # 5 minutes cooldown after a confirmed quota exhaustion
_LAST_USAGE_LOG_AT = 0  # throttle high-frequency usage logs
_USAGE_LOG_INTERVAL = 30  # seconds


class GropChatbot:
    """VIP Pro Chatbot sử dụng Groq (Grop) API"""

    def __init__(self):
        """Khởi tạo Grop (Groq) client"""
        if not GROP_API_KEY:
            raise ValueError(
                "❌ GROP_API_KEY chưa được cấu hình! "
                "Thêm GROP_API_KEY vào settings.py"
            )

        # Initialize Groq client
        self.client = Groq(api_key=GROP_API_KEY)

        # Initialize current_user to None (will be set per request)
        self._current_user = None

        logger.info(f"✅ Grop (Groq) AI initialized: {GROP_MODEL}")

    def get_response(self, user_message: str, user=None, session_key=None, session=None) -> str:
        """
        Lấy response từ Grop (Groq) AI

        Args:
            user_message: Câu hỏi của user
            user: User object (nếu đã login)
            session_key: Session key (cho guest)
            session: Django session object (for conversation memory)

        Returns:
            str: Câu trả lời từ AI
        """
        # Store user in instance for use in helpers like contact intent
        self._current_user = user

        # 0a. Quick response for common queries (no AI needed)
        from .performance_optimizer import FastResponseOptimizer
        quick_response = FastResponseOptimizer.get_quick_response(user_message)
        if quick_response:
            if session:
                ConversationMemory.add_message(session, user_message, quick_response)
            return quick_response

        # 0b. Enhance message with Vietnamese number parsing and typo tolerance
        enhanced_message = self._enhance_message_with_parsers(user_message, session)

        # 1. Check cache (skip cache if we have session context to personalize or contact intent which must be fresh)
        is_contact = self._is_contact_query(enhanced_message)
        if ENABLE_CACHE and not session and not is_contact:
            cache_key = f"grop:{CACHE_VERSION}:{hash(enhanced_message)}"
            cached = cache.get(cache_key)
            if cached:
                logger.info(f"💾 Cache hit for: {enhanced_message[:50]}")
                return cached

        # 2. Trả lời trực tiếp cho một số intent đặc biệt (chính xác 100% từ DB)
        direct = self._direct_answer_if_applicable(enhanced_message, session)
        if direct:
            # Save to conversation history
            if session:
                ConversationMemory.add_message(session, user_message, direct)

            # Do not cache contact answers; they must always reflect the latest phone/name
            if ENABLE_CACHE and not session and not is_contact:
                cache.set(f"grop:{CACHE_VERSION}:{hash(enhanced_message)}", direct, CACHE_TIMEOUT)
            return direct

        # 3. Build context từ database
        context_builder = AIContextBuilder(user=user, session_key=session_key, session=session)
        dynamic_context = context_builder.build_context(enhanced_message)

        # 4. Add conversation history to context
        if session:
            conversation_context = ConversationMemory.get_context_string(session)
            if conversation_context:
                dynamic_context = conversation_context + "\n\n" + dynamic_context

        # 5. Tạo prompt đầy đủ
        full_prompt = self._build_full_prompt(enhanced_message, dynamic_context)

        # 6. Call Grop API với retry
        response_text = self._call_grop_with_retry(full_prompt)

        # 7. Smart suggestions if no results found
        if response_text and self._is_no_results_response(response_text):
            suggestions = self._generate_smart_suggestions(enhanced_message, session)
            if suggestions:
                response_text += "\n\n" + suggestions

        # 8. Save to conversation history
        if session and response_text:
            ConversationMemory.add_message(session, user_message, response_text)

        # 9. Cache result (skip if personalized with session)
        if ENABLE_CACHE and response_text and not session and not is_contact:
            cache_key = f"grop:{CACHE_VERSION}:{hash(enhanced_message)}"
            cache.set(cache_key, response_text, CACHE_TIMEOUT)

        return response_text

    def _is_contact_query(self, text: str) -> bool:
        m = text.lower()
        return any(kw in m for kw in [
            'liên hệ', 'lien he', 'số điện thoại', 'so dien thoai', 'điện thoại', 'dien thoai',
            'người đăng', 'nguoi dang', 'chủ nhà', 'chu nha', 'chủ trọ', 'chu tro', 'sdt', 'contact'
        ])

    # ===== Direct, deterministic answers for key intents =====
    def _direct_answer_if_applicable(self, message: str, session=None) -> str | None:
        m_lower = message.lower()

        # Check if this is a follow-up question about a specific post
        # If yes, skip direct answer to avoid re-parsing location incorrectly
        # BUT: Only skip if NOT a new search query
        search_keywords = ['tìm', 'tim', 'tìm kiếm', 'tim kiem', 'cho thuê', 'cho thue', 'có phòng', 'co phong', 'còn phòng', 'con phong', 'kiếm', 'kiem']
        is_search_query = any(kw in m_lower for kw in search_keywords)

        if not is_search_query and session:
            # Only check for follow-up if this is NOT a search query
            follow_up_patterns = [
                'căn hộ này', 'phòng này', 'nhà này', 'nó', 'đó',
                'can ho nay', 'phong nay', 'nha nay',
                'máy lạnh', 'wifi', 'gác lửng', 'wc', 'toilet',
                'thang máy', 'ban công', 'bàn ghế', 'tủ lạnh', 'máy giặt',
            ]
            is_follow_up = any(pattern in m_lower for pattern in follow_up_patterns)

            if is_follow_up:
                # Check if there's a post in conversation history
                try:
                    from chatbot.vietnamese_parser import ConversationMemory
                    history = ConversationMemory.get_history(session)
                    if history:
                        import re
                        for exchange in reversed(history[-5:]):
                            bot_response = exchange.get('bot', '')
                            if re.search(r'/post/(\d+)/|ID:\s*(\d+)', bot_response):
                                logger.info(f"[DirectAnswer] Skipping for follow-up question about specific post")
                                return None  # Let AI handle it with proper context
                except Exception as e:
                    logger.debug(f"[DirectAnswer] Error checking follow-up: {e}")

        # 0) LIÊN HỆ ADMIN / QUẢN TRỊ / CSKH
        # Nếu người dùng hỏi cách liên hệ admin (không phải người đăng bài)
        # Ưu tiên bắt trước vì chuỗi "liên hệ" sẽ trùng với nhánh người đăng bên dưới
        if any(kw in m_lower for kw in [
            'admin', 'quản trị', 'quan tri', 'quản trị viên', 'quan tri vien',
            'cskh', 'chăm sóc khách hàng', 'cham soc khach hang', 'support', 'hỗ trợ', 'ho tro'
        ]) and not any(kw in m_lower for kw in [
            'người đăng', 'nguoi dang', 'chủ nhà', 'chu nha', 'chủ trọ', 'chu tro'
        ]):
            # Trả về thông tin hỗ trợ hệ thống (static / có thể lấy từ settings sau này)
            try:
                support_email = 'support@phongtroNMA.vn'
                hotline = '1900-xxxx'
                lines = [
                    '🛠️ Thông tin hỗ trợ / quản trị viên:',
                    f'- 📧 Email: {support_email}',
                    f'- ☎️ Hotline: {hotline} (giờ hành chính)',
                    '- 💬 Chat trực tuyến: dùng chatbot này đặt câu hỏi, hệ thống sẽ chuyển tiếp nếu cần',
                    '- 🚨 Báo cáo vi phạm: mở trang chi tiết phòng và bấm "Báo cáo vi phạm"',
                    '- ⏱️ Thời gian phản hồi email: 24-48 giờ'
                ]
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Admin contact direct answer error: {e}")
                # Không chặn các nhánh khác nếu lỗi

        # Z) Liên hệ người đăng / số điện thoại cho bài hiện tại
        contact_patterns = [
            'liên hệ', 'lien he', 'số điện thoại', 'so dien thoai', 'điện thoại', 'dien thoai',
            'người đăng', 'nguoi dang', 'chủ nhà', 'chu nha', 'chủ trọ', 'chu tro',
            'sdt', 'phone', 'contact',
            'thông tin người', 'thong tin nguoi',  # "xin thông tin người đăng"
            'cho tôi xin', 'cho toi xin',  # "cho tôi xin thông tin"
            'chủ tin', 'chu tin',  # "chủ tin đăng"
        ]
        if any(kw in m_lower for kw in contact_patterns):
            try:
                post = self._resolve_post_from_message_or_history(message, session)
                if not post:
                    return (
                        "Mình cần biết bạn đang hỏi liên hệ của bài nào. "
                        "Bạn có thể: (1) bấm vào link 'Xem chi tiết' của bài rồi hỏi lại 'cho mình số điện thoại', "
                        "hoặc (2) gửi link dạng /post/<ID>/ trong tin nhắn."
                    )

                owner = getattr(post, 'user', None)
                owner_username = owner.username if owner else None
                owner_full = None
                try:
                    if owner and owner.get_full_name().strip():
                        owner_full = owner.get_full_name().strip()
                except Exception:
                    owner_full = None

                # Lấy số điện thoại: ưu tiên ở bài đăng, sau đó đến hồ sơ người dùng
                phone = getattr(post, 'phone_number', None)
                if not phone and owner and hasattr(owner, 'customerprofile'):
                    phone = getattr(owner.customerprofile, 'phone', None)

                # Mask phone for unauthenticated users
                phone_display = self._mask_phone(phone, self._current_user)

                link = f"/post/{post.id}/"
                lines = ["📞 Thông tin liên hệ bài đăng:"]
                if owner_username or owner_full:
                    if owner_full and owner_username and owner_full != owner_username:
                        lines.append(f"- 👤 Người đăng: {owner_full} ({owner_username})")
                    else:
                        lines.append(f"- 👤 Người đăng: {owner_full or owner_username}")
                else:
                    lines.append("- 👤 Người đăng: (chưa có thông tin)")
                if phone_display:
                    lines.append(f"- ☎️ Số điện thoại: {phone_display}")
                else:
                    lines.append("- ☎️ Số điện thoại: (chưa cập nhật)")
                lines.append(f"- 🔗 Xem chi tiết: {link}")
                return "\n".join(lines)
            except Exception as e:
                logger.error(f"Direct contact info error: {e}")
                return None

        # A) ĐẮT NHẤT / MỚI NHẤT
        if any(kw in m_lower for kw in ["đắt nhất", "dat nhat", "cao nhất", "cao nhat"]) or any(kw in m_lower for kw in ["mới nhất", "moi nhat", "new", "vừa đăng", "vua dang"]):
            try:
                is_most_expensive = any(kw in m_lower for kw in ["đắt nhất", "dat nhat", "cao nhất", "cao nhat"])
                limit = self._parse_quantity_quick(m_lower, default=3)

                qs = self._visible_posts()
                qs, context_note = self._apply_common_filters(qs, message, m_lower)

                if is_most_expensive:
                    posts = list(qs.order_by('-price')[:limit])
                    header = f"✅ Top {len(posts)} phòng ĐẮT NHẤT{context_note}:\n\n" if posts else None
                else:
                    posts = list(qs.order_by('-created_at')[:limit])
                    header = f"✅ {len(posts)} phòng MỚI NHẤT{context_note}:\n\n" if posts else None

                if not posts:
                    return f"Hiện chưa có phòng nào hiển thị{context_note}."

                if len(posts) == 1:
                    return header + self._format_post_detail(posts[0])
                lines = [self._format_post_summary(i+1, p) for i, p in enumerate(posts)]
                return header + "\n".join(lines)
            except Exception as e:
                logger.error(f"Direct answer (most/newest) error: {e}")

        # B) DIỆN TÍCH LỚN/SMALL NHẤT
        if any(kw in m_lower for kw in ["diện tích lớn nhất", "dien tich lon nhat", "rộng nhất", "rong nhat", "to nhất", "to nhat"]) or any(kw in m_lower for kw in ["diện tích nhỏ nhất", "dien tich nho nhat", "hẹp nhất", "hep nhat", "bé nhất", "be nhat"]):
            try:
                is_largest = any(kw in m_lower for kw in ["diện tích lớn nhất", "dien tich lon nhat", "rộng nhất", "rong nhat", "to nhất", "to nhat"])
                limit = self._parse_quantity_quick(m_lower, default=3)

                qs = self._visible_posts().filter(area__gt=0)
                qs, context_note = self._apply_common_filters(qs, message, m_lower)

                order = '-area' if is_largest else 'area'
                posts = list(qs.order_by(order, 'price')[:limit])
                header = f"✅ Top {len(posts)} phòng {('DIỆN TÍCH LỚN NHẤT' if is_largest else 'DIỆN TÍCH NHỎ NHẤT')}{context_note}:\n\n" if posts else None
                if not posts:
                    return f"Hiện chưa có phòng nào hiển thị{context_note}."
                if len(posts) == 1:
                    return header + self._format_post_detail(posts[0])
                lines = [self._format_post_summary(i+1, p) for i, p in enumerate(posts)]
                return header + "\n".join(lines)
            except Exception as e:
                logger.error(f"Direct answer (area extremes) error: {e}")

        # C) NHIỀU YÊU CẦU 24H
        if any(kw in m_lower for kw in ["nhiều yêu cầu", "nhieu yeu cau", "nhiều người hỏi", "nhieu nguoi hoi", "hot nhất", "hot nhat", "quan tâm nhiều", "quan tam nhieu"]):
            try:
                since = timezone.now() - timedelta(hours=24)
                limit = self._parse_quantity_quick(m_lower, default=3)
                qs = self._visible_posts()
                qs, context_note = self._apply_common_filters(qs, message, m_lower)
                qs = qs.annotate(req24=Count('rental_requests', filter=Q(rental_requests__created_at__gte=since)))
                posts = list(qs.filter(req24__gt=0).order_by('-req24', '-created_at')[:limit])
                if not posts:
                    return f"24h qua chưa có phòng nào được yêu cầu{context_note}."
                header = f"🔥 Phòng được QUAN TÂM NHIỀU trong 24h{context_note}:\n\n"
                if len(posts) == 1:
                    return header + self._format_post_detail(posts[0])
                lines = [self._format_post_summary(i+1, p) for i, p in enumerate(posts)]
                return header + "\n".join(lines)
            except Exception as e:
                logger.error(f"Direct answer (requests 24h) error: {e}")

        # D) DIỆN TÍCH THRESHOLD (dưới/trên X m²)
        try:
            area_parsed = self._parse_area_range(m_lower)
            if area_parsed is not None:
                val_or_range, mode = area_parsed

                base_qs = self._visible_posts().filter(area__gt=0)
                # Skip area/price filter vì section này tự xử lý riêng
                qs, context_note = self._apply_common_filters(base_qs, message, m_lower, skip_area_price=True)
                limit = self._parse_quantity_quick(m_lower, default=3)

                candidates = []
                if mode == 'exact':
                    # Diện tích xấp xỉ X m² (±10%)
                    delta = max(2, val_or_range * 0.1)
                    lo = val_or_range - delta
                    hi = val_or_range + delta
                    candidates = list(qs.filter(area__gte=lo, area__lte=hi).order_by('area')[:100])
                    # Nếu có giá trong câu hỏi → lọc thêm theo giá
                    price_range = self._parse_price_range(m_lower)
                    price_parsed = self._parse_price_million(m_lower) if price_range is None else None
                    if candidates and (price_range or price_parsed is not None):
                        def price_to_vnd(p):
                            try:
                                v = int(p.price)
                                return v if v >= 1000 else v * 1_000_000
                            except Exception:
                                try:
                                    v = int(float(p.price))
                                    return v if v >= 1000 else v * 1_000_000
                                except Exception:
                                    return 10**12
                        if price_range is not None:
                            lo_mil, hi_mil = price_range
                            lo_v = int(lo_mil * 1_000_000); hi_v = int(hi_mil * 1_000_000)
                            candidates = [p for p in candidates if lo_v <= price_to_vnd(p) <= hi_v]
                        else:
                            target_mil, mode_p = price_parsed
                            if mode_p in ('exact','approx'):
                                delta = 0.25 if mode_p=='exact' else max(0.5, round(target_mil*0.1,1))
                                lo_v = int((target_mil-delta)*1_000_000); hi_v=int((target_mil+delta)*1_000_000)
                                candidates = [p for p in candidates if lo_v <= price_to_vnd(p) <= hi_v]
                            elif mode_p=='min':
                                v = int(target_mil*1_000_000)
                                candidates = [p for p in candidates if price_to_vnd(p) >= v]
                            elif mode_p=='max':
                                v = int(target_mil*1_000_000)
                                candidates = [p for p in candidates if price_to_vnd(p) <= v]
                    candidates = candidates[:limit]
                    if candidates:
                        header = f"✅ Phòng diện tích khoảng {int(val_or_range)}m²{context_note}:\n\n"
                        explanation = self._build_filter_explanation(message, price_range=price_range, price_parsed=price_parsed, area_parsed=(val_or_range, mode))
                        if len(candidates) == 1:
                            resp = self._format_post_detail(candidates[0])
                        else:
                            lines = [self._format_post_summary(i+1, p) for i, p in enumerate(candidates)]
                            resp = header + "\n".join(lines)
                        return resp + (f"\n\n{explanation}" if explanation else "")

                elif mode == 'min':
                    # Diện tích > X m² (strictly greater - 'trên' không bao gồm giá trị X)
                    candidates = list(qs.filter(area__gt=val_or_range).order_by('area')[:100])
                    # Lọc theo giá nếu có
                    price_range = self._parse_price_range(m_lower)
                    price_parsed = self._parse_price_million(m_lower) if price_range is None else None
                    if candidates and (price_range or price_parsed is not None):
                        def price_to_vnd(p):
                            try:
                                v = int(p.price)
                                return v if v >= 1000 else v * 1_000_000
                            except Exception:
                                try:
                                    v = int(float(p.price))
                                    return v if v >= 1000 else v * 1_000_000
                                except Exception:
                                    return 10**12
                        if price_range is not None:
                            lo_mil, hi_mil = price_range
                            lo_v = int(lo_mil * 1_000_000); hi_v = int(hi_mil * 1_000_000)
                            candidates = [p for p in candidates if lo_v <= price_to_vnd(p) <= hi_v]
                        else:
                            target_mil, mode_p = price_parsed
                            if mode_p in ('exact','approx'):
                                delta = 0.25 if mode_p=='exact' else max(0.5, round(target_mil*0.1,1))
                                lo_v = int((target_mil-delta)*1_000_000); hi_v=int((target_mil+delta)*1_000_000)
                                candidates = [p for p in candidates if lo_v <= price_to_vnd(p) <= hi_v]
                            elif mode_p=='min':
                                v = int(target_mil*1_000_000)
                                candidates = [p for p in candidates if price_to_vnd(p) >= v]
                            elif mode_p=='max':
                                v = int(target_mil*1_000_000)
                                candidates = [p for p in candidates if price_to_vnd(p) <= v]
                    candidates = candidates[:limit]
                    if candidates:
                        header = f"✅ Phòng diện tích từ {int(val_or_range)}m² trở lên{context_note}:\n\n"
                        explanation = self._build_filter_explanation(message, price_range=price_range, price_parsed=price_parsed, area_parsed=(val_or_range, mode))
                        if len(candidates) == 1:
                            resp = self._format_post_detail(candidates[0])
                        else:
                            lines = [self._format_post_summary(i+1, p) for i, p in enumerate(candidates)]
                            resp = header + "\n".join(lines)
                        return resp + (f"\n\n{explanation}" if explanation else "")

                elif mode == 'max':
                    # Diện tích < X m² (strictly less - 'dưới' không bao gồm giá trị X)
                    candidates = list(qs.filter(area__lt=val_or_range).order_by('-area')[:100])
                    # Lọc theo giá nếu có
                    price_range = self._parse_price_range(m_lower)
                    price_parsed = self._parse_price_million(m_lower) if price_range is None else None
                    if candidates and (price_range or price_parsed is not None):
                        def price_to_vnd(p):
                            try:
                                v = int(p.price)
                                return v if v >= 1000 else v * 1_000_000
                            except Exception:
                                try:
                                    v = int(float(p.price))
                                    return v if v >= 1000 else v * 1_000_000
                                except Exception:
                                    return 10**12
                        if price_range is not None:
                            lo_mil, hi_mil = price_range
                            lo_v = int(lo_mil * 1_000_000); hi_v = int(hi_mil * 1_000_000)
                            candidates = [p for p in candidates if lo_v <= price_to_vnd(p) <= hi_v]
                        else:
                            target_mil, mode_p = price_parsed
                            if mode_p in ('exact','approx'):
                                delta = 0.25 if mode_p=='exact' else max(0.5, round(target_mil*0.1,1))
                                lo_v = int((target_mil-delta)*1_000_000); hi_v=int((target_mil+delta)*1_000_000)
                                candidates = [p for p in candidates if lo_v <= price_to_vnd(p) <= hi_v]
                            elif mode_p=='min':
                                v = int(target_mil*1_000_000)
                                candidates = [p for p in candidates if price_to_vnd(p) >= v]
                            elif mode_p=='max':
                                v = int(target_mil*1_000_000)
                                candidates = [p for p in candidates if price_to_vnd(p) <= v]
                    candidates = candidates[:limit]
                    if candidates:
                        header = f"✅ Phòng diện tích tới {int(val_or_range)}m² trở xuống{context_note}:\n\n"
                        explanation = self._build_filter_explanation(message, price_range=price_range, price_parsed=price_parsed, area_parsed=(val_or_range, mode))
                        if len(candidates) == 1:
                            resp = self._format_post_detail(candidates[0])
                        else:
                            lines = [self._format_post_summary(i+1, p) for i, p in enumerate(candidates)]
                            resp = header + "\n".join(lines)
                        return resp + (f"\n\n{explanation}" if explanation else "")

                elif mode == 'range':
                    # Diện tích từ A đến B m²
                    lo, hi = val_or_range
                    candidates = list(qs.filter(area__gte=lo, area__lte=hi).order_by('area')[:100])
                    # Lọc theo giá nếu có
                    price_range = self._parse_price_range(m_lower)
                    price_parsed = self._parse_price_million(m_lower) if price_range is None else None
                    if candidates and (price_range or price_parsed is not None):
                        def price_to_vnd(p):
                            try:
                                v = int(p.price)
                                return v if v >= 1000 else v * 1_000_000
                            except Exception:
                                try:
                                    v = int(float(p.price))
                                    return v if v >= 1000 else v * 1_000_000
                                except Exception:
                                    return 10**12
                        if price_range is not None:
                            lo_mil, hi_mil = price_range
                            lo_v = int(lo_mil * 1_000_000); hi_v = int(hi_mil * 1_000_000)
                            candidates = [p for p in candidates if lo_v <= price_to_vnd(p) <= hi_v]
                        else:
                            target_mil, mode_p = price_parsed
                            if mode_p in ('exact','approx'):
                                delta = 0.25 if mode_p=='exact' else max(0.5, round(target_mil*0.1,1))
                                lo_v = int((target_mil-delta)*1_000_000); hi_v=int((target_mil+delta)*1_000_000)
                                candidates = [p for p in candidates if lo_v <= price_to_vnd(p) <= hi_v]
                            elif mode_p=='min':
                                v = int(target_mil*1_000_000)
                                candidates = [p for p in candidates if price_to_vnd(p) >= v]
                            elif mode_p=='max':
                                v = int(target_mil*1_000_000)
                                candidates = [p for p in candidates if price_to_vnd(p) <= v]
                    candidates = candidates[:limit]
                    if candidates:
                        header = f"✅ Phòng diện tích {int(lo)}-{int(hi)}m²{context_note}:\n\n"
                        explanation = self._build_filter_explanation(message, price_range=price_range, price_parsed=price_parsed, area_parsed=((lo, hi), mode))
                        if len(candidates) == 1:
                            resp = self._format_post_detail(candidates[0])
                        else:
                            lines = [self._format_post_summary(i+1, p) for i, p in enumerate(candidates)]
                            resp = header + "\n".join(lines)
                        return resp + (f"\n\n{explanation}" if explanation else "")

                # Không có kết quả
                return f"Hiện chưa tìm thấy phòng với diện tích yêu cầu{context_note}."
        except Exception as e:
            logger.error(f"Direct answer (area threshold) error: {e}")

        # 0) Hỏi theo GIÁ X TRIỆU → lọc phòng theo khoảng giá xấp xỉ hoặc ngưỡng tối thiểu/tối đa
        try:
            # ƯU TIÊN: Parse khoảng giá có cả mốc dưới và trên (ví dụ: "trên 8 triệu và dưới 11 triệu" hoặc "8-11 triệu")
            price_range = self._parse_price_range(m_lower)
            if price_range is not None:
                lo_mil, hi_mil = price_range

                base_qs = self._visible_posts()
                builder = AIContextBuilder()
                province = builder.get_province_from_query(message)
                if province:
                    base_qs = base_qs.filter(province=province)
                feats = self._detect_features(message)
                for f in feats:
                    base_qs = base_qs.filter(features__contains=[f])
                category = self._detect_category(message)
                qs = base_qs.filter(category=category) if category else base_qs

                limit = self._parse_quantity_quick(m_lower, default=3)

                def price_to_vnd(p):
                    try:
                        v = int(p.price)
                        return v if v >= 1000 else v * 1_000_000
                    except Exception:
                        try:
                            v = int(float(p.price))
                            return v if v >= 1000 else v * 1_000_000
                        except Exception:
                            return 10**12

                lo_vnd = int(lo_mil * 1_000_000)
                hi_vnd = int(hi_mil * 1_000_000)
                raw_posts = list(qs[:200])
                # KHÔNG nới lỏng danh mục ở đây: nếu người dùng đã chỉ định loại, phải giữ đúng loại
                filtered = [p for p in raw_posts if lo_vnd <= price_to_vnd(p) <= hi_vnd]
                # Kết hợp ràng buộc DIỆN TÍCH nếu có
                area_parsed = self._parse_area_range(m_lower)
                if area_parsed is not None:
                    val_or_range, mode_a = area_parsed
                    def area_ok(p):
                        a = float(getattr(p, 'area', 0) or 0)
                        if a <= 0:
                            return False
                        if mode_a == 'exact':
                            d = max(2.0, float(val_or_range) * 0.1)
                            return (float(val_or_range) - d) <= a <= (float(val_or_range) + d)
                        if mode_a == 'min':
                            return a >= float(val_or_range)
                        if mode_a == 'max':
                            return a <= float(val_or_range)
                        if mode_a == 'range':
                            lo_a, hi_a = val_or_range
                            return float(lo_a) <= a <= float(hi_a)
                        return True
                    filtered = [p for p in filtered if area_ok(p)]
                filtered.sort(key=lambda p: price_to_vnd(p))
                candidates = filtered[:limit]

                if candidates:
                    head_lo = int(lo_mil) if float(lo_mil).is_integer() else lo_mil
                    head_hi = int(hi_mil) if float(hi_mil).is_integer() else hi_mil
                    header = f"✅ Phòng giá trong khoảng {head_lo}-{head_hi} triệu/tháng"
                    header += f" tại {province.name}" if province else ""
                    header += ":\n\n"
                    explanation = self._build_filter_explanation(message, price_range=(lo_mil, hi_mil), area_parsed=area_parsed)
                    if len(candidates) == 1 or limit == 1:
                        resp = self._format_post_detail(candidates[0])
                    else:
                        lines = [self._format_post_summary(i+1, p) for i, p in enumerate(candidates)]
                        resp = header + "\n".join(lines)
                    return resp + (f"\n\n{explanation}" if explanation else "")

                # Không có kết quả
                loc_note = f" tại {province.name}" if province else ""
                return f"Hiện chưa tìm thấy phòng nào trong khoảng {lo_mil}-{hi_mil} triệu/tháng{loc_note}."

            parsed = self._parse_price_million(m_lower)
            if parsed is not None:
                target_million, mode = parsed

                base_qs = self._visible_posts()
                # Đối với intent theo giá: lọc theo tỉnh/thành nếu có; nếu có tiện ích thì áp dụng; danh mục áp dụng nhưng có cơ chế nới lỏng nếu không có kết quả
                builder = AIContextBuilder()
                province = builder.get_province_from_query(message)
                if province:
                    base_qs = base_qs.filter(province=province)
                # Áp dụng tiện ích nếu người dùng chỉ định (áp dụng cho cả fallback)
                feats = self._detect_features(message)
                for f in feats:
                    base_qs = base_qs.filter(features__contains=[f])
                # Danh mục áp dụng chặt chẽ trước; nếu không có kết quả, sẽ nới lỏng
                category = self._detect_category(message)
                qs = base_qs.filter(category=category) if category else base_qs

                # Số lượng yêu cầu: với intent giá → mặc định 3; '1/2/...' sẽ ghi đè; 'các' → 5
                limit = self._parse_quantity_quick(m_lower, default=3)

                # Hỗ trợ cả 2 kiểu lưu giá: triệu (1..20) hoặc VND (1_000_000..)
                def price_to_vnd(p):
                    try:
                        v = int(p.price)
                        return v if v >= 1000 else v * 1_000_000
                    except Exception:
                        try:
                            v = int(float(p.price))
                            return v if v >= 1000 else v * 1_000_000
                        except Exception:
                            return 10**12

                # Xử lý theo từng chế độ: exact/approx (quanh mục tiêu), min (>=), max (<=)
                candidates = []
                if mode in ('exact', 'approx'):
                    # Exact → siết chặt biên độ; Approx/Range → nới hơn
                    if mode == 'exact':
                        delta = 0.25  # ±250k
                    else:
                        delta = max(0.5, round(target_million * 0.1, 1))  # ±10% tối thiểu 0.5

                    lo_mil = max(0, target_million - delta)
                    hi_mil = target_million + delta
                    lo_vnd = int(lo_mil * 1_000_000)
                    hi_vnd = int(hi_mil * 1_000_000)

                    raw_candidates = list(
                        qs.filter(
                            Q(price__gte=lo_vnd, price__lte=hi_vnd) |
                            Q(price__gte=int(lo_mil), price__lte=int(hi_mil))
                        )[:50]
                    )
                    # Nếu có danh mục nhưng không có kết quả → nới lỏng bỏ danh mục để không trả về rỗng
                    if not raw_candidates and category:
                        qs_relaxed = base_qs
                        raw_candidates = list(
                            qs_relaxed.filter(
                                Q(price__gte=lo_vnd, price__lte=hi_vnd) |
                                Q(price__gte=int(lo_mil), price__lte=int(hi_mil))
                            )[:50]
                        )

                    target_vnd = int(target_million * 1_000_000)
                    delta_vnd = int(delta * 1_000_000)
                    # Kết hợp ràng buộc DIỆN TÍCH nếu có
                    area_parsed = self._parse_area_range(m_lower)
                    def area_ok2(p):
                        if area_parsed is None:
                            return True
                        val_or_range, mode_a = area_parsed
                        a = float(getattr(p, 'area', 0) or 0)
                        if a <= 0:
                            return False
                        if mode_a == 'exact':
                            d = max(2.0, float(val_or_range) * 0.1)
                            return (float(val_or_range) - d) <= a <= (float(val_or_range) + d)
                        if mode_a == 'min':
                            return a >= float(val_or_range)
                        if mode_a == 'max':
                            return a <= float(val_or_range)
                        if mode_a == 'range':
                            lo_a, hi_a = val_or_range
                            return float(lo_a) <= a <= float(hi_a)
                        return True

                    filtered = [p for p in raw_candidates if abs(price_to_vnd(p) - target_vnd) <= delta_vnd and area_ok2(p)]
                    filtered.sort(key=lambda p: (abs(price_to_vnd(p) - target_vnd), price_to_vnd(p)))
                    candidates = filtered[:limit]

                    if not candidates:
                        # Không có trong khoảng → lấy N phòng gần nhất theo giá từ toàn bộ danh sách (đã áp dụng tỉnh + tiện ích)
                        all_posts = list(base_qs.order_by('price')[:50])
                        if all_posts:
                            all_posts.sort(key=lambda p: abs(price_to_vnd(p) - target_vnd))
                            # Tôn trọng ràng buộc diện tích nếu có trong fallback
                            if area_parsed is not None:
                                all_posts = [p for p in all_posts if area_ok2(p)]
                            candidates = all_posts[:limit]

                    if candidates:
                        heading_val = int(target_million) if float(target_million).is_integer() else target_million
                        location_str = f" tại {province.name}" if province else ""
                        header = f"✅ Phòng gần mức giá {heading_val} triệu/tháng{location_str}:\n\n"
                        explanation = self._build_filter_explanation(message, price_parsed=(target_million, mode), area_parsed=area_parsed)
                        if len(candidates) == 1 or limit == 1:
                            resp = self._format_post_detail(candidates[0])
                        else:
                            lines = [self._format_post_summary(idx+1, p) for idx, p in enumerate(candidates)]
                            resp = header + "\n".join(lines)
                        return resp + (f"\n\n{explanation}" if explanation else "")

                elif mode == 'min':
                    # Giá TỐI THIỂU/X TRỞ LÊN → lấy rẻ nhất trong số >= target
                    vnd = int(target_million * 1_000_000)
                    # FIX: Normalize price trước khi filter
                    raw_posts = list(qs[:150])

                    # Lọc price >= target (VND) sau khi normalize
                    filtered = [p for p in raw_posts if price_to_vnd(p) >= vnd]
                    # Kết hợp diện tích nếu có
                    area_parsed = self._parse_area_range(m_lower)
                    if area_parsed is not None:
                        def area_ok3(p):
                            val_or_range, mode_a = area_parsed
                            a = float(getattr(p, 'area', 0) or 0)
                            if a <= 0:
                                return False
                            if mode_a == 'exact':
                                d = max(2.0, float(val_or_range) * 0.1)
                                return (float(val_or_range) - d) <= a <= (float(val_or_range) + d)
                            if mode_a == 'min':
                                return a >= float(val_or_range)
                            if mode_a == 'max':
                                return a <= float(val_or_range)
                            if mode_a == 'range':
                                lo_a, hi_a = val_or_range
                                return float(lo_a) <= a <= float(hi_a)
                            return True
                        filtered = [p for p in filtered if area_ok3(p)]
                    # Sort tăng dần (rẻ nhất trước)
                    filtered.sort(key=lambda p: price_to_vnd(p))
                    candidates = filtered[:limit]

                    if candidates:
                        explanation = self._build_filter_explanation(message, price_parsed=(target_million, mode), area_parsed=area_parsed)
                        if len(candidates) == 1 or limit == 1:
                            resp = self._format_post_detail(candidates[0])
                        else:
                            header = f"✅ Phòng giá từ {int(target_million)} triệu/tháng trở lên:\n\n"
                            lines = [self._format_post_summary(i+1, p) for i, p in enumerate(candidates)]
                            resp = header + "\n".join(lines)
                        return resp + (f"\n\n{explanation}" if explanation else "")

                elif mode == 'max':
                    # Giá TỐI ĐA/X TRỞ XUỐNG → lấy rẻ nhất trong số <= target
                    vnd = int(target_million * 1_000_000)
                    # FIX: Normalize price trước khi filter để tránh OR logic lỏng lẻo
                    raw_posts = list(qs[:150])  # Lấy tối đa 150 bài

                    # Lọc price <= target (VND) sau khi normalize
                    filtered = [p for p in raw_posts if price_to_vnd(p) <= vnd]
                    # Kết hợp diện tích nếu có
                    area_parsed = self._parse_area_range(m_lower)
                    if area_parsed is not None:
                        def area_ok4(p):
                            val_or_range, mode_a = area_parsed
                            a = float(getattr(p, 'area', 0) or 0)
                            if a <= 0:
                                return False
                            if mode_a == 'exact':
                                d = max(2.0, float(val_or_range) * 0.1)
                                return (float(val_or_range) - d) <= a <= (float(val_or_range) + d)
                            if mode_a == 'min':
                                return a >= float(val_or_range)
                            if mode_a == 'max':
                                return a <= float(val_or_range)
                            if mode_a == 'range':
                                lo_a, hi_a = val_or_range
                                return float(lo_a) <= a <= float(hi_a)
                            return True
                        filtered = [p for p in filtered if area_ok4(p)]
                    # Sort tăng dần (rẻ nhất trước)
                    filtered.sort(key=lambda p: price_to_vnd(p))
                    candidates = filtered[:limit]

                    if candidates:
                        explanation = self._build_filter_explanation(message, price_parsed=(target_million, mode), area_parsed=area_parsed)
                        if len(candidates) == 1 or limit == 1:
                            resp = self._format_post_detail(candidates[0])
                        else:
                            header = f"✅ Phòng giá tới {int(target_million)} triệu/tháng trở xuống:\n\n"
                            lines = [self._format_post_summary(i+1, p) for i, p in enumerate(candidates)]
                            resp = header + "\n".join(lines)
                        return resp + (f"\n\n{explanation}" if explanation else "")

                # Nếu vẫn không có kết quả
                location_note = f" tại {province.name}" if province else ""
                if mode == 'min':
                    return f"Hiện chưa tìm thấy phòng nào từ {int(target_million)} triệu/tháng trở lên{location_note}."
                if mode == 'max':
                    return f"Hiện chưa tìm thấy phòng nào tới {int(target_million)} triệu/tháng trở xuống{location_note}."
                return (
                    f"Hiện chưa có phòng nào quanh mức {target_million} triệu/tháng{location_note}. "
                    f"Bạn có muốn xem các phòng giá rẻ nhất không?"
                )
        except Exception as e:
            logger.error(f"Direct answer (price filter) error: {e}")

        # 1) "rẻ nhất" / "thấp nhất" → liệt kê N phòng có giá thấp nhất (mặc định 3), kèm ảnh + link
        if any(kw in m_lower for kw in ["rẻ nhất", "re nhat", "thấp nhất", "thap nhat", "giá thấp nhất", "gia thap nhat", "rẻ nhat"]):
            try:
                # Áp dụng bộ lọc chung (tỉnh/thành, danh mục, tiện ích)
                qs = self._visible_posts()
                qs, context_note = self._apply_common_filters(qs, message, m_lower)

                # Số lượng mong muốn (mặc định 3; nếu user nói 1 phòng → 1)
                limit = self._parse_quantity_quick(m_lower, default=3)

                posts = list(qs.order_by('price', 'area')[:limit])
                if not posts:
                    return f"Hiện tại chưa có phòng nào đang hiển thị{context_note}."

                if len(posts) == 1 or limit == 1:
                    header = f"✅ Phòng có GIÁ RẺ NHẤT hiện tại{context_note}:\n\n"
                    return header + self._format_post_detail(posts[0])

                header = f"✅ Top {len(posts)} phòng GIÁ RẺ NHẤT{context_note}:\n\n"
                lines = [self._format_post_summary(i+1, p) for i, p in enumerate(posts)]
                return header + "\n".join(lines)
            except Exception as e:
                logger.error(f"Direct answer (cheapest) error: {e}")

        # 2) "CHO XEM / LIỆT KÊ TẤT CẢ" các loại phòng hoặc theo địa điểm (mở rộng)
        # Pattern: "cho xem các phòng trọ ở Bình Dương", "cho tôi xem các căn hộ mini", "liệt kê phòng trọ"
        list_keywords = ['cho xem', 'cho tôi xem', 'cho toi xem', 'liệt kê', 'liet ke', 'hiển thị', 'hien thi', 'xem các', 'xem cac', 'các phòng', 'cac phong', 'tất cả', 'tat ca', 'toàn bộ', 'toan bo']
        is_listing_query = any(kw in m_lower for kw in list_keywords)

        if is_listing_query:
            try:
                builder = AIContextBuilder()
                province = builder.get_province_from_query(message)

                # Áp dụng bộ lọc chung
                qs = self._visible_posts()
                qs, context_note = self._apply_common_filters(qs, message, m_lower)

                # Parse số lượng: "cho xem các" thường muốn nhiều → default 5
                limit = self._parse_quantity_quick(m_lower, default=5)
                posts = list(qs.order_by('-created_at')[:limit])

                if posts:
                    # Format đẹp với ảnh + link như các query khác
                    lines = []
                    header = f"✅ Tìm thấy {len(posts)} phòng{context_note}:\n\n"
                    for idx, p in enumerate(posts, 1):
                        lines.append(self._format_post_summary(idx, p))
                    explanation = self._build_filter_explanation(
                        message,
                        price_range=self._parse_price_range(m_lower),
                        price_parsed=self._parse_price_million(m_lower),
                        area_parsed=self._parse_area_range(m_lower),
                    )
                    resp = header + "\n".join(lines)
                    return resp + (f"\n\n{explanation}" if explanation else "")
                else:
                    loc_txt = f" tại {province.name}" if province else ""
                    return f"Hiện tại chưa có phòng nào đang hiển thị{context_note}{loc_txt}."
            except Exception as e:
                logger.error(f"Direct answer (listing query) error: {e}")

        # 3) Tìm phòng theo tỉnh: linh hoạt hơn (chỉ cần có tỉnh + ý định về phòng/trọ)
        if True:
            try:
                builder = AIContextBuilder()
                province = builder.get_province_from_query(message)

                # Điều kiện kích hoạt: có nhắc tới tỉnh và có ý định về phòng/trọ
                intent_room = any(w in m_lower for w in ["phòng", "phong", "trọ", "tro", "nhà", "can ho", "căn hộ"]) or any(w in m_lower for w in ["có", "co", "còn", "con", "kiếm", "kiem", "tìm", "tim"])

                if province and intent_room:
                    # Áp dụng đầy đủ bộ lọc chung (tỉnh/thành, danh mục, tiện ích)
                    qs = self._visible_posts()
                    qs, context_note = self._apply_common_filters(qs, message, m_lower)

                    # Parse số lượng nếu có, mặc định 3 (nếu user nói 1 phòng → 1)
                    limit = self._parse_quantity_quick(m_lower, default=3)
                    posts = list(qs.order_by('-created_at')[:limit])

                    if posts:
                        lines = []
                        header = f"✅ Tìm thấy {len(posts)} phòng{context_note}:\n\n"
                        for idx, p in enumerate(posts, 1):
                            lines.append(self._format_post_summary(idx, p))
                        explanation = self._build_filter_explanation(
                            message,
                            price_range=self._parse_price_range(m_lower),
                            price_parsed=self._parse_price_million(m_lower),
                            area_parsed=self._parse_area_range(m_lower),
                        )
                        resp = header + "\n".join(lines)
                        return resp + (f"\n\n{explanation}" if explanation else "")
                    else:
                        # KHÔNG gợi ý tỉnh khác khi câu hỏi đã nêu rõ tỉnh/thành.
                        return (
                            f"Hiện tại chưa có phòng nào đang hiển thị tại {province.name}.\n\n"
                            f"Bạn có thể thử mở rộng khu vực lân cận hoặc điều chỉnh mức giá/diện tích."
                        )
                # Nếu không detect được province hoặc không có ý định rõ → không trả direct
            except Exception as e:
                logger.error(f"Direct answer (province search) error: {e}")

        # 3) Bảng giá/Phí/VIP
        if any(kw in m_lower for kw in ["mất phí", "mat phi", "phí", "phi", "bảng giá", "bang gia", "vip", "giá gói", "gia goi", "giá dịch vụ", "gia dich vu", "bảng giá vip", "gia vip", "vip3", "vip 3", "bang gia vip"]):
            try:
                # Try to pull from database (authoritative)
                try:
                    from website.models import VIPPackageConfig
                    vips = list(VIPPackageConfig.objects.filter(is_active=True).order_by('plan'))
                    if vips:
                        effective = timezone.now().strftime('%d/%m/%Y')
                        lines = [f"📅 Áp dụng từ: {effective}", ""]
                        for vip in vips:
                            price = f"{int(vip.price):,}".replace(',', '.') + 'đ'
                            color = vip.get_title_color_display().upper()
                            name = vip.get_plan_display()
                            duration = f"{vip.expire_days} ngày" if vip.expire_days != 7 else "1 tuần"
                            lines.append(
                                f"• {name}: {vip.posts_per_day} tin/ngày • Hạn {duration} • {color} • Giá: {price}"
                            )
                        note = "\n💡 Lưu ý: Giá có thể thay đổi theo thời điểm. Vui lòng kiểm tra trang 'Bảng giá' để cập nhật mới nhất."
                        return "\n".join(lines) + note
                except Exception as e:
                    logger.warning(f"Pricing DB fetch failed, using fallback: {e}")

                # Fallback to embedded pricing (kept up-to-date)
                lines = [f"📅 Áp dụng từ: {PRICING_FALLBACK.get('effective_date', '')}", ""]
                for pkg in PRICING_FALLBACK.get('packages', []):
                    price = f"{pkg['price_vnd']:,.0f}".replace(',', '.') + 'đ'
                    lines.append(
                        f"• {pkg['name']}: {pkg['posts_per_day']} tin/ngày • Hạn {pkg['duration']} • {pkg['title_color']} • Giá: {price}"
                    )
                note = "\n💡 Lưu ý: Giá có thể thay đổi theo thời điểm. Vui lòng kiểm tra trang 'Bảng giá' để cập nhật mới nhất."
                return "\n".join(lines) + note
            except Exception as e:
                logger.error(f"Direct answer (pricing) error: {e}")

        return None

    # ===== Utilities =====
    def _visible_posts(self):
        """Queryset of posts visible on website: approved, not deleted, not rented, not expired."""
        now = timezone.now()
        return RentalPost.objects.filter(
            is_approved=True,
            is_deleted=False,
            is_rented=False,
        ).filter(Q(expired_at__isnull=True) | Q(expired_at__gt=now))
    def _format_currency_vn(self, amount: int) -> str:
        try:
            return f"{amount:,.0f}".replace(',', '.')
        except Exception:
            return str(amount)

    def _format_price_vnd(self, raw_price) -> str:
        try:
            value = int(raw_price)
            if value < 1000:
                value = value * 1_000_000
        except Exception:
            try:
                value = int(float(raw_price))
            except Exception:
                value = 0
        return f"{self._format_currency_vn(value)} VNĐ"

    def _format_price_million(self, raw_price) -> str:
        """Format ưu tiên 'triệu' để nhất quán với mong muốn hiển thị."""
        try:
            # Chuẩn hóa về VND trước
            value = int(raw_price)
            if value < 1000:
                value = value * 1_000_000
        except Exception:
            try:
                value = int(float(raw_price))
            except Exception:
                value = 0
        millions = value / 1_000_000.0
        if abs(millions - int(millions)) < 1e-6:
            return f"{int(millions)} triệu"
        return f"{millions:.1f} triệu"

    # ===== Helper: Build filter explanation (lightweight) =====
    def _build_filter_explanation(self, message: str, *, price_range=None, price_parsed=None, area_parsed=None) -> str | None:
        try:
            builder = AIContextBuilder()
            province = builder.get_province_from_query(message)
            categories = self._detect_all_categories(message)
            feats = self._detect_features(message)
            parts = []
            if province:
                parts.append(f"khu vực={province.name}")
            if categories:
                label_map = dict(RentalPost.CATEGORY_CHOICES)
                cat_names = [label_map.get(c, c) for c in categories[:3]]
                parts.append("loại=" + (" hoặc ".join(cat_names)))
            if price_range is not None:
                lo, hi = price_range
                try:
                    lo_s = int(lo) if float(lo).is_integer() else lo
                except Exception:
                    lo_s = lo
                try:
                    hi_s = int(hi) if float(hi).is_integer() else hi
                except Exception:
                    hi_s = hi
                parts.append(f"giá {lo_s}-{hi_s} triệu")
            elif price_parsed is not None:
                try:
                    val, mode = price_parsed
                except Exception:
                    val, mode = None, None
                if val is not None:
                    try:
                        val_s = int(val) if float(val).is_integer() else val
                    except Exception:
                        val_s = val
                    if mode == 'exact':
                        parts.append(f"giá ≈{val_s} triệu")
                    elif mode == 'approx':
                        parts.append(f"giá khoảng {val_s} triệu")
                    elif mode == 'min':
                        parts.append(f"giá từ {val_s} triệu")
                    elif mode == 'max':
                        parts.append(f"giá tới {val_s} triệu")
            if area_parsed is not None:
                try:
                    val_or_range, amode = area_parsed
                except Exception:
                    val_or_range, amode = None, None
                if val_or_range is not None:
                    if amode == 'range' and isinstance(val_or_range, (list, tuple)) and len(val_or_range) == 2:
                        lo_a, hi_a = val_or_range
                        try:
                            lo_a_s = int(lo_a) if float(lo_a).is_integer() else lo_a
                        except Exception:
                            lo_a_s = lo_a
                        try:
                            hi_a_s = int(hi_a) if float(hi_a).is_integer() else hi_a
                        except Exception:
                            hi_a_s = hi_a
                        parts.append(f"diện tích {lo_a_s}-{hi_a_s}m²")
                    else:
                        v = val_or_range
                        try:
                            v_s = int(v) if float(v).is_integer() else v
                        except Exception:
                            v_s = v
                        if amode == 'exact':
                            parts.append(f"diện tích ≈{v_s}m²")
                        elif amode == 'min':
                            parts.append(f"diện tích từ {v_s}m²")
                        elif amode == 'max':
                            parts.append(f"diện tích tới {v_s}m²")
            if feats:
                feat_map = dict(FEATURE_CHOICES)
                feat_names = [feat_map.get(f, f) for f in feats[:3]]
                if feat_names:
                    parts.append("tiện ích=" + ", ".join(feat_names))
            if parts:
                return "ℹ️ Lọc áp dụng: " + "; ".join(parts)
        except Exception:
            return None
        return None

    def _format_post_summary(self, idx: int, post: RentalPost) -> str:
        """Format 1 dòng summary với đầy đủ thông tin: giá, diện tích, địa chỉ, ảnh, link."""
        prov_name = post.province.name if post.province else "N/A"
        dist_name = post.district.name if getattr(post, 'district', None) else ""
        addr_raw = f"{post.address}, {dist_name}, {prov_name}".strip(', ')
        addr = self._normalize_address(addr_raw)
        price_txt = self._format_price_million(post.price)
        area = f"{post.area} m²" if getattr(post, 'area', None) else "N/A"
        title = post.title or "Phòng trọ"

        # Luôn có ảnh (thật hoặc placeholder)
        thumb = self._get_thumb_url(post)
        img_line = f"\n   - 🖼️ ![Ảnh]({thumb})"

        # Luôn có link chi tiết
        # Thêm ID rõ ràng để intent liên hệ có thể trích xuất chắc chắn
        detail_link = f"\n   - 👉 [Xem chi tiết](/post/{post.id}/) (ID:{post.id})"

        return (
            f"{idx}. **{title}**\n"
            f"   - 💰 Giá: {price_txt}/tháng\n"
            f"   - 📐 Diện tích: {area}\n"
            f"   - 📍 Địa chỉ: {addr}{img_line}{detail_link}"
        )

    def _format_post_detail(self, post: RentalPost) -> str:
        """Format chi tiết 1 bài với đầy đủ thông tin, luôn có ảnh và link."""
        prov_name = post.province.name if post.province else "N/A"
        dist_name = post.district.name if getattr(post, 'district', None) else ""
        addr_raw = f"{post.address}, {dist_name}, {prov_name}".strip(', ')
        addr = self._normalize_address(addr_raw)
        price_txt = self._format_price_million(post.price)
        area = f"{post.area} m²" if getattr(post, 'area', None) else "N/A"
        title = post.title or "Phòng trọ"
        desc = (post.description or '').strip()
        if len(desc) > 220:
            desc = desc[:220].rstrip() + '...'

        # Luôn có link chi tiết (URL thuần); hiển thị ID ở ngoài để tránh phá URL
        link_url = f"/post/{post.id}/"
        id_note = f" (ID:{post.id})"

        # Luôn có ảnh (thật hoặc placeholder)
        thumb = self._get_thumb_url(post)
        img_block = f"\n🖼️ ![Ảnh]({thumb})\n"

        # Category label
        cat_label = dict(RentalPost.CATEGORY_CHOICES).get(post.category, post.category) if hasattr(post, 'category') else ""
        cat_line = f"🏷️ Loại: {cat_label}\n" if cat_label else ""

        return (
            f"**{title}**\n"
            f"{cat_line}"
            f"💰 Giá: {price_txt}/tháng\n"
            f"📐 Diện tích: {area}\n"
            f"📍 Địa chỉ: {addr}\n"
            f"👉 [Xem chi tiết]({link_url}){id_note}\n"
            f"{img_block}"
            + (f"📝 Mô tả: {desc}\n" if desc else "")
        )

    def _get_thumb_url(self, post: RentalPost) -> str | None:
        """
        Lấy URL ảnh thumbnail nếu có (ưu tiên ảnh chính, sau đó ảnh bổ sung).
        Luôn trả về URL - dùng placeholder nếu không có ảnh thật.
        """
        # 1. Ảnh chính (image field)
        try:
            if getattr(post, 'image', None) and post.image:
                return post.image.url
        except Exception:
            pass

        # 2. Ảnh bổ sung đầu tiên (images related)
        try:
            first_img = getattr(post, 'images', None).first() if hasattr(post, 'images') else None
            if first_img and first_img.image:
                return first_img.image.url
        except Exception:
            pass

        # 3. Placeholder mặc định cho category
        category = getattr(post, 'category', 'phongtro')
        placeholder_map = {
            'phongtro': '/static/images/placeholder-phongtro.jpg',
            'canho': '/static/images/placeholder-canho.jpg',
            'canho_mini': '/static/images/placeholder-canho-mini.jpg',
            'canho_dichvu': '/static/images/placeholder-canho-dichvu.jpg',
            'nhanguyencan': '/static/images/placeholder-nha.jpg',
            'oghep': '/static/images/placeholder-oghep.jpg',
            'matbang': '/static/images/placeholder-matbang.jpg',
        }
        return placeholder_map.get(category, '/static/images/placeholder-default.jpg')

    def _mask_phone(self, phone: str | None, user) -> str | None:
        """
        Mask phone number for unauthenticated users.
        Authenticated: show full phone.
        Anonymous: mask middle digits (0909***456).

        Args:
            phone: Raw phone number string
            user: Django User object or None

        Returns:
            Masked or full phone string, or None if no phone
        """
        if not phone:
            return None

        # If user is authenticated, show full phone
        if user and user.is_authenticated:
            return phone

        # Mask for anonymous users
        phone_str = str(phone).strip()
        if len(phone_str) < 6:
            # Too short to mask meaningfully
            return phone_str[:2] + '***'

        # Pattern: show first 4 and last 3, mask middle (e.g., 0909***456)
        return phone_str[:4] + '***' + phone_str[-3:]

    def _resolve_post_from_message_or_history(self, message: str, session=None) -> RentalPost | None:
        """Tìm post liên quan từ nội dung tin nhắn hiện tại hoặc lịch sử hội thoại gần nhất.
        Ưu tiên link /post/<id>/ trong message; nếu không có thì lấy link gần nhất trong 5 trao đổi gần đây.
        """
        import re
        # 1) Parse ngay trong message
        m = re.search(r'/post/(\d+)/', message)
        post_id = int(m.group(1)) if m else None

        # 2) Nếu chưa có, tìm trong lịch sử gần nhất (scan nhiều hơn để không quên)
        if not post_id and session:
            try:
                hist = ConversationMemory.get_history(session)
                # Scan 15 exchanges (was 5) để tránh quên post khi có nhiều câu hỏi follow-up
                for exch in reversed(hist[-15:]):
                    bot_resp = (exch.get('bot') or '')
                    # Also check for ID:123 pattern in addition to /post/123/
                    m2 = re.search(r'/post/(\d+)/|ID:\s*(\d+)', bot_resp)
                    if m2:
                        post_id = int(m2.group(1) or m2.group(2))
                        break
            except Exception:
                pass

        if not post_id:
            return None
        try:
            return RentalPost.objects.get(id=post_id)
        except RentalPost.DoesNotExist:
            return None
        except Exception:
            return None

    def _parse_quantity_quick(self, text: str, default: int = 3) -> int:
        import re
        # 1) Các mẫu số lượng phổ biến: "top 3", "3 phòng", "1 bài", "2 tin", "3 kết quả"...
        patterns = [
            r"top\s*(\d+)",
            r"(\d+)\s*(phòng|phong|căn|can|nhà|nha)",
            r"(\d+)\s*(bài|bai|tin|post|kết quả|ket qua)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                try:
                    n = int(m.group(1))
                    return max(1, min(n, 10))
                except Exception:
                    pass

        # 2) Từ khóa định lượng: "một bài", "một phòng" → 1
        if any(kw in text for kw in [
            'một bài', 'mot bai', 'một tin', 'mot tin', 'một phòng', 'mot phong', 'một căn', 'mot can',
            '1 bài', '1 tin', '1 phòng', '1 phong', '1 căn', '1 can'
        ]):
            return 1

        # 3) Nếu người dùng nói 'các/tất cả/all/hết' → hiển thị nhiều (5)
        if any(t in text for t in ['các', 'cac', 'tất cả', 'tat ca', 'all', 'hết', 'het']):
            return 5

        return default

    def _parse_area_range(self, text: str):
        """
        Parse diện tích từ text. Trả về tuple (value, mode) hoặc None.
        mode ∈ {'exact', 'min', 'max', 'range'}
        - exact: đúng X m²
        - min: từ X m² trở lên (dưới/trên X m²)
        - max: tới X m² trở xuống
        - range: từ A đến B m²

        Ví dụ: '20m²' → (20, 'exact'); 'trên 30m²' → (30, 'min'); 'dưới 15m²' → (15, 'max');
                '20-40m²' → ((20,40), 'range')
        """
        import re
        # Từ khóa ngưỡng (đánh giá trên text đã loại bỏ cụm giá để tránh nhiễu bởi "trên 10 triệu")
        min_words = ['trên', 'tren', 'lon hon', 'lớn hơn', 'tu', 'từ', 'toi thieu', 'tối thiểu', 'it nhat', 'ít nhất']
        max_words = ['duoi', 'dưới', 'nho hon', 'nhỏ hơn', 'toi', 'tới', 'den', 'đến', 'toi da', 'tối đa']
        # Loại bỏ các cụm có 'triệu/tr' để không nhầm với giá
        # Loại bỏ cả cụm có từ khóa min/max đi kèm số + 'triệu' để tránh "trên 10 triệu" ảnh hưởng diện tích
        text_no_price = re.sub(r'(?:trên|tren|dưới|duoi|tối\s*thiểu|toi\s*thieu|tối\s*đa|toi\s*da|từ|tu|đến|den)?\s*\d+[\.,]?\d*\s*(?:tr|triệu|trieu)', '', text, flags=re.IGNORECASE)
        has_min = any(w in text_no_price for w in min_words)
        has_max = any(w in text_no_price for w in max_words)

        # Khoảng diện tích: 20-40m² hoặc 20 đến 40m² hoặc từ 20 đến 40m vuông
        # Support: 20-40, 20~40, 20 đến 40, 20 tới 40, từ 20 đến 40
        m_range = re.search(r"(?:từ|tu)?\s*(\d+(?:[\.,]\d+)?)\s*(?:[-~]|đến|den|tới|toi)\s*(\d+(?:[\.,]\d+)?)\s*(?:m2|m²|met\s*vuong|mét\s*vuông|m(?:\s|$))", text_no_price, re.IGNORECASE)
        if m_range:
            try:
                a = float(m_range.group(1).replace(',', '.'))
                b = float(m_range.group(2).replace(',', '.'))
                if a > 0 and b > 0:
                    return ((a, b), 'range')
            except Exception:
                pass

        # Diện tích đơn: 30m² hoặc 30 mét vuông (HỖ TRỢ CẢ KHÔNG SPACE)
        m_single = re.search(r"(\d+(?:[\.,]\d+)?)\s*(m2|m²|met\s*vuong|mét\s*vuông|m)", text_no_price, re.IGNORECASE)
        if m_single:
            try:
                val = float(m_single.group(1).replace(',', '.'))
                # Chỉ parse nếu context là diện tích (có từ "diện tích" hoặc có đơn vị m²/m2/met)
                unit = m_single.group(2).lower()
                if 'm2' in unit or 'm²' in unit or 'met' in unit or ('m' == unit and ('dien tich' in text or 'diện tích' in text or 'phong' in text or 'phòng' in text)):
                    if has_min and not has_max:
                        return (val, 'min')
                    if has_max and not has_min:
                        return (val, 'max')
                    return (val, 'exact')
            except Exception:
                pass

        # Dạng "diện tích 30" (không có đơn vị rõ ràng)
        m_bare = re.search(r"dien\s*tich\s*(?:khoang|tam|~)?\s*(\d+(?:[\.,]\d+)?)", text_no_price, re.IGNORECASE)
        if m_bare:
            try:
                val = float(m_bare.group(1).replace(',', '.'))
                if has_min and not has_max:
                    return (val, 'min')
                if has_max and not has_min:
                    return (val, 'max')
                return (val, 'exact')
            except Exception:
                pass

        return None

    def _parse_price_million(self, text: str):
        """Trích xuất giá theo 'triệu' từ câu hỏi và trả về tuple (value, mode).
        mode ∈ {'exact','approx','min','max'}
        - exact: đúng mức X triệu (siết ±0.25)
        - approx: khoảng X triệu hoặc A-B triệu (nới ±10%)
        - min: "trên/ít nhất/tối thiểu/≥ X triệu" → từ X trở lên
        - max: "dưới/tối đa/≤ X triệu" → tới X trở xuống

        QUAN TRỌNG: Chỉ parse số có đơn vị 'triệu/tr/trieu', KHÔNG parse số có 'm²/m2'
        """
        import re
        approx_words = ['khoảng', 'khoang', 'tầm', 'tam', 'xấp xỉ', 'xap xi', '~', 'gần', 'gan']
        min_words = ['trên', 'tren', 'tối thiểu', 'toi thieu', 'ít nhất', 'it nhat', '>=', '≥', 'lon hon hoac bang']
        max_words = ['dưới', 'duoi', 'tối đa', 'toi da', '<=', '≤', 'nho hon hoac bang']

        # Kiểm tra min/max CHỈ trong context giá (không phải diện tích)
        # Pattern: "giá trên X triệu", "trên X triệu" (không có "m²" sau)
        has_min = bool(re.search(r'(?:gi[aá]\s+)?(?:' + '|'.join(min_words) + r')\s+\d+[\.,]?\d*\s*(?:tr|triệu|trieu)', text, re.IGNORECASE))
        has_max = bool(re.search(r'(?:gi[aá]\s+)?(?:' + '|'.join(max_words) + r')\s+\d+[\.,]?\d*\s*(?:tr|triệu|trieu)', text, re.IGNORECASE))
        has_approx = any(w in text for w in approx_words)

        # Loại bỏ các cụm có "m²" hoặc "m2" để không nhầm với diện tích
        text_no_area = re.sub(r'\d+[\.,]?\d*\s*(m2|m²|met)', '', text, flags=re.IGNORECASE)

        # Khoảng giá dạng 6-8 triệu
        m_range = re.search(r"(\d+(?:[\.,]\d+)?)\s*[-~đ]\s*(\d+(?:[\.,]\d+)?)\s*(tr|triệu|trieu)", text_no_area, re.IGNORECASE)
        if m_range:
            try:
                a = float(m_range.group(1).replace(',', '.'))
                b = float(m_range.group(2).replace(',', '.'))
                if a > 0 and b > 0:
                    return ((a + b) / 2.0, 'approx')
            except Exception:
                pass

        # Đơn giá dạng 7 triệu / 7tr / 7.5 trieu (có thể kèm 'trên/dưới')
        m_single = re.search(r"(\d+(?:[\.,]\d+)?)\s*(tr|triệu|trieu)(?!\s*m)", text_no_area, re.IGNORECASE)
        if m_single:
            try:
                val = float(m_single.group(1).replace(',', '.'))
                if has_min and not has_max:
                    return (val, 'min')
                if has_max and not has_min:
                    return (val, 'max')
                return (val, 'approx' if has_approx else 'exact')
            except Exception:
                return None

        # Trường hợp người dùng chỉ nói 'giá 7' trong ngữ cảnh giá
        m_bare = re.search(r"gi[aá]\s*(?:khoảng|tầm|~)?\s*(\d+(?:[\.,]\d+)?)\b", text_no_area, re.IGNORECASE)
        if m_bare:
            try:
                val = float(m_bare.group(1).replace(',', '.'))
                return (val, 'approx' if has_approx else 'exact')
            except Exception:
                return None

        # Câu như '7tr có phòng không' (không có từ 'giá')
        m_at = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*(tr|triệu|trieu)\b", text_no_area, re.IGNORECASE)
        if m_at:
            try:
                val = float(m_at.group(1).replace(',', '.'))
                if has_min and not has_max:
                    return (val, 'min')
                if has_max and not has_min:
                    return (val, 'max')
                return (val, 'approx' if has_approx else 'exact')
            except Exception:
                return None

        return None

    def _parse_price_range(self, text: str):
        """Trích xuất khoảng giá có cả mốc thấp và cao (triệu), trả về (lo, hi) theo 'triệu'.
        Hỗ trợ các dạng:
        - "từ 8 triệu đến 11 triệu"
        - "8-11 triệu" hoặc "8 ~ 11 triệu"
        - Kết hợp từ khóa: "trên 8 triệu và dưới 11 triệu"
        Trả về None nếu không phát hiện được cả 2 mốc.
        """
        import re
        # Bỏ cụm diện tích để tránh nhầm
        text_no_area = re.sub(r'\d+[\.,]?\d*\s*(m2|m²|met)', '', text, flags=re.IGNORECASE)

        # 1) Dạng "từ A đến B triệu"
        m_from_to = re.search(r"(?:từ|tu)\s*(\d+(?:[\.,]\d+)?)\s*(tr|triệu|trieu)\s*(?:đến|den|tới|toi)\s*(\d+(?:[\.,]\d+)?)\s*(tr|triệu|trieu)", text_no_area, re.IGNORECASE)
        if m_from_to:
            try:
                a = float(m_from_to.group(1).replace(',', '.'))
                b = float(m_from_to.group(3).replace(',', '.'))
                if a > 0 and b > 0:
                    lo, hi = (a, b) if a <= b else (b, a)
                    return (lo, hi)
            except Exception:
                pass

        # 2) Dạng "A - B triệu" (gạch ngang, ngã)
        m_dash = re.search(r"(\d+(?:[\.,]\d+)?)\s*[-~–—]\s*(\d+(?:[\.,]\d+)?)\s*(tr|triệu|trieu)", text_no_area, re.IGNORECASE)
        if m_dash:
            try:
                a = float(m_dash.group(1).replace(',', '.'))
                b = float(m_dash.group(2).replace(',', '.'))
                if a > 0 and b > 0:
                    lo, hi = (a, b) if a <= b else (b, a)
                    return (lo, hi)
            except Exception:
                pass

        # 3) Dạng "trên A triệu" VÀ "dưới B triệu" (xuất hiện cùng lúc, không cần thứ tự)
        m_min = re.search(r"(?:trên|tren|tối\s*thiểu|toi\s*thieu|ít\s*nhất|it\s*nhat|>=|≥|từ|tu)\D{0,12}(\d+(?:[\.,]\d+)?)\s*(tr|triệu|trieu)", text_no_area, re.IGNORECASE)
        m_max = re.search(r"(?:dưới|duoi|tối\s*đa|toi\s*da|<=|≤|tới|toi|đến|den)\D{0,12}(\d+(?:[\.,]\d+)?)\s*(tr|triệu|trieu)", text_no_area, re.IGNORECASE)
        if m_min and m_max:
            try:
                a = float(m_min.group(1).replace(',', '.'))
                b = float(m_max.group(1).replace(',', '.'))
                if a > 0 and b > 0 and a <= b:
                    return (a, b)
                if a > 0 and b > 0 and b < a:
                    return (b, a)
            except Exception:
                pass

        return None

    # ===== Filtering helpers =====
    def _normalize(self, s: str) -> str:
        s = s.lower()
        s = unicodedata.normalize('NFD', s)
        return ''.join(c for c in s if unicodedata.category(c) != 'Mn')

    def _detect_category(self, text: str) -> str | None:
        """
        Nhận diện danh mục phòng từ text với độ chính xác cao.
        Ưu tiên các từ khóa cụ thể trước (mini, dịch vụ) rồi mới tổng quát (căn hộ).

        Trả về một category hoặc None. Nếu None, caller cần xử lý multiple categories.
        """
        norm = self._normalize(text)

        # Thứ tự quan trọng: từ CỤ THỂ → TỔNG QUÁT để tránh nhầm lẫn
        # 1. Căn hộ mini (cụ thể nhất trong nhóm căn hộ)
        if any(kw in norm for kw in ['can ho mini', 'căn hộ mini', 'studio', 'can ho nho', 'căn hộ nhỏ']):
            return 'canho_mini'

        # 2. Căn hộ dịch vụ
        if any(kw in norm for kw in ['can ho dich vu', 'căn hộ dịch vụ', 'chcc dich vu', 'chcc dịch vụ', 'serviced apartment']):
            return 'canho_dichvu'

        # 3. Căn hộ chung cư (tổng quát hơn, check sau mini/dịch vụ)
        if any(kw in norm for kw in ['can ho chung cu', 'căn hộ chung cư', 'chung cu', 'chung cư', 'apartment', 'can ho', 'căn hộ', 'chcc']):
            return 'canho'

        # 4. Mặt bằng + Văn phòng
        if any(kw in norm for kw in ['mat bang', 'mặt bằng', 'van phong', 'văn phòng', 'mb', 'vp', 'mat tien', 'mặt tiền', 'ki ot', 'ki-ốt', 'quay hang', 'quầy hàng']):
            return 'matbang'

        # 5. Nhà nguyên căn
        if any(kw in norm for kw in ['nha nguyen can', 'nhà nguyên căn', 'nguyen can', 'nguyên căn', 'nha rieng', 'nhà riêng', 'nha ca nhan', 'nhà cá nhân', 'house', 'villa']):
            return 'nhanguyencan'

        # 6. Ở ghép
        if any(kw in norm for kw in ['o ghep', 'ở ghép', 'tim nguoi o ghep', 'tìm người ở ghép', 'tim ban o ghep', 'tìm bạn ở ghép', 'roommate', 'share room']):
            return 'oghep'

        # 7. Phòng trọ (tổng quát nhất - check cuối)
        if any(kw in norm for kw in ['phong tro', 'phòng trọ', 'nha tro', 'nhà trọ', 'phong', 'phòng', 'tro', 'trọ', 'room']):
            return 'phongtro'

        return None

    def _detect_features(self, text: str) -> list[str]:
        """
        Nhận diện 11 tiện ích/đặc điểm nổi bật từ text.
        Sử dụng nhiều biến thể từ ngữ để tăng độ bao phủ.
        """
        norm = self._normalize(text)
        feats = []

        # Map từng feature code → danh sách keywords (đã normalize)
        feat_map = {
            'day_du_noi_that': [
                'day du noi that', 'full noi that',
                'noi that day du', 'co noi that',
                'trang bi day du', 'full furnished'
            ],
            'co_may_lanh': [
                'may lanh', 'dieu hoa', 'dieu hoa nhiet do',
                'air conditioner', 'air-con', 'aircon'
            ],
            'co_thang_may': [
                'thang may', 'elevator', 'lift', 'co thang may'
            ],
            'bao_ve_24_24': [
                'bao ve 24', 'bao ve 24/24',
                'bao ve ca ngay', 'an ninh 24h', 'security 24/7',
                'co bao ve'
            ],
            'co_gac': [
                'gac', 'gac lung', 'co gac',
                'loft', 'mezzanine'
            ],
            'co_may_giat': [
                'may giat', 'washing machine', 'co may giat',
                'may giat quan ao'
            ],
            'khong_chung_chu': [
                'khong chung chu', 'khong chung',
                'rieng tu', 'chu rieng', 'independent'
            ],
            'co_ham_de_xe': [
                'ham de xe', 'ham gui xe',
                'cho de xe', 'bai do xe',
                'parking', 'garage', 'co cho de xe'
            ],
            'co_ke_bep': [
                'ke bep', 'tu bep', 'kitchen cabinet',
                'co ke bep', 'co tu bep'
            ],
            'co_tu_lanh': [
                'tu lanh', 'fridge', 'refrigerator', 'co tu lanh',
                'may lanh thuc pham'
            ],
            'gio_giac_tu_do': [
                'gio giac tu do', 'tu do',
                'khong han che gio', 'flexible time',
                'khong gioi han gio', 'gio ra vao tu do'
            ],
        }

        for code, keywords in feat_map.items():
            if any(kw in norm for kw in keywords):
                feats.append(code)

        return feats

    def _detect_all_categories(self, text: str) -> list[str]:
        """
        Detect TẤT CẢ categories được nhắc tới trong text.
        Trả về list các category codes.
        Ví dụ: "phòng trọ hoặc nhà nguyên căn" → ['phongtro', 'nhanguyencan']
        """
        norm = self._normalize(text)
        categories = []

        # Check theo thứ tự CỤ THỂ → TỔNG QUÁT
        # 1. Căn hộ mini
        if any(kw in norm for kw in ['can ho mini', 'căn hộ mini', 'studio', 'can ho nho', 'căn hộ nhỏ']):
            categories.append('canho_mini')

        # 2. Căn hộ dịch vụ
        if any(kw in norm for kw in ['can ho dich vu', 'căn hộ dịch vụ', 'chcc dich vu', 'chcc dịch vụ', 'serviced apartment']):
            categories.append('canho_dichvu')

        # 3. Căn hộ chung cư (nếu chưa có mini/dịch vụ)
        if not any(c in categories for c in ['canho_mini', 'canho_dichvu']):
            if any(kw in norm for kw in ['can ho chung cu', 'căn hộ chung cư', 'chung cu', 'chung cư', 'apartment', 'can ho', 'căn hộ', 'chcc']):
                categories.append('canho')

        # 4. Mặt bằng + Văn phòng
        if any(kw in norm for kw in ['mat bang', 'mặt bằng', 'van phong', 'văn phòng', 'mb', 'vp', 'mat tien', 'mặt tiền', 'ki ot', 'ki-ốt', 'quay hang', 'quầy hàng']):
            categories.append('matbang')

        # 5. Nhà nguyên căn
        if any(kw in norm for kw in ['nha nguyen can', 'nhà nguyên căn', 'nguyen can', 'nguyên căn', 'nha rieng', 'nhà riêng', 'nha ca nhan', 'nhà cá nhân', 'house', 'villa']):
            categories.append('nhanguyencan')

        # 6. Ở ghép
        if any(kw in norm for kw in ['o ghep', 'ở ghép', 'tim nguoi o ghep', 'tìm người ở ghép', 'tim ban o ghep', 'tìm bạn ở ghép', 'roommate', 'share room']):
            categories.append('oghep')

        # 7. Phòng trọ (nếu chưa có loại nào khác, hoặc có từ khóa rõ ràng)
        # Chỉ thêm 'phongtro' nếu có từ khóa cụ thể
        if any(kw in norm for kw in ['phong tro', 'phòng trọ', 'nha tro', 'nhà trọ', 'room for rent']):
            if 'phongtro' not in categories:
                categories.append('phongtro')

        return categories

    def _apply_common_filters(self, qs, message: str, m_lower: str, skip_area_price=False):
        """
        Áp dụng các filter chung: tỉnh/thành, danh mục, tiện ích, giá, diện tích.
        Trả về (qs, context_note).

        Args:
            skip_area_price: Nếu True, bỏ qua filter giá và diện tích (vì đã xử lý riêng ở caller)
        """
        builder = AIContextBuilder()
        province = builder.get_province_from_query(message)
        if province:
            qs = qs.filter(province=province)

        # Detect tất cả categories được nhắc tới
        categories = self._detect_all_categories(message)

        # Nếu có nhiều categories → filter theo OR (lấy bất kỳ category nào trong list)
        if len(categories) > 1:
            from django.db.models import Q
            category_q = Q()
            for cat in categories:
                category_q |= Q(category=cat)
            qs = qs.filter(category_q)
        elif len(categories) == 1:
            # Chỉ có 1 category → filter bình thường
            qs = qs.filter(category=categories[0])
        # Nếu không có category nào → không filter (lấy tất cả)

        features = self._detect_features(message)
        for f in features:
            qs = qs.filter(features__contains=f)  # MultiSelectField: use string, not list

        # Apply price and area filters (unless skipped by specialized handlers)
        if not skip_area_price:
            # Apply price filter
            price_range = self._parse_price_range(m_lower)
            if price_range:
                lo, hi = price_range
                qs = qs.filter(price__gte=lo, price__lte=hi)

            # Apply area filter
            area_parsed = self._parse_area_range(m_lower)
            if area_parsed is not None:
                val, mode = area_parsed
                if mode == 'min':
                    qs = qs.filter(area__gt=val)  # 'trên' = strictly >
                elif mode == 'max':
                    qs = qs.filter(area__lt=val)  # 'dưới' = strictly <
                elif mode == 'exact':
                    qs = qs.filter(area=val)
                elif mode == 'range':
                    a, b = val
                    qs = qs.filter(area__gte=a, area__lte=b)

        note_parts = []
        if province:
            note_parts.append(f" tại {province.name}")
        if len(categories) == 1:
            # Convert code to human-friendly label
            cat_label = dict(RentalPost.CATEGORY_CHOICES).get(categories[0], categories[0])
            note_parts.append(f" ({cat_label})")
        elif len(categories) > 1:
            cat_labels = [dict(RentalPost.CATEGORY_CHOICES).get(c, c) for c in categories]
            note_parts.append(f" ({' hoặc '.join(cat_labels)})")
        context_note = ''.join(note_parts)
        return qs, context_note

    def _normalize_address(self, addr: str) -> str:
        """Loại bỏ phần địa chỉ trùng lặp theo từng đoạn, giữ nguyên thứ tự."""
        try:
            parts = [p.strip() for p in addr.split(',') if p.strip()]
            seen = set()
            uniq = []
            for p in parts:
                if p not in seen:
                    uniq.append(p)
                    seen.add(p)
            return ', '.join(uniq)
        except Exception:
            return addr

    def _build_rental_list_link(self, *, province=None, district=None, ward=None, category: str | None = None,
                                 features: list[str] | None = None, price_vnd_range: tuple[int, int] | None = None,
                                 area_range: tuple[float, float] | None = None) -> str:
        """Tạo deep-link đến trang danh sách '/phong-tro/' với query params tương ứng."""
        base = "/phong-tro/"
        params = {}
        if province:
            try:
                params['province'] = province.id
            except Exception:
                pass
        if district:
            try:
                params['district'] = district.id
            except Exception:
                pass
        if ward:
            try:
                params['ward'] = ward.id
            except Exception:
                pass
        if category:
            params['type'] = category
        if price_vnd_range:
            lo, hi = price_vnd_range
            params['price'] = f"{max(0, int(lo))}-{max(0, int(hi))}"
        if area_range:
            lo_a, hi_a = area_range
            params['area'] = f"{max(0, int(lo_a))}-{max(0, int(hi_a))}"
        query = urlencode(params, doseq=True)
        # Features must be appended manually as repeated keys to support multiple values
        feats = features or []
        if feats:
            feat_q = '&'.join([f"features={f}" for f in feats])
            query = f"{query}&{feat_q}" if query else feat_q
        return f"{base}?{query}" if query else base

    def _build_full_prompt(self, user_message: str, dynamic_context: str) -> str:
        """Xây dựng prompt đầy đủ cho Grop (Groq)"""

        # Check FAQ trước
        faq_answer = self._check_faq(user_message)
        faq_hint = ""
        if faq_answer:
            faq_hint = f"\n💡 **GỢI Ý TỪ FAQ:** {faq_answer}\n"

        prompt = f"""
{WEBSITE_KNOWLEDGE}

{dynamic_context}

{faq_hint}

---

**CÂU HỎI CỦA NGƯỜI DÙNG:**
{user_message}

**YÊU CẦU TRẢ LỜI:**
1. Dựa vào DỮ LIỆU THỰC TẾ ở trên (nếu có)
2. Nếu là câu hỏi tìm phòng → Liệt kê cụ thể các phòng từ "KẾT QUẢ TÌM KIẾM THỰC TẾ"
3. Nếu hỏi về tính năng → Dùng thông tin từ KNOWLEDGE BASE
4. Trả lời ngắn gọn, dễ hiểu, thân thiện
5. KHÔNG bịa đặt thông tin không có trong dữ liệu

Trả lời:
"""
        # Log để debug context AI nhận được
        logger.info(f"[GropPrompt] User query: {user_message[:100]}")
        if "PHÒNG ĐANG ĐƯỢC HỎI" in dynamic_context:
            logger.info("[GropPrompt] Context có section 'PHÒNG ĐANG ĐƯỢC HỎI'")
        if "KẾT QUẢ TÌM KIẾM" in dynamic_context:
            logger.info("[GropPrompt] Context có section 'KẾT QUẢ TÌM KIẾM'")

        return prompt

    def _check_faq(self, message: str) -> str:
        """Kiểm tra xem có trong FAQ không"""
        message_lower = message.lower()

        for keyword, answer in FAQ.items():
            if keyword in message_lower:
                return answer

        return ""

    def _call_grop_with_retry(self, prompt: str) -> str:
        """Call Grop (Groq) API với circuit breaker, adaptive backoff, header-aware retry.

        Logic cải tiến:
        1. Circuit breaker: nếu vừa gặp QUOTA (429) trong vòng _QUOTA_COOLDOWN_SECONDS → bỏ qua ngay, trả fallback.
        2. Adaptive backoff: delay = RETRY_DELAY * (2 ** (attempt-1)).
        3. Parse 'Retry-After' (nếu có) từ exception để điều chỉnh cooldown.
        4. Throttle usage logs (không spam mỗi request nếu tần suất cao).
        5. Trả về fallback rõ ràng nếu hết quota, không lặp lại nhiều log QUOTA EXHAUSTED.
        """
        global _LAST_QUOTA_EXHAUSTED_AT, _QUOTA_COOLDOWN_SECONDS, _LAST_USAGE_LOG_AT

        # 1) Circuit breaker pre-check
        if _LAST_QUOTA_EXHAUSTED_AT:
            elapsed = time.time() - _LAST_QUOTA_EXHAUSTED_AT
            if elapsed < _QUOTA_COOLDOWN_SECONDS:
                remaining = int(_QUOTA_COOLDOWN_SECONDS - elapsed)
                logger.warning(
                    f"⛔ Skipping Grop call (quota cooldown {remaining}s remaining)"
                )
                return self._get_fallback_response()

        quota_error_detected = False
        last_retry_after_seconds = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"🤖 Grop attempt {attempt}/{MAX_RETRIES}")

                response = self.client.chat.completions.create(
                    model=GROP_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_INSTRUCTION},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=TEMPERATURE,
                    max_tokens=MAX_OUTPUT_TOKENS,
                )

                content = ""
                if response and response.choices:
                    choice = response.choices[0]
                    message = getattr(choice, "message", None)
                    if message:
                        content = (message.get("content")
                                   if isinstance(message, dict)
                                   else getattr(message, "content", None)) or ""

                if content.strip():
                    # 2) Success — clear quota breaker if previously set
                    if quota_error_detected:
                        _LAST_QUOTA_EXHAUSTED_AT = None

                    # 3) Controlled usage logging (throttle)
                    try:
                        now_ts = time.time()
                        usage = getattr(response, "usage", None)
                        if usage and (now_ts - _LAST_USAGE_LOG_AT) >= _USAGE_LOG_INTERVAL:
                            logger.info(
                                "✅ Grop OK | Tokens total=%s (in=%s, out=%s)" % (
                                    getattr(usage, 'total_tokens', 'N/A'),
                                    getattr(usage, 'prompt_tokens', 'N/A'),
                                    getattr(usage, 'completion_tokens', 'N/A')
                                )
                            )
                            _LAST_USAGE_LOG_AT = now_ts
                        elif not usage:
                            logger.info("✅ Grop OK")
                    except Exception:
                        logger.info("✅ Grop OK")

                    return content.strip()
                else:
                    logger.warning("⚠️ Empty Grop response")
                    return "Xin lỗi, AI đang gặp vấn đề. Vui lòng thử lại sau! 🙏"

            except Exception as e:
                error_str = str(e)
                is_quota = (
                    '429' in error_str or
                    'quota' in error_str.lower() or
                    'resourceexhausted' in error_str.lower() or
                    'rate limit' in error_str.lower()
                )
                if is_quota:
                    quota_error_detected = True
                    retry_after = self._extract_retry_after(e)
                    last_retry_after_seconds = retry_after
                    logger.error(
                        f"❌ Grop QUOTA EXHAUSTED attempt {attempt} | "
                        f"Retry-After={retry_after if retry_after is not None else 'N/A'} | "
                        f"Message: {error_str[:180]}"
                    )
                else:
                    logger.error(f"❌ Grop error attempt {attempt}: {error_str[:200]}")

                # Decide next step
                if attempt < MAX_RETRIES and not quota_error_detected:
                    # Non-quota error → exponential backoff
                    backoff = RETRY_DELAY * (2 ** (attempt - 1))
                    time.sleep(backoff)
                    continue
                if attempt < MAX_RETRIES and quota_error_detected:
                    # Quota: no point hammering quickly; single short backoff then break to fallback
                    time.sleep(0.5)
                    break
                # Last attempt failed → break
                break

        # Post-failure handling
        if quota_error_detected:
            _LAST_QUOTA_EXHAUSTED_AT = time.time()
            # Adjust cooldown if server gave hint (Retry-After header seconds)
            if last_retry_after_seconds and last_retry_after_seconds > 0:
                # Cap excessively large values to 30m for safety
                adjusted = min(int(last_retry_after_seconds), 1800)
                _QUOTA_COOLDOWN_SECONDS = max(adjusted, _QUOTA_COOLDOWN_SECONDS)
                logger.warning(f"⏳ Updated quota cooldown to { _QUOTA_COOLDOWN_SECONDS }s based on Retry-After")
            return self._get_fallback_response()
        return self._get_fallback_response()

    def _extract_retry_after(self, exc) -> int | None:
        """Cố gắng lấy Retry-After (giây) từ exception nếu có.
        Google client có thể gói HTTP response; ta kiểm tra phổ biến attributes.
        Trả về None nếu không tìm thấy.
        """
        try:
            # Common patterns: exc.retry_after or exc.response.headers
            if hasattr(exc, 'retry_after') and isinstance(getattr(exc, 'retry_after'), (int, float)):
                return int(getattr(exc, 'retry_after'))
            resp = getattr(exc, 'response', None)
            if resp and hasattr(resp, 'headers'):
                headers = resp.headers
                # headers có thể là dict hoặc case-insensitive mapping
                for k in ['Retry-After', 'retry-after']:
                    if k in headers:
                        try:
                            return int(headers[k])
                        except Exception:
                            # If format is HTTP date, ignore for simplicity
                            return None
        except Exception:
            return None
        return None

    # ===== Helper methods (moved back into class) =====
    def _enhance_message_with_parsers(self, message: str, session=None) -> str:
        enhanced = message

        # Parse area FIRST to avoid confusion with price
        area = VietnameseNumberParser.parse_area(message)
        if area:
            enhanced += f" [DIỆN TÍCH: {area} m2]"

        # Only parse price if message doesn't contain area keywords
        # (to avoid "trên 20 m²" being parsed as price >= 20 triệu)
        m_lower = message.lower()
        has_area_context = any(kw in m_lower for kw in ['m2', 'm²', 'm vuông', 'mét vuông', 'diện tích', 'dien tich'])

        if not has_area_context:
            price_range = VietnameseNumberParser.extract_price_range(message)
            if price_range[0] or price_range[1]:
                min_price, max_price = price_range
                if min_price and max_price:
                    enhanced += f" [GIÁ: {min_price//1_000_000}-{max_price//1_000_000} triệu]"
                elif max_price:
                    enhanced += f" [GIÁ TỐI ĐA: {max_price//1_000_000} triệu]"
                elif min_price:
                    enhanced += f" [GIÁ TỐI THIỂU: {min_price//1_000_000} triệu]"
        province_normalized = TypoTolerance.normalize_province(message)
        if province_normalized:
            enhanced += f" [KHU VỰC: {province_normalized}]"
        if session:
            context = ConversationMemory.extract_context(session)
            if context.get('mentioned_province') and province_normalized is None:
                enhanced += f" [NGẦM ĐỊNH KHU VỰC: {context['mentioned_province'].name}]"
        logger.info(f"Enhanced message: {message} -> {enhanced}")
        return enhanced

    def _is_no_results_response(self, response: str) -> bool:
        phrases = ["chưa tìm thấy","không tìm thấy","chưa có phòng","không có phòng","hiện chưa có","hiện không có"]
        rl = response.lower()
        return any(p in rl for p in phrases)

    def _generate_smart_suggestions(self, message: str, session=None) -> str:
        suggestions = []
        builder = AIContextBuilder()
        province = builder.get_province_from_query(message)
        price_range = VietnameseNumberParser.extract_price_range(message)
        area = VietnameseNumberParser.parse_area(message)
        categories = self._detect_all_categories(message)
        if price_range[0] or price_range[1]:
            min_price, max_price = price_range
            if max_price:
                suggestions.append(f"💡 Thử tăng giá lên tới **{int(max_price*1.3)//1_000_000} triệu/tháng**?")
            if min_price:
                suggestions.append(f"💡 Thử giảm giá xuống từ **{int(min_price*0.8)//1_000_000} triệu/tháng**?")
        if area:
            suggestions.append(f"💡 Thử mở rộng diện tích từ **{int(area*0.8)}-{int(area*1.2)}m²**?")
        if categories:
            all_categories = {
                'phongtro':'Phòng trọ','nhanguyencan':'Nhà nguyên căn','canho_mini':'Căn hộ mini',
                'canho_dichvu':'Căn hộ dịch vụ','oghep':'Ở ghép','ktx':'KTX','matbang':'Mặt bằng'
            }
            other = [c for c in all_categories if c not in categories]
            if other:
                names = [all_categories[c] for c in other[:2]]
                suggestions.append("💡 Thử tìm **" + " hoặc ".join(names) + "**?")
        if province:
            nearby = {
                'Thành phố Hồ Chí Minh':['Bình Dương','Đồng Nai','Long An'],
                'Hà Nội':['Bắc Ninh','Hưng Yên','Hà Nam'],
                'Đà Nẵng':['Quảng Nam','Thừa Thiên Huế']
            }.get(province.name, [])
            if nearby:
                suggestions.append(f"💡 Thử tìm ở **{', '.join(nearby[:2])}** (lân cận)?")
        if not suggestions:
            suggestions.append("💡 Thử bỏ bớt một số tiêu chí để có nhiều lựa chọn hơn?")
        return "\n\n**GỢI Ý:**\n" + "\n".join(suggestions[:3]) if suggestions else ""

    def _get_fallback_response(self) -> str:
        return ("Xin lỗi, AI chatbot tạm thời gặp vấn đề kỹ thuật. 😔\n\n"
                "Bạn có thể:\n"
                "- Thử lại sau vài giây\n"
                "- Tìm kiếm phòng trực tiếp tại trang chủ\n"
                "- Liên hệ support: support@phongtroNMA.vn")

    # ===== Public helper APIs for external modules (views/tests) =====

def get_quota_cooldown_remaining() -> int:
    """Số giây cooldown quota còn lại (0 nếu không trong cooldown)."""
    if _LAST_QUOTA_EXHAUSTED_AT is None:
        return 0
    elapsed = time.time() - _LAST_QUOTA_EXHAUSTED_AT
    remaining = _QUOTA_COOLDOWN_SECONDS - elapsed
    return int(remaining) if remaining > 0 else 0


def is_in_quota_cooldown() -> bool:
    return get_quota_cooldown_remaining() > 0

# ===== Reattach helper methods to class (indent fix) =====


# Singleton instance
_grop_chatbot = None

def get_grop_chatbot() -> GropChatbot:
    """Lấy singleton instance của Grop chatbot.

    Sau khi deploy cập nhật code, instance cũ (được tạo trước) có thể thiếu các method mới
    (ví dụ: _enhance_message_with_parsers). Hàm này kiểm tra và tự động khởi tạo lại nếu thiếu.
    """
    global _grop_chatbot
    needs_reinit = False
    if _grop_chatbot is None:
        needs_reinit = True
    else:
        # Kiểm tra các method quan trọng đã tồn tại chưa (tránh AttributeError do instance cũ)
        critical_methods = [
            '_enhance_message_with_parsers',
            '_call_grop_with_retry',
            'get_response'
        ]
        for m in critical_methods:
            if not hasattr(_grop_chatbot, m):
                logger.warning(f"♻️ Grop instance missing method '{m}', reinitializing singleton.")
                needs_reinit = True
                break

    if needs_reinit:
        try:
            _grop_chatbot = GropChatbot()
        except ValueError as e:
            logger.error(f"❌ Cannot initialize Grop: {e}")
            raise
    return _grop_chatbot
