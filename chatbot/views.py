import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from .models import ChatMessage
from website.models import RentalPost, Province, District, Ward, Feature
from django.db.models import Q, Avg, Min, Max, Count
from django.conf import settings
from .vietnamese_parser import ConversationMemory
from django.utils import timezone
import uuid
import logging
import re
from decimal import Decimal
import unicodedata

# Setup logging
logger = logging.getLogger(__name__)

# ===== HELPER: Phone Masking =====
def _mask_phone_helper(phone: str | None, user) -> str | None:
    """
    Mask phone number for unauthenticated users.
    Authenticated: show full phone.
    Anonymous: mask middle digits (0909***456).
    """
    if not phone:
        return None
    if user and user.is_authenticated:
        return phone
    phone_str = str(phone).strip()
    if len(phone_str) < 6:
        return phone_str[:2] + '***'
    return phone_str[:4] + '***' + phone_str[-3:]

# ===== GROP AI INTEGRATION =====
USE_GROP_AI = True  # Toggle để bật/tắt Grop AI

# (Legacy quota globals removed) Trạng thái quota được quản lý bên trong grop_service (circuit breaker)

try:
    from .grop_service import get_grop_chatbot, is_in_quota_cooldown, get_quota_cooldown_remaining
    GROP_AVAILABLE = True
    logger.info("✅ Grop AI service imported successfully")
except Exception as e:
    GROP_AVAILABLE = False
    logger.warning(f"⚠️ Grop AI not available: {e}")
    logger.info("💡 Chatbot will use rule-based fallback")


def visible_posts_qs():
    """Queryset các bài đang hiển thị: đã duyệt, không xóa, chưa cho thuê, chưa hết hạn."""
    now = timezone.now()
    return (
        RentalPost.objects
        .filter(is_approved=True, is_deleted=False, is_rented=False)
        .filter(Q(expired_at__isnull=True) | Q(expired_at__gt=now))
    )


def debug_database():
    """Debug function để kiểm tra dữ liệu database"""
    try:
        total_posts = RentalPost.objects.count()
        active_posts = visible_posts_qs().count()

        # Lấy một vài phòng trọ mẫu (chỉ bài đang hiển thị)
        sample_posts = visible_posts_qs()[:3]

        debug_info = f"""
        🔍 DEBUG DATABASE:
        - Tổng số tin: {total_posts}
        - Tin đang hiển thị: {active_posts}
        - Tin mẫu: {len(sample_posts)}
        """

        for post in sample_posts:
            debug_info += f"\n- {post.title} | {post.price:,.0f} VNĐ | {post.area}m² | {post.province.name if post.province else 'N/A'}"

        return debug_info
    except Exception as e:
        return f"Lỗi debug: {str(e)}"


def simple_room_search(message):
    """Tìm kiếm phòng trọ đơn giản"""
    try:
        # Kiểm tra database trước
        total_posts = RentalPost.objects.count()
        if total_posts == 0:
            return "❌ Hiện tại chưa có tin đăng phòng trọ nào trong hệ thống.\n\n💡 **Gợi ý:**\n• Hãy đăng tin phòng trọ đầu tiên\n• Hoặc liên hệ admin để thêm dữ liệu mẫu"

        # Tìm kiếm đơn giản
        rooms = visible_posts_qs().order_by('-created_at')[:5]

        if rooms:
            result = f"🔍 **Tìm thấy {len(rooms)} phòng trọ:**\n\n"

            for i, room in enumerate(rooms, 1):
                result += f"🏠 **{i}. {room.title}**\n"
                result += f"💰 **Giá:** {format_currency_vn(resolve_price_vnd(room.price)):s} VNĐ/tháng\n"
                result += f"📐 **Diện tích:** {room.area} m²\n"

                if room.province:
                    result += f"📍 **Địa điểm:** {room.province.name}"
                    if room.district:
                        result += f" - {room.district.name}"
                    result += "\n"

                # Hiển thị danh mục
                category_name = dict(RentalPost.CATEGORY_CHOICES).get(room.category, room.category)
                result += f"🏷️ **Loại:** {category_name}\n"

                result += f"📝 **Mô tả:** {room.description[:100]}...\n"
                # Thêm link chi tiết để các intent như 'liên hệ' có thể tham chiếu post
                result += f"👉 [Xem chi tiết](/post/{room.pk}/)\n\n"

            result += "💡 **Lưu ý:** Đây là tất cả phòng trọ hiện có. Hãy liên hệ trực tiếp với chủ trọ để biết thêm chi tiết!"
            return result
        else:
            return "❌ Không tìm thấy phòng trọ nào đang hiển thị.\n\n💡 **Có thể:**\n• Tất cả tin đăng đang chờ duyệt\n• Hoặc đã bị xóa\n• Hãy thử lại sau hoặc liên hệ admin"

    except Exception as e:
        logger.error(f"Error in simple room search: {e}")
        return f"❌ Lỗi khi tìm kiếm: {str(e)}\n\n{debug_database()}"


# ====== Helpers cho parsing và định dạng giá ======
def format_currency_vn(amount: int) -> str:
    """Định dạng tiền VND theo kiểu Việt Nam: 11.000.000"""
    try:
        return f"{amount:,.0f}".replace(',', '.')
    except Exception:
        return str(amount)


def resolve_price_vnd(raw_price) -> int:
    """Chuyển giá trong DB sang VND hiển thị.
    Nếu DB lưu 11 (triệu) thì trả về 11_000_000; nếu đã là VND (>= 1000) thì giữ nguyên."""
    try:
        value = int(raw_price)
        if value < 1000:
            return value * 1_000_000
        return value
    except Exception:
        try:
            return int(Decimal(str(raw_price)))
        except Exception:
            return 0


def parse_price_from_text(message: str):
    """Parse giá từ câu tự nhiên. Trả về tuple (min_vnd, max_vnd, exact_vnd)
    - exact_vnd: khi người dùng nói 1 con số cụ thể (ví dụ 1 triệu)
    - min/max: cho khoảng (ví dụ 3-5 triệu)
    Hỗ trợ: 'triệu|tr', 'k|ngàn|nghìn', 'vnd|đ|đồng'"""
    text = message.lower()
    text = text.replace('nghìn', 'k').replace('ngàn', 'k').replace('đồng', 'vnd').replace('đ', 'vnd')

    # Khoảng giá: 3-5 triệu, 3 đến 5 tr
    range_pattern = r"(\d+[\.,]?\d*)\s*(triệu|tr|trieu|k|vnd)?\s*(đến|toi|tới|->|–|-|~)\s*(\d+[\.,]?\d*)\s*(triệu|tr|trieu|k|vnd)?"
    m = re.search(range_pattern, text)
    if m:
        n1, u1, _, n2, u2 = m.groups()
        v1 = number_to_vnd(n1, u1)
        v2 = number_to_vnd(n2, u2 or u1)
        if v1 and v2:
            return (min(v1, v2), max(v1, v2), None)

    # Một giá cụ thể: 1.2 triệu, 800k, 1200000 vnd, 'giá 1tr'
    single_pattern = r"giá\s*(khoảng|tầm|=|là)?\s*(\d+[\.,]?\d*)\s*(triệu|tr|trieu|k|vnd)?"
    m2 = re.search(single_pattern, text)
    if not m2:
        # fallback: có số + đơn vị nhưng không có chữ 'giá' (chỉ 2 groups)
        fallback = re.search(r"(\d+[\.,]?\d*)\s*(triệu|tr|trieu|k|vnd)", text)
        if fallback:
            n = fallback.group(1)
            unit = fallback.group(2)
            v = number_to_vnd(n, unit)
            if v:
                return (None, None, v)
    else:
        # single_pattern có 3 hoặc 4 groups (group(2)=number, group(3)=unit?)
        try:
            n = m2.group(2)
            unit = m2.group(3)
            v = number_to_vnd(n, unit)
            if v:
                return (None, None, v)
        except IndexError:
            # Defensive: pattern unexpected
            pass

    return (None, None, None)


def parse_area_from_text(message: str):
    """Parse diện tích từ câu. Trả về (min_area, max_area, exact_area).
    Hỗ trợ: 'trên 90m²', 'dưới 50m²', '30-50m²', 'khoảng 40m²', '23 m vuong'"""
    text = message.lower()
    # Normalize various area formats to 'm²' with space before it
    text = text.replace('m2', ' m²').replace('met vuong', ' m²').replace('mét vuông', ' m²')
    text = text.replace('m vuông', ' m²').replace('m vuong', ' m²')
    # Collapse multiple spaces
    text = ' '.join(text.split())

    # Khoảng: 30-50m², 30 đến 50m²
    range_pattern = r"(\d+[\.,]?\d*)\s*(đến|toi|tới|->|–|-|~)\s*(\d+[\.,]?\d*)\s*m"
    m = re.search(range_pattern, text)
    if m:
        n1, _, n2 = m.group(1), m.group(2), m.group(3)
        try:
            v1, v2 = float(n1.replace(',', '.')), float(n2.replace(',', '.'))
            return (min(v1, v2), max(v1, v2), None)
        except:
            pass

    # Trên X: trên 90m², từ 50m²
    above_pattern = r"(trên|từ|tu|>|>=)\s*(\d+[\.,]?\d*)\s*m"
    m2 = re.search(above_pattern, text)
    if m2:
        try:
            val = float(m2.group(2).replace(',', '.'))
            return (val, None, None)  # min only
        except:
            pass

    # Dưới X: dưới 50m², tối đa 30m²
    below_pattern = r"(dưới|duoi|tối đa|toi da|<|<=)\s*(\d+[\.,]?\d*)\s*m"
    m3 = re.search(below_pattern, text)
    if m3:
        try:
            val = float(m3.group(2).replace(',', '.'))
            return (None, val, None)  # max only
        except:
            pass

    # Exact: khoảng 40m², diện tích 35m², or just plain "23 m²"
    exact_pattern = r"(khoảng|diện tích|dien tich|dt|=|là|nha|phong|can)\s+(\d+[\.,]?\d*)\s*m"
    m4 = re.search(exact_pattern, text)
    if m4:
        try:
            val = float(m4.group(2).replace(',', '.'))
            tolerance = val * 0.1  # ±10%
            return (val - tolerance, val + tolerance, val)
        except:
            pass

    # Fallback: just number + m (like "23 m²")
    simple_pattern = r"(\d+[\.,]?\d*)\s*m[²²2]?"
    m5 = re.search(simple_pattern, text)
    if m5:
        try:
            val = float(m5.group(1).replace(',', '.'))
            # Only return if context suggests area (not random number)
            if any(kw in text for kw in ['dien tich', 'diện tích', 'm²', 'm2', 'vuong', 'vuông', 'nha', 'phong', 'can']):
                tolerance = val * 0.1  # ±10%
                return (val - tolerance, val + tolerance, val)
        except:
            pass

    # Fallback: "diện tích trên 90" không có m²
    if 'diện tích' in text or 'dien tich' in text:
        above_no_m = re.search(r"(trên|tu|từ)\s*(\d+)", text)
        if above_no_m:
            try:
                val = float(above_no_m.group(2))
                return (val, None, None)
            except:
                pass

    return (None, None, None)




def parse_quantity_from_text(message: str) -> int:
    """Parse số lượng phòng muốn hiển thị từ câu.
    Hỗ trợ: 'tìm 1 phòng', 'tìm 3 căn', 'cho tôi xem 5 phòng', 'tìm các' (=all=5)
    Default: 5"""
    text = message.lower()

    # Pattern: "tìm 3 phòng", "cho tôi 2 căn", "xem 4 phòng"
    patterns = [
        r'tìm\s+(\d+)\s*(phòng|căn|cái)',
        r'tim\s+(\d+)\s*(phong|can|cai)',
        r'cho\s+(tôi|toi)\s+(xem)?\s*(\d+)',
        r'xem\s+(\d+)\s*(phòng|căn)',
        r'hiển thị\s+(\d+)',
        r'hien thi\s+(\d+)',
        r'(\d+)\s+phòng',
        r'(\d+)\s+căn',
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                # Lấy số từ group cuối cùng có chữ số
                for group in m.groups():
                    if group and group.isdigit():
                        num = int(group)
                        # Giới hạn từ 1-10
                        return max(1, min(num, 10))
            except:
                pass

    # Nếu có "các", "tất cả", "hết" → hiển thị nhiều (5)
    if any(word in text for word in ['các', 'cac', 'tất cả', 'tat ca', 'hết', 'het', 'all']):
        return 5

    # Default: 1 nếu có "tìm", "cho tôi", không thì 5
    if any(word in text for word in ['tìm', 'tim', 'cho toi', 'cho tôi']):
        return 1

    return 5


def number_to_vnd(num_str: str, unit: str | None) -> int | None:
    try:
        value = float(num_str.replace('.', '').replace(',', '.'))
        if not unit or unit in ['vnd']:
            return int(value)
        if unit in ['k']:
            return int(value * 1_000)
        if unit in ['triệu', 'tr', 'trieu']:
            return int(value * 1_000_000)
        return int(value)
    except Exception:
        return None


def normalize_text(s: str) -> str:
    # Lowercase + remove accents + collapse spaces
    s = s.lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ' '.join(s.split())


PROVINCE_SYNONYMS = {
    'hcm': 'ho chi minh',
    'tphcm': 'ho chi minh',
    'tp hcm': 'ho chi minh',
    'tp.hcm': 'ho chi minh',  # Support dot separator
    'tphồ chí minh': 'ho chi minh',
    'sai gon': 'ho chi minh',
    'saigon': 'ho chi minh',
    'tp ho chi minh': 'ho chi minh',
    'thanh pho ho chi minh': 'ho chi minh',
    'hn': 'ha noi',
    'hanoi': 'ha noi',
    'tp.hn': 'ha noi',  # Support Hà Nội with dot
}


def find_province_in_text(message: str):
    """Trả về một đối tượng Province nếu phát hiện trong câu; ngược lại None."""
    norm = normalize_text(message)
    tokens = set(norm.split())

    # Map synonyms trước (ưu tiên khớp cụm từ)
    for key, target in PROVINCE_SYNONYMS.items():
        if f" {key} " in f" {norm} ":
            if 'ho chi minh' in target:
                prov = Province.objects.filter(name__icontains='Hồ Chí Minh').first()
                if prov:
                    return prov
            elif 'ha noi' in target:
                prov = Province.objects.filter(name__icontains='Hà Nội').first()
                if prov:
                    return prov

    # Bổ sung: match rút gọn cho các thành phố có tiền tố "Thành phố" trong DB
    # Người dùng thường chỉ gõ "hà nội", "ho chi minh", "da nang".
    if 'ha' in tokens and 'noi' in tokens:
        prov = Province.objects.filter(name__icontains='Hà Nội').first()
        if prov:
            return prov
    if 'ho' in tokens and 'chi' in tokens and 'minh' in tokens:
        prov = Province.objects.filter(name__icontains='Hồ Chí Minh').first()
        if prov:
            return prov
    # 'đà' sau normalize thành 'đa' (không bỏ dấu đ) → chấp nhận cả 'da' và 'đa'
    if ('da' in tokens or 'đa' in tokens) and 'nang' in tokens:
        prov = Province.objects.filter(name__icontains='Đà Nẵng').first()
        if prov:
            return prov

    # Duyệt toàn bộ tỉnh thành đã có trong DB với logic tránh false positive
    for prov in Province.objects.all():
        if not prov.name:
            continue
        prov_norm = normalize_text(prov.name)
        # BỎ QUA tiền tố "Tỉnh"/"Thành phố"/"TP" khi matching
        prov_norm_clean = prov_norm
        for prefix in ['tinh ', 'thanh pho ', 'tp ', 'thanh pho ho chi minh', 'tp ho chi minh']:
            if prov_norm_clean.startswith(prefix):
                prov_norm_clean = prov_norm_clean[len(prefix):].strip()
                break

        prov_tokens = [t for t in prov_norm_clean.split() if len(t) > 1]

        if not prov_tokens:
            continue

        if len(prov_tokens) == 1:
            # Match theo từ nguyên vẹn (word-level)
            if prov_tokens[0] in tokens:
                return prov
        else:
            # Yêu cầu tất cả token của tên tỉnh đều xuất hiện (sau khi đã bỏ tiền tố)
            if all(t in tokens for t in prov_tokens):
                return prov

    return None


def find_district_in_text(message: str, province: Province | None = None):
    """Thử phát hiện quận/huyện trong câu. Nếu có province thì chỉ tìm trong province đó."""
    norm = normalize_text(message)
    districts = District.objects.all()
    if province:
        districts = districts.filter(province=province)
    for d in districts:
        if not d.name:
            continue
        if normalize_text(d.name) in norm:
            return d
    return None




CATEGORY_KEYWORDS = {
    # Thứ tự quan trọng: phrases dài hơn phải check trước!
    'canho_mini': ['căn hộ mini', 'can ho mini'],
    'canho_dichvu': ['căn hộ dịch vụ', 'can ho dich vu'],
    'nhanguyencan': ['nhà nguyên căn', 'nguyên căn', 'nhà riêng', 'nha nguyen can'],
    'phongtro': ['phòng trọ', 'nhà trọ', 'phong tro', 'nha tro'],
    'canho': ['căn hộ', 'can ho'],
    'oghep': ['ở ghép', 'o ghep', 'ghép'],
    'matbang': ['mặt bằng', 'văn phòng', 'mat bang', 'van phong'],
}

def detect_category_from_text(message: str):
    """Phát hiện loại phòng từ câu."""
    norm = normalize_text(message)
    for cat_code, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if normalize_text(kw) in norm:
                return cat_code
    return None



def advanced_room_search(message: str) -> str:
    """Tìm phòng nâng cao theo nhiều tiêu chí: giá, diện tích, địa điểm, loại phòng."""
    try:
        total_posts = RentalPost.objects.count()
        if total_posts == 0:
            return "❌ Hiện tại chưa có tin đăng phòng trọ nào trong hệ thống."

        # Parse tất cả tiêu chí
        min_price, max_price, exact_price = parse_price_from_text(message)
        min_area, max_area, exact_area = parse_area_from_text(message)
        province = find_province_in_text(message)
        district = find_district_in_text(message, province)
        category = detect_category_from_text(message)

        # Log để debug
        logger.info(f"[AdvancedSearch] Query: {message[:100]}")
        logger.info(f"[AdvancedSearch] Detected - Province: {province.name if province else None}, District: {district.name if district else None}, Category: {category}")
        logger.info(f"[AdvancedSearch] Price: exact={exact_price}, range=({min_price}, {max_price})")
        logger.info(f"[AdvancedSearch] Area: exact={exact_area}, range=({min_area}, {max_area})")

        # Xây dựng queryset (chỉ bài đang hiển thị)
        qs = visible_posts_qs()

        # Filter địa điểm
        if province:
            qs = qs.filter(province=province)
            logger.info(f"[AdvancedSearch] Filtering by province: {province.name}")
        if district:
            qs = qs.filter(district=district)
            logger.info(f"[AdvancedSearch] Filtering by district: {district.name}")

        # Filter loại phòng
        if category:
            qs = qs.filter(category=category)
            logger.info(f"[AdvancedSearch] Filtering by category: {category}")

        # Filter giá - xử lý cả VND và triệu (DB có thể lưu cả 2 format)
        if exact_price:
            near_low = int(exact_price * 0.95)
            near_high = int(exact_price * 1.05)
            near_low_million = near_low // 1_000_000
            near_high_million = near_high // 1_000_000
            qs = qs.filter(
                Q(price__gte=near_low, price__lte=near_high) |  # Format VND
                Q(price__gte=near_low_million, price__lte=near_high_million)  # Format triệu
            )
            logger.info(f"[AdvancedSearch] Exact price filter: {near_low:,} - {near_high:,} VND or {near_low_million} - {near_high_million} triệu")
        elif min_price and max_price:
            min_million = min_price // 1_000_000
            max_million = max_price // 1_000_000
            qs = qs.filter(
                Q(price__gte=min_price, price__lte=max_price) |  # Format VND
                Q(price__gte=min_million, price__lte=max_million)  # Format triệu
            )
            logger.info(f"[AdvancedSearch] Price range filter: {min_price:,} - {max_price:,} VND or {min_million} - {max_million} triệu")
        elif min_price:  # Chỉ có min
            min_million = min_price // 1_000_000
            qs = qs.filter(Q(price__gte=min_price) | Q(price__gte=min_million))
            logger.info(f"[AdvancedSearch] Min price filter: >= {min_price:,} VND or >= {min_million} triệu")
        elif max_price:  # Chỉ có max
            max_million = max_price // 1_000_000
            qs = qs.filter(Q(price__lte=max_price) | Q(price__lte=max_million))
            logger.info(f"[AdvancedSearch] Max price filter: <= {max_price:,} VND or <= {max_million} triệu")

        # Filter diện tích
        if exact_area:
            qs = qs.filter(area__gte=min_area, area__lte=max_area)
            logger.info(f"[AdvancedSearch] Exact area filter: {min_area} - {max_area} m²")
        elif min_area and max_area:
            qs = qs.filter(area__gte=min_area, area__lte=max_area)
            logger.info(f"[AdvancedSearch] Area range filter: {min_area} - {max_area} m²")
        elif min_area:  # Trên X m²
            qs = qs.filter(area__gte=min_area)
            logger.info(f"[AdvancedSearch] Area min filter: >= {min_area} m²")
        elif max_area:  # Dưới X m²
            qs = qs.filter(area__lte=max_area)
            logger.info(f"[AdvancedSearch] Area max filter: <= {max_area} m²")

        # Parse số lượng muốn hiển thị
        limit = parse_quantity_from_text(message)

        # Sort và lấy kết quả
        rooms = list(qs.order_by('-created_at')[:limit])

        if not rooms:
            criteria = []
            if min_price or max_price or exact_price:
                if exact_price:
                    criteria.append(f"giá {format_currency_vn(exact_price)} VNĐ")
                elif min_price and max_price:
                    criteria.append(f"giá {format_currency_vn(min_price)}-{format_currency_vn(max_price)} VNĐ")
                elif min_price:
                    criteria.append(f"giá từ {format_currency_vn(min_price)} VNĐ")
                elif max_price:
                    criteria.append(f"giá dưới {format_currency_vn(max_price)} VNĐ")
            if min_area or max_area or exact_area:
                if exact_area:
                    criteria.append(f"diện tích ~{exact_area:.0f}m²")
                elif min_area and max_area:
                    criteria.append(f"diện tích {min_area:.0f}-{max_area:.0f}m²")
                elif min_area:
                    criteria.append(f"diện tích trên {min_area:.0f}m²")
                elif max_area:
                    criteria.append(f"diện tích dưới {max_area:.0f}m²")
            if province:
                loc = district.name + ", " + province.name if district else province.name
                criteria.append(f"ở {loc}")
            if category:
                cat_name = dict(RentalPost.CATEGORY_CHOICES).get(category, category)
                criteria.append(f"loại {cat_name}")

            crit_text = ", ".join(criteria) if criteria else "yêu cầu của bạn"
            return f"❌ Không tìm thấy phòng nào phù hợp với {crit_text}.\n\n💡 **Gợi ý:** Thử mở rộng tiêu chí hoặc bỏ bớt điều kiện."

        # Format kết quả
        header_parts = []
        if min_area or max_area:
            if min_area and not max_area:
                header_parts.append(f"diện tích ≥ {min_area:.0f}m²")
            elif max_area and not min_area:
                header_parts.append(f"diện tích ≤ {max_area:.0f}m²")
            elif min_area and max_area:
                header_parts.append(f"diện tích {min_area:.0f}-{max_area:.0f}m²")
        if province:
            loc = district.name + ", " + province.name if district else province.name
            header_parts.append(f"ở {loc}")
        if category:
            cat_name = dict(RentalPost.CATEGORY_CHOICES).get(category, category)
            header_parts.append(cat_name)

        header = " - ".join(header_parts) if header_parts else "phù hợp"
        count_text = f"{len(rooms)}/{limit}" if limit < 10 else f"{len(rooms)}"
        result = [f"🔍 **Tìm thấy {count_text} phòng trọ {header}:**\n"]

        for i, room in enumerate(rooms, 1):
            price_txt = format_currency_vn(resolve_price_vnd(room.price))
            line = (
                f"{i}. **[{room.title}](/post/{room.pk}/)**\n"
                f"   • 💰 Giá: {price_txt} VNĐ/tháng\n"
                f"   • 📐 Diện tích: {room.area} m²\n"
            )
            if room.province:
                line += f"   • 📍 Địa điểm: {room.province.name}"
                if room.district:
                    line += f" - {room.district.name}"
                line += "\n"
            line += f"   • 👉 [Xem chi tiết](/post/{room.pk}/)\n"
            result.append(line)

        result.append("\n💡 **Mẹo:** Bạn có thể kết hợp nhiều tiêu chí. Ví dụ: 'phòng 3-5 triệu, diện tích trên 30m² ở TPHCM'")
        return "\n".join(result)

    except Exception as e:
        logger.error(f"advanced_room_search error: {e}")
        return simple_room_search(message)


def location_room_list_response(message: str) -> str:
    """Liệt kê nhiều phòng theo địa điểm (tối đa 5)."""
    province = find_province_in_text(message)
    if not province:
        return "❌ Mình chưa nhận ra bạn muốn tìm ở tỉnh/thành nào. Hãy thử: 'xem phòng ở TP.HCM'"

    district = find_district_in_text(message, province)
    qs = visible_posts_qs().filter(province=province)
    if district:
        qs = qs.filter(district=district)

    rooms = list(qs.order_by('-created_at')[:5])
    if not rooms:
        if district:
            return f"❌ Hiện chưa có phòng trọ nào ở {district.name}, {province.name}."
        return f"❌ Hiện chưa có phòng trọ nào ở {province.name}."

    header_loc = district.name + ", " + province.name if district else province.name
    result = [f"📍 **Các phòng trọ mới nhất ở {header_loc}:**\n"]
    for i, room in enumerate(rooms, 1):
        price_txt = format_currency_vn(resolve_price_vnd(room.price))
        line = (
            f"{i}. **[{room.title}](/post/{room.pk}/)**\n"
            f"   • 💰 Giá: {price_txt} VNĐ/tháng\n"
            f"   • 📐 Diện tích: {room.area} m²\n"
            f"   • 👉 [Xem chi tiết](/post/{room.pk}/)\n"
        )
        result.append(line)
    result.append("\n💡 Bạn có thể thêm giá hoặc diện tích để lọc chính xác hơn. Ví dụ: 'phòng 3-5 triệu ở TPHCM'.")
    return "\n".join(result)


def intelligent_room_search(message: str) -> str:
    """Tìm phòng thông minh theo giá người dùng nêu."""
    try:
        total_posts = RentalPost.objects.count()
        if total_posts == 0:
            return "❌ Hiện tại chưa có tin đăng phòng trọ nào trong hệ thống."

        min_vnd, max_vnd, exact_vnd = parse_price_from_text(message)
        province = find_province_in_text(message)

        qs = visible_posts_qs()
        if province:
            qs = qs.filter(province=province)

        selected = None
        if exact_vnd:
            # Dữ liệu có thể là VND hoặc triệu -> thử cả hai
            near_low = int(exact_vnd * 0.95)
            near_high = int(exact_vnd * 1.05)
            qs_exact = qs.filter(
                Q(price__gte=near_low, price__lte=near_high) |
                Q(price__gte=near_low // 1_000_000, price__lte=near_high // 1_000_000)
            ).order_by('price')
            selected = qs_exact.first()
        elif min_vnd and max_vnd:
            qs_range = qs.filter(
                Q(price__gte=min_vnd, price__lte=max_vnd) |
                Q(price__gte=min_vnd // 1_000_000, price__lte=max_vnd // 1_000_000)
            ).order_by('price')
            selected = qs_range.first()

        if selected:
            price_vnd = resolve_price_vnd(selected.price)
            price_txt = format_currency_vn(price_vnd)
            result = (
                f"🔎 **Tìm thấy 1 phòng trọ phù hợp giá yêu cầu:**\n\n"
                f"🏠 **[{selected.title}](/post/{selected.pk}/)**\n"
                f"💰 **Giá:** {price_txt} VNĐ/tháng\n"
                f"📐 **Diện tích:** {selected.area} m²\n"
            )
            if selected.province:
                result += f"📍 **Địa điểm:** {selected.province.name}"
                if getattr(selected, 'district', None):
                    result += f" - {selected.district.name}"
                result += "\n"
            category_name = dict(RentalPost.CATEGORY_CHOICES).get(selected.category, selected.category)
            result += f"🏷️ **Loại:** {category_name}\n"
            result += f"📝 **Mô tả:** {selected.description[:120]}...\n\n"
            result += f"👉 [**Xem chi tiết phòng**](/post/{selected.pk}/)"
            return result

        # Không parse được giá hoặc không tìm thấy theo giá -> nếu có tỉnh thì liệt kê phòng theo tỉnh
        if province:
            return location_room_list_response(message)
        return simple_room_search(message)
    except Exception as e:
        logger.error(f"intelligent_room_search error: {e}")
        return simple_room_search(message)


def get_smart_response(message, session=None, user=None):
    """Trả lời thông minh dựa trên dữ liệu thực tế"""
    message_lower = message.lower()

    # Debug database
    if any(word in message_lower for word in ['debug', 'kiểm tra', 'dữ liệu', 'database']):
        return debug_database()

    # Tìm kiếm phòng trọ - dùng advanced search
    elif any(word in message_lower for word in ['tìm phòng', 'xem phòng', 'xem các phòng', 'cho tôi xem', 'tìm nhà', 'phòng trọ', 'căn hộ', 'nhà thuê', 'tìm cho tôi', 'tìm giúp', 'cho xem', 'có phòng', 'có nhà']):
        return advanced_room_search(message)

    # ===== ADMIN/SUPPORT CONTACT (ưu tiên) =====
    admin_kw = [
        'admin', 'quản trị', 'quan tri', 'quản trị viên', 'quan tri vien',
        'cskh', 'chăm sóc khách hàng', 'cham soc khach hang', 'support', 'hỗ trợ', 'ho tro'
    ]
    # Nếu có ý định hỏi admin và không nhắc tới người đăng/chủ nhà thì trả về thông tin support
    if any(kw in message_lower for kw in admin_kw) and not any(kw in message_lower for kw in [
        'người đăng','nguoi dang','chủ nhà','chu nha','chủ trọ','chu tro'
    ]):
        support_email = 'support@phongtroNMA.vn'
        hotline = '1900-xxxx'
        return (
            "🛠️ Thông tin hỗ trợ / quản trị viên:\n"
            f"- 📧 Email: {support_email}\n"
            f"- ☎️ Hotline: {hotline} (giờ hành chính)\n"
            "- 💬 Chat trực tuyến: dùng chatbot này đặt câu hỏi, hệ thống sẽ chuyển tiếp nếu cần\n"
            "- 🚨 Báo cáo vi phạm: mở trang chi tiết phòng và bấm \"Báo cáo vi phạm\"\n"
            "- ⏱️ Thời gian phản hồi email: 24-48 giờ"
        )

    # ===== RULE-BASED CONTACT INFO INTENT (fallback when Grop AI disabled or failed) =====
    contact_keywords = [
        'liên hệ','lien he','số điện thoại','so dien thoai','điện thoại','dien thoai',
        'người đăng','nguoi dang','chủ nhà','chu nha','chủ trọ','chu tro','sdt','phone','contact','thông tin người đăng','thong tin nguoi dang'
    ]
    if any(kw in message_lower for kw in contact_keywords):
        try:
            # Attempt to resolve post id from current message first (/post/<id>/)
            import re
            post_id = None
            m = re.search(r"/post/(\d+)/", message)
            if m:
                try:
                    post_id = int(m.group(1))
                except Exception:
                    post_id = None

            # If not found, scan last 5 bot responses in conversation memory for a link
            if not post_id:
                try:
                    # Access thread-local request via middleware? Not available here.
                    # We embed a light heuristic: ConversationMemory stored in session (passed externally in chat_api)
                    # chat_api will call this function and then add message afterward, so we cannot read session here directly.
                    # => We expose a global accessor via ConversationMemory (if session available through thread locals). If not, skip.
                    from .vietnamese_parser import ConversationMemory
                    sess = session
                except Exception:
                    sess = None
                if sess:
                    try:
                        hist = ConversationMemory.get_history(sess)
                        for exch in reversed(hist[-5:]):
                            bot_resp = (exch.get('bot') or '')
                            m2 = re.search(r"/post/(\d+)/", bot_resp)
                            if m2:
                                post_id = int(m2.group(1))
                                break
                    except Exception:
                        pass

            if not post_id:
                return (
                    "Mình cần biết bạn đang hỏi liên hệ của bài nào. "
                    "Hãy bấm vào link 'Xem chi tiết' của một phòng (có dạng /post/<ID>/) rồi hỏi lại 'cho mình số điện thoại'."
                )

            from website.models import RentalPost
            try:
                post = RentalPost.objects.get(id=post_id)
            except RentalPost.DoesNotExist:
                return "Không tìm thấy bài đăng này nữa (có thể đã bị xóa hoặc hết hạn)."

            owner = getattr(post, 'user', None)
            owner_username = owner.username if owner else None
            try:
                owner_full = owner.get_full_name().strip() if owner and owner.get_full_name().strip() else None
            except Exception:
                owner_full = None
            phone = getattr(post, 'phone_number', None)
            if not phone and owner and hasattr(owner, 'customerprofile'):
                phone = getattr(owner.customerprofile, 'phone', None)

            # Mask phone for unauthenticated users
            phone_display = _mask_phone_helper(phone, user)

            link = f"/post/{post.id}/"
            lines = ["📞 Thông tin liên hệ bài đăng:"]
            if owner_full and owner_username and owner_full != owner_username:
                lines.append(f"- 👤 Người đăng: {owner_full} ({owner_username})")
            elif owner_full or owner_username:
                lines.append(f"- 👤 Người đăng: {owner_full or owner_username}")
            else:
                lines.append("- 👤 Người đăng: (chưa có thông tin)")
            lines.append(f"- ☎️ Số điện thoại: {phone_display if phone_display else '(chưa cập nhật)'}")
            lines.append(f"- 🔗 Xem chi tiết: {link}")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Rule-based contact intent error: {e}")
            # Fall through to generic handling if something goes wrong

    # Thông tin tổng quan
    elif any(word in message_lower for word in ['thống kê', 'số liệu', 'tổng quan', 'hiện tại']):
        try:
            total_posts = RentalPost.objects.count()
            active_posts = visible_posts_qs().count()
            pending_posts = RentalPost.objects.filter(is_approved=False, is_deleted=False).count()

            # Thống kê giá (chỉ bài đang hiển thị)
            price_stats = visible_posts_qs().aggregate(
                avg_price=Avg('price'),
                min_price=Min('price'),
                max_price=Max('price')
            )

            result = f"""📊 **THỐNG KÊ WEBSITE HIỆN TẠI:**

📈 **TỔNG QUAN:**
• Tổng số tin đăng: {total_posts:,}
• Tin đang hiển thị: {active_posts:,}
• Tin chờ duyệt: {pending_posts:,}

💰 **GIÁ CẢ:**
• Giá trung bình: {format_currency_vn(resolve_price_vnd(price_stats['avg_price'] or 0))} VNĐ/tháng
• Giá thấp nhất: {format_currency_vn(resolve_price_vnd(price_stats['min_price'] or 0))} VNĐ/tháng
• Giá cao nhất: {format_currency_vn(resolve_price_vnd(price_stats['max_price'] or 0))} VNĐ/tháng

💡 **LƯU Ý:** Dữ liệu được cập nhật theo thời gian thực từ database."""

            return result
        except Exception as e:
            return f"❌ Lỗi khi lấy thống kê: {str(e)}\n\n{debug_database()}"

    # Hướng dẫn đăng tin
    elif any(word in message_lower for word in ['đăng tin', 'post', 'tạo tin', 'đăng bài']):
        return """📝 **HƯỚNG DẪN ĐĂNG TIN PHÒNG TRỌ:**

1️⃣ **CHUẨN BỊ THÔNG TIN:**
   • Tiêu đề hấp dẫn
   • Mô tả chi tiết về phòng
   • Giá thuê và diện tích
   • Địa chỉ cụ thể
   • Ảnh chất lượng cao

2️⃣ **CÁC BƯỚC ĐĂNG TIN:**
   • Đăng nhập tài khoản
   • Click "Đăng tin" ở góc phải
   • Chọn danh mục phù hợp
   • Điền đầy đủ thông tin
   • Upload ảnh và submit

3️⃣ **LƯU Ý QUAN TRỌNG:**
   • Tin đăng sẽ được duyệt trong 24h
   • Thông tin phải chính xác
   • Ảnh phải rõ nét
   • Tuân thủ quy định website

💡 **TIPS:** Tin đăng có ảnh đẹp sẽ được xem nhiều hơn!"""

    # Hướng dẫn tìm kiếm
    elif any(word in message_lower for word in ['tìm kiếm', 'search', 'lọc', 'bộ lọc']):
        return """🔍 **HƯỚNG DẪN TÌM KIẾM PHÒNG TRỌ:**

1️⃣ **TÌM KIẾM CƠ BẢN:**
   • Sử dụng thanh tìm kiếm ở trang chủ
   • Nhập từ khóa: "phòng trọ", "căn hộ", tên quận...
   • Browse theo danh mục

2️⃣ **BỘ LỌC NÂNG CAO:**
   • Click "Bộ lọc" để mở bộ lọc
   • Lọc theo giá: 1-3 triệu, 3-5 triệu...
   • Lọc theo diện tích: 20-30m², 30-50m²...
   • Lọc theo tính năng: máy lạnh, thang máy...

3️⃣ **MẸO TÌM KIẾM:**
   • Sử dụng từ khóa cụ thể
   • Kết hợp nhiều bộ lọc
   • Lưu tin yêu thích
   • Liên hệ trực tiếp chủ trọ

💡 **GỢI Ý:** Hãy hỏi tôi "tìm phòng trọ" để tôi tìm giúp!"""

    # Thông tin về tính năng
    elif any(word in message_lower for word in ['tính năng', 'feature', 'tiện ích']):
        return """✨ **CÁC TÍNH NĂNG PHÒNG TRỌ:**

🏠 **NỘI THẤT CƠ BẢN:**
   • Đầy đủ nội thất
   • Có gác
   • Có kệ bếp

❄️ **TIỆN NGHI:**
   • Có máy lạnh
   • Có máy giặt
   • Có tủ lạnh

🏢 **TIỆN ÍCH CHUNG:**
   • Có thang máy
   • Có bảo vệ 24/24
   • Có hầm để xe

🏡 **SINH HOẠT:**
   • Không chung chủ
   • Giờ giấc tự do

💡 **LƯU Ý:** Cân nhắc tính năng nào thực sự cần thiết!"""

    # Giá cả chung (không phải bảng giá VIP / dịch vụ đăng tin)
    elif any(word in message_lower for word in ['giá phòng', 'giá thuê', 'price', 'tiền phòng', 'chi phí phòng', 'khoảng giá']) or (('giá' in message_lower or 'tiền' in message_lower) and 'vip' not in message_lower and 'bảng giá' not in message_lower):
        return """💰 **THÔNG TIN VỀ GIÁ CẢ PHÒNG TRỌ (THUÊ):**

📊 **KHOẢNG GIÁ PHỔ BIẾN:**
   • Dưới 1 triệu: Phòng trọ cơ bản
   • 1-2 triệu: Phòng trọ có tiện nghi
   • 2-3 triệu: Phòng trọ đầy đủ tiện nghi
   • 3-5 triệu: Căn hộ mini, nhà nguyên căn nhỏ
   • 5-7 triệu: Căn hộ dịch vụ, nhà nguyên căn
   • 7-10 triệu: Căn hộ cao cấp
   • 10-15 triệu: Nhà nguyên căn lớn
   • Trên 15 triệu: Biệt thự, căn hộ cao cấp

💡 **YẾU TỐ ẢNH HƯỞNG GIÁ:**
   • Vị trí (trung tâm vs ngoại thành)
   • Diện tích
   • Tiện nghi (máy lạnh, thang máy...)
   • Loại hình (phòng trọ vs căn hộ)

🔍 **MẸO TIẾT KIỆM:** Tìm phòng ở khu vực ngoại thành, chia sẻ với bạn bè, hoặc chọn phòng trọ thay vì căn hộ."""

    # Bảng giá VIP / dịch vụ đăng tin (direct DB answer, fallback nếu lỗi)
    elif any(word in message_lower for word in ['bảng giá vip', 'bang gia vip', 'bảng giá dịch vụ', 'bang gia dich vu', 'giá vip', 'gia vip', 'gói vip', 'goi vip', 'vip 1', 'vip 2', 'vip 3', 'dịch vụ đăng tin', 'dich vu dang tin']):
        try:
            from website.models import VIPPackageConfig
            from django.utils import timezone
            vips = list(VIPPackageConfig.objects.filter(is_active=True).order_by('plan'))
            if vips:
                effective = timezone.now().strftime('%d/%m/%Y')
                lines = [f"📅 Áp dụng từ: {effective}", ""]
                for vip in vips:
                    price_vnd = int(vip.price)
                    price_txt = format_currency_vn(price_vnd)
                    color = vip.get_title_color_display().upper()
                    name = vip.get_plan_display()
                    duration = f"{vip.expire_days} ngày" if vip.expire_days != 7 else "1 tuần"
                    lines.append(
                        f"• {name}: {vip.posts_per_day} tin/ngày • Hạn {duration} • {color} • Giá: {price_txt}đ"
                    )
                lines.append("💡 Lưu ý: Giá có thể thay đổi. Kiểm tra trang 'Bảng giá' để cập nhật mới nhất.")
                return "\n".join(lines)
        except Exception as e:
            logger.warning(f"VIP pricing DB fetch failed: {e}")
        # Fallback static (aligned with current database)
        return """📅 Áp dụng (fallback)

• VIP 1: 5 tin/ngày • Hạn 1 tuần • MÀU ĐỎ • Giá: 500.000đ
• VIP 2: 3 tin/ngày • Hạn 3 ngày • MÀU XANH • Giá: 300.000đ
• VIP 3: 2 tin/ngày • Hạn 1 ngày • MÀU HỒNG • Giá: 150.000đ
💡 Lưu ý: Giá có thể thay đổi. Kiểm tra trang 'Bảng giá' để cập nhật mới nhất."""

    # Diện tích
    elif any(word in message_lower for word in ['diện tích', 'area', 'm2', 'mét vuông']):
        return """📐 **THÔNG TIN VỀ DIỆN TÍCH PHÒNG TRỌ:**

📏 **KHOẢNG DIỆN TÍCH PHỔ BIẾN:**
   • Dưới 20m²: Phòng trọ nhỏ, phù hợp 1 người
   • 20-30m²: Phòng trọ tiêu chuẩn, đủ cho 1-2 người
   • 30-50m²: Phòng trọ rộng, căn hộ mini
   • 50-70m²: Căn hộ 1 phòng ngủ
   • 70-90m²: Căn hộ 2 phòng ngủ
   • Trên 90m²: Nhà nguyên căn, căn hộ lớn

💡 **LƯU Ý KHI CHỌN DIỆN TÍCH:**
   • Cân nhắc số người ở
   • Tính toán chi phí thuê/m²
   • Kiểm tra không gian thực tế
   • Xem xét nhu cầu sinh hoạt

🔍 **MẸO:** Diện tích 25-35m² thường là lựa chọn tối ưu về giá cả và tiện nghi."""

    # Chào hỏi
    elif any(word in message_lower for word in ['xin chào', 'hello', 'chào', 'hi']):
        return """👋 **Chào bạn! Mình là trợ lý AI của PhòngTrọ NMA. Rất vui được hỗ trợ bạn.**

Mình có thể giúp bạn:
• 🔍 Tìm kiếm phòng trọ theo giá, diện tích, địa điểm
• 📊 Xem thống kê website
• 📝 Hướng dẫn đăng tin phòng trọ
• 💰 Tư vấn về giá cả và diện tích
• ✨ Thông tin tính năng phòng trọ

Bạn cứ hỏi bất cứ điều gì về phòng trọ nhé!

Ví dụ:
• "Tìm phòng trọ"
• "Thống kê website hiện tại"
• "Hướng dẫn đăng tin" """

    # Help
    elif any(word in message_lower for word in ['help', 'giúp', 'hướng dẫn', 'làm gì']):
        return """❓ **TÔI CÓ THỂ GIÚP BẠN:**

🔍 **TÌM KIẾM PHÒNG TRỌ:**
   • "Tìm phòng trọ"
   • "Tìm phòng ở Hà Nội"
   • "Phòng trọ giá 2 triệu"

📊 **THÔNG TIN THỐNG KÊ:**
   • "Thống kê website hiện tại"
   • "Số liệu tổng quan"

📝 **HƯỚNG DẪN:**
   • "Hướng dẫn đăng tin"
   • "Cách tìm kiếm hiệu quả"

💰 **TƯ VẤN:**
   • "Giá phòng trọ hiện tại"
   • "Diện tích phù hợp"
   • "Tính năng nên có"

💡 **MẸO:** Hãy hỏi cụ thể để tôi có thể hỗ trợ tốt nhất!"""

    else:
        return f"""🤔 **Tôi hiểu bạn đang hỏi về: "{message}"**

Tôi có thể giúp bạn với:
🔍 **Tìm kiếm phòng trọ** cụ thể
📊 **Thống kê và phân tích** website
📝 **Hướng dẫn đăng tin** và sử dụng website
💰 **Tư vấn về giá cả**, diện tích, tính năng

**Hãy hỏi cụ thể hơn nhé!** Ví dụ:
• "Tìm phòng trọ"
• "Thống kê website hiện tại"
• "Hướng dẫn đăng tin phòng trọ" """


@csrf_exempt
@require_http_methods(["POST"])
def chat_api(request):
    """API endpoint để xử lý tin nhắn chat"""
    try:
        logger.info("Chat API called")
        data = json.loads(request.body)
        message = data.get('message', '')
        session_id = data.get('session_id', str(uuid.uuid4()))

        logger.info(f"Message: {message}, Session: {session_id}")

        if not message.strip():
            return JsonResponse({'error': 'Tin nhắn không được để trống'}, status=400)

        # ===== VIP PRO MODE: Grop AI with circuit breaker =====
        response_mode = "rule-based"
        bot_response = None

        if USE_GROP_AI and GROP_AVAILABLE:
            in_cooldown = is_in_quota_cooldown()
            try:
                user = request.user if request.user.is_authenticated else None
                grop_bot = get_grop_chatbot()
                bot_response = grop_bot.get_response(
                    user_message=message,
                    user=user,
                    session_key=session_id,
                    session=request.session
                )
                fallback_phrases = [
                    "Xin lỗi, AI chatbot tạm thời gặp vấn đề kỹ thuật",
                    "Xin lỗi, AI đang gặp vấn đề"
                ]
                if any(fp in bot_response for fp in fallback_phrases):
                    if in_cooldown:
                        remaining = get_quota_cooldown_remaining()
                        response_mode = f"grop-quota-fallback-{remaining}s"
                        logger.info(f"⛔ Grop quota cooldown active ({remaining}s left) fallback used")
                    else:
                        response_mode = "grop-error-fallback"
                        logger.info("⚠️ Grop error fallback used")
                else:
                    response_mode = "grop"
                    logger.info(f"🤖 Grop AI responded to: {message[:50]}")
            except Exception as e:
                logger.error(f"❌ Grop unexpected error: {e}")
                bot_response = get_smart_response(message, session=request.session, user=request.user)
                response_mode = "rule-based-fallback"
        if bot_response is None:
            bot_response = get_smart_response(message, session=request.session, user=request.user)
            logger.info(f"📝 Rule-based response for: {message[:50]}")

        # Ghi vào ConversationMemory để các intent tiếp theo (như liên hệ) có thể tham chiếu lại post/link
        try:
            ConversationMemory.add_message(request.session, message, bot_response)
        except Exception as cm_err:
            logger.error(f"ConversationMemory error: {cm_err}")

        # Lưu tin nhắn vào database
        try:
            ChatMessage.objects.create(
                session_id=session_id,
                message=message,
                response=bot_response,
                is_user_message=True
            )

            ChatMessage.objects.create(
                session_id=session_id,
                message=bot_response,
                response="",
                is_user_message=False
            )
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")

        return JsonResponse({
            'response': bot_response,
            'session_id': session_id,
            'mode': response_mode  # 'grop', 'grop-quota-fallback-XXs', 'grop-error-fallback', 'rule-based'
        })

    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return JsonResponse({'error': f'Lỗi: {str(e)}'}, status=500)


def chatbot_widget(request):
    """View để hiển thị widget chatbot"""
    return render(request, 'chatbot/chatbot_widget.html')


@csrf_exempt
@require_http_methods(["GET"])
def get_chat_history(request):
    """Lấy lịch sử chat của session"""
    try:
        session_id = request.GET.get('session_id')
        if not session_id:
            return JsonResponse({'messages': []})

        messages = ChatMessage.objects.filter(session_id=session_id).order_by('timestamp')
        chat_data = []

        for msg in messages:
            chat_data.append({
                'message': msg.message,
                'is_user': msg.is_user_message,
                'timestamp': msg.timestamp.isoformat()
            })

        return JsonResponse({'messages': chat_data})
    except Exception as e:
        logger.error(f"Get chat history error: {e}")
        return JsonResponse({'messages': []})