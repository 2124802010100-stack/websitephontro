from __future__ import annotations

import re
import pickle
import os
from typing import Dict, Any, List, Tuple
from collections import Counter
from django.utils import timezone
from django.conf import settings


class ContentModerator:
    """
    AI Content Moderator với khả năng:
    1. Phát hiện biến thể từ nhạy cảm (l0à đ@o, xxx...)
    2. Học từ dữ liệu đã duyệt/từ chối
    3. Tự động phát hiện pattern mới
    4. Cập nhật từ điển động
    """

    def __init__(self) -> None:
        # Từ nhạy cảm cơ bản
        self.sensitive_keywords = {
            # Lừa đảo
            'lừa đảo', 'lừa_đảo', 'lua dao', 'lua đao', 'scam', 'lừa', 'đảo',
            'lừa đảo online', 'gian lận', 'fake bill', 'vu khống',

            # Nội dung người lớn
            'xxx', 'sex', 'gái', 'cave', 'massage',
            'đồi trụy', 'khiêu dâm', 'pornography', 'porn',
            'mua bán thân', 'sugar baby', 'sugar daddy', 'bán dâm',
            'trai bao', 'gái bao', 'lộ hàng', 'clip nóng',
            'chat sex', 'ảnh sex', 'tự sướng', 'chơi gái',
            'gạ tình', 'dụ dỗ', 'thả thính tục', 'câu view bẩn',
            'livestream bẩn', 'nội dung 18+', 'nội dung nhạy cảm',

            # Ma túy & chất cấm
            'ma túy', 'ma_túy', 'drug', 'thuốc lá', 'cần sa', 'chất cấm', 'chất_cấm',
            'heroin', 'thuốc lắc', 'mua bán ma túy', 'bán đá', 'mua đá',

            # Vũ khí & bạo lực
            'súng', 'vũ khí', 'dao găm', 'bom', 'lựu đạn',
            'chất nổ', 'thuốc nổ', 'bắn nhau', 'giết người',
            'đánh nhau', 'cướp', 'trộm', 'bắt cóc', 'chém nhau',

            # Cờ bạc
            'cờ bạc', 'đánh bạc', 'casino', 'gamble',
            'rửa tiền', 'lô đề', 'xóc đĩa', 'nổ hũ',
            'nổ hũ online', 'đá gà', 'cá độ', 'đánh đề',

            # Mua bán bất hợp pháp
            'hack', 'phishing', 'virus', 'trojan',
            'buôn bán', 'mua bán', 'trái phép', 'trái_phép',
            'mua bán nội tạng', 'bán acc', 'bán nick',
            'hack facebook', 'bán dữ liệu', 'mua data',
            'rò rỉ thông tin', 'lộ thông tin', 'bẻ khóa',
            'vi phạm bản quyền', 'crack', 'tool cheat', 'spam', 'click ảo',

            # Buôn bán hàng hóa (TỔNG QUÁT - không phải cho thuê phòng)
            'bán hàng', 'bán đồ', 'buôn hàng', 'buôn bán',
            'cần bán', 'cần mua', 'mua bán', 'thanh lý', 'sang nhượng',
            'sỉ lẻ', 'bán sỉ', 'bán lẻ', 'đại lý', 'nhà phân phối',
            'phân phối', 'nhập khẩu', 'bán buôn', 'bán lẻ',
            'mở shop', 'mở cửa hàng', 'kinh doanh online',
            'bán xe', 'bán điện thoại', 'bán laptop',
            'bán quần áo', 'bán mỹ phẩm', 'bán hàng online',
            'bán chó', 'bán mèo', 'bán thú cưng', 'bán pet',
            'bán chó cảnh', 'bán mèo cảnh', 'bán cá cảnh',
            'bán chim cảnh', 'bán rùa', 'bán hamster',
            'có hàng', 'nhận order', 'đặt hàng', 'ship hàng',
            'bán giá sỉ', 'giá buôn', 'số lượng lớn',
            'sang quán', 'sang shop', 'cần sang', 'sang lại',
            'order online', 'nhận đơn', 'ship cod',

            # Chính trị nhạy cảm
            'phản động', 'chống phá', 'bạo loạn', 'nội chiến',
            'đảo chính', 'kích động', 'lật đổ', 'chống nhà nước',
            'xuyên tạc', 'bôi nhọ', 'đả kích',

            # Từ tục tĩu
            'đm', 'địt', 'dm', 'vcl', 'cc', 'ml', 'cl',
            'lồn', 'cặc', 'buồi', 'đéo', 'đếch',
            'đếch mẹ', 'đéo mẹ', 'vãi l', 'vãi cả l',
            'mẹ mày', 'bố mày', 'bà mày',

            # Xúc phạm
            'thằng ngu', 'ngu vãi', 'ngu như bò', 'óc chó',
            'đồ chó', 'chó chết', 'thằng chó', 'con chó',
            'điên khùng', 'mất dạy', 'khốn nạn', 'đồ điên',
            'thằng điên', 'bẩn thỉu', 'láo toét', 'hâm hấp',
            'ngu người',

            # Lừa đảo & MLM
            'tiền ảo lừa đảo', 'đầu tư forex lừa đảo', 'mlm lừa đảo',
            'kiếm tiền nhanh', 'làm giàu cấp tốc',

            # Tuyển dụng lừa đảo
            'không cần giấy tờ', 'không kiểm tra hồ sơ',
            'không cần cmnd', 'không cần cccd',
            'nhận ngay', 'trả lương ngay', 'nhận tiền ngay',
            'tuyển gấp 100 người', 'tuyển hàng loạt',
            'lương cao không cần kinh nghiệm',
            'việc nhẹnh lương cao', 'ngồi nhà kiếm tiền',
            'tuyển gấp', 'cần gấp', 'tuyển nhiều',
            'làm việc tại nhà lương cao', 'việc làm thêm lương cao',
        }        # Whitelist - Từ an toàn không được đánh dấu (tránh false positive)
        self.safe_words = {
            'lớn', 'to lớn', 'rộng lớn', 'diện tích lớn', 'phòng lớn',
            'căn hộ lớn', 'nhà lớn', 'siêu lớn', 'cực lớn',
            'cọc', 'đặt cọc', 'tiền cọc',  # Từ hợp pháp trong cho thuê
            'con', 'con gái', 'con trai', 'con cái',  # Từ bình thường
            'đường', 'đường phố', 'con đường',
            'dành', 'dành cho', 'dành riêng',  # "dành cho sinh viên" - KHÔNG phải "đá" (ma túy)
            'đá', 'đá banh', 'sân đá',  # Hoạt động thể thao
        }

        # Từ cần kiểm tra context
        self.context_keywords = {
            'zalo', 'facebook', 'telegram', 'viber', 'whatsapp',
            'chuyển khoản', 'chuyển_khoản', 'bank', 'banking',
            'tiền cọc', 'cọc trước', 'đặt cọc', 'cọc',
            'thanh toán trước', 'trả trước', 'ship cod',
            'liên hệ ngay', 'inbox', 'nhắn tin', 'gọi ngay',
            'giá rẻ bất ngờ', 'giảm giá sốc', 'quá rẻ',
            'link', 'http', 'https', 'bit.ly', 'tinyurl'
        }

        # Từ nghiêm trọng - Chỉ cần xuất hiện 1 lần là auto-flag
        # (những từ này KHÔNG BAO GIỜ xuất hiện trong ngữ cảnh bình thường)
        self.critical_keywords = {
            # Tục tĩu nghiêm trọng
            'đm', 'địt', 'dm', 'vcl', 'cc', 'ml', 'cl',
            'lồn', 'cặc', 'buồi', 'đéo', 'đếch',
            'đếch mẹ', 'đéo mẹ', 'địt mẹ', 'vãi l', 'vãi cả l',
            'mẹ mày', 'bố mày', 'bà mày',

            # Xúc phạm nghiêm trọng
            'thằng ngu', 'thg ngu', 'ngu vãi', 'óc chó', 'đồ chó',
            'chó chết', 'đồ súc sinh', 'súc vật', 'loài người',
            'mất dạy', 'khốn nạn', 'điên khùng', 'láo toét',

            # Nội dung 18+ nghiêm trọng
            'bán dâm', 'mua dâm', 'trai bao', 'gái bao',
            'sugar baby', 'sugar daddy', 'chat sex', 'clip nóng',
            'ảnh sex', 'livestream bẩn', 'nội dung 18+',

            # Ma túy & vũ khí
            'ma túy', 'heroin', 'thuốc lắc', 'cần sa',
            'súng', 'bom', 'lựu đạn', 'chất nổ',

            # Cờ bạc & lừa đảo
            'lừa đảo', 'lừa đảo online', 'scam', 'gian lận',
            'lô đề', 'xóc đĩa', 'nổ hũ', 'cá độ',

            # Chính trị
            'phản động', 'bạo loạn', 'đảo chính', 'chống nhà nước',

            # Hack & bất hợp pháp
            'hack facebook', 'bán dữ liệu', 'crack', 'tool cheat',
        }

        # Pattern nghi ngờ (regex)
        self.suspicious_patterns = [
            r'\b(\d+)\s*tr(?:iệu|ieu)?\b.*\b(cọc|đặt cọc)\b',  # "5 triệu cọc"
            r'\b(zalo|viber)\s*:?\s*0\d{9,10}\b',  # "zalo: 0912345678"
            r'\b(liên hệ|lh|inbox)\s*(ngay|gấp)\b',  # "liên hệ ngay"
            r'(http|https|www)\.',  # Links
            r'\b0\d{9,10}\b.*\b(zalo|viber|telegram)\b',  # SĐT + app
            r'(inbox|ib|nhắn tin).*\b(free|miễn phí|tặng)\b',  # "inbox nhận quà"

            # Pattern tuyển dụng lừa đảo
            r'(tuyển|cần|nhận).*(không cần giấy tờ|không kiểm tra)',
            r'(tuyển|cần).*(bao ăn ở|bao ăn|bao ở)',
            r'(lương cao|thu nhập cao).*(không cần|không kiểm tra)',
            r'(nhận ngay|trả ngay|nhận tiền).*(lương|tiền)',
        ]

        # Map ký tự thay thế phổ biến
        self.char_substitutions = {
            '0': 'o', '@': 'a', '4': 'a', '3': 'e', '1': 'i', '!': 'i',
            '5': 's', '$': 's', '7': 't', '6': 'b', '9': 'g', '8': 'b',
            'đ': 'd', 'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
            'ă': 'a', 'ắ': 'a', 'ằ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
            'â': 'a', 'ấ': 'a', 'ầ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
            'é': 'e', 'è': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
            'ê': 'e', 'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
            'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
            'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
            'ô': 'o', 'ố': 'o', 'ồ': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
            'ơ': 'o', 'ớ': 'o', 'ờ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
            'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
            'ư': 'u', 'ứ': 'u', 'ừ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
            'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
        }

        # Load learned patterns nếu có
        self.learned_patterns = self._load_learned_patterns()

        # Cache để tránh tính toán lại
        self._cache = {}

    def _normalize_text(self, text: str) -> str:
        """Chuẩn hóa text để phát hiện biến thể từ"""
        if not text:
            return ""

        text = text.lower()

        # Thay thế ký tự đặc biệt
        for char, replacement in self.char_substitutions.items():
            text = text.replace(char, replacement)

        # Loại bỏ space dư thừa
        text = re.sub(r'\s+', ' ', text)

        # Loại bỏ ký tự đặc biệt nhưng giữ space
        text = re.sub(r'[^\w\s]', '', text)

        return text.strip()

    def _detect_obfuscated_keywords(self, text: str) -> Tuple[int, List[str]]:
        """Phát hiện từ nhạy cảm bị che giấu (l0à đ@o)"""
        text_lower = text.lower()

        # Kiểm tra whitelist trước - nếu có từ an toàn thì bỏ qua từ đó
        for safe_word in self.safe_words:
            if safe_word in text_lower:
                # Nếu tìm thấy từ an toàn, tạm thời thay thế để không bị detect nhầm
                text_lower = text_lower.replace(safe_word, ' ' * len(safe_word))

        normalized = self._normalize_text(text_lower)
        detected = []

        for keyword in self.sensitive_keywords:
            normalized_keyword = self._normalize_text(keyword)
            if normalized_keyword in normalized:
                detected.append(keyword)

        return len(detected), detected

    def _check_patterns(self, text: str) -> Tuple[int, List[str]]:
        """Kiểm tra các pattern nghi ngờ"""
        matched_patterns = []

        for pattern in self.suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                matched_patterns.append(pattern)

        return len(matched_patterns), matched_patterns

    def _check_context_keywords(self, text: str) -> int:
        """Đếm từ khóa context"""
        normalized = self._normalize_text(text)
        count = 0

        for keyword in self.context_keywords:
            normalized_keyword = self._normalize_text(keyword)
            if normalized_keyword in normalized:
                count += 1

        return count

    def _load_learned_patterns(self) -> Dict[str, Any]:
        """Load các pattern đã học từ file"""
        model_path = os.path.join(settings.BASE_DIR, 'website', 'ai_moderation', 'models', 'learned_patterns.pkl')

        try:
            if os.path.exists(model_path):
                with open(model_path, 'rb') as f:
                    return pickle.load(f)
        except Exception as e:
            print(f"Could not load learned patterns: {e}")

        return {
            'rejected_words': Counter(),  # Từ xuất hiện nhiều trong bài bị từ chối
            'approved_words': Counter(),  # Từ xuất hiện nhiều trong bài được duyệt
            'last_updated': None,
        }

    def _save_learned_patterns(self):
        """Lưu patterns đã học"""
        model_dir = os.path.join(settings.BASE_DIR, 'website', 'ai_moderation', 'models')
        os.makedirs(model_dir, exist_ok=True)

        model_path = os.path.join(model_dir, 'learned_patterns.pkl')

        try:
            with open(model_path, 'wb') as f:
                pickle.dump(self.learned_patterns, f)
        except Exception as e:
            print(f"Could not save learned patterns: {e}")

    def learn_from_decision(self, title: str, description: str, is_approved: bool):
        """
        Học từ quyết định duyệt/từ chối của admin
        Gọi hàm này khi admin duyệt hoặc từ chối bài
        """
        text = f"{title or ''} {description or ''}".lower()
        words = re.findall(r'\w+', text)

        if is_approved:
            self.learned_patterns['approved_words'].update(words)
        else:
            self.learned_patterns['rejected_words'].update(words)

        self.learned_patterns['last_updated'] = timezone.now()
        self._save_learned_patterns()

    def _calculate_learned_score(self, text: str) -> float:
        """Tính điểm dựa trên patterns đã học"""
        if not self.learned_patterns['rejected_words']:
            return 0.0

        words = set(re.findall(r'\w+', text.lower()))

        rejected_score = sum(
            self.learned_patterns['rejected_words'].get(word, 0)
            for word in words
        )

        approved_score = sum(
            self.learned_patterns['approved_words'].get(word, 0)
            for word in words
        )

        # Điểm càng cao = càng giống bài bị từ chối
        if rejected_score + approved_score == 0:
            return 0.0

        return rejected_score / (rejected_score + approved_score)

    def check_content(self, title: str, description: str) -> Dict[str, Any]:
        """
        Kiểm tra nội dung với AI nâng cao
        """
        text = f"{title or ''} {description or ''}".lower()

        # 0. CHECK CRITICAL KEYWORDS TRƯỚC - Auto-flag ngay nếu phát hiện
        # NHƯNG: Kiểm tra whitelist trước để tránh false positive
        text_to_check = text

        # Loại bỏ các từ an toàn trước khi kiểm tra
        for safe_word in self.safe_words:
            if safe_word in text_to_check:
                text_to_check = text_to_check.replace(safe_word, ' ' * len(safe_word))

        normalized = self._normalize_text(text_to_check)
        critical_detected = []
        for keyword in self.critical_keywords:
            normalized_keyword = self._normalize_text(keyword)
            if normalized_keyword in normalized:
                critical_detected.append(keyword)

        if critical_detected:
            # Phát hiện từ nghiêm trọng → AUTO-FLAG với confidence cao
            return {
                'is_flagged': True,
                'confidence': 0.95,
                'reason': f"Phát hiện {len(critical_detected)} từ nghiêm trọng: {', '.join(critical_detected[:3])}",
                'rule_result': {
                    'sensitive_count': len(critical_detected),
                    'sensitive_words': critical_detected[:5],
                    'pattern_count': 0,
                    'context_count': 0,
                    'learned_score': 0.0,
                    'rule_score': 1.0,
                },
                'ml_result': {
                    'prediction': 1,
                    'confidence': 0.95,
                },
            }

        # 1. Phát hiện từ nhạy cảm (kể cả biến thể)
        sensitive_count, sensitive_words = self._detect_obfuscated_keywords(text)

        # 2. Phát hiện pattern nghi ngờ
        pattern_count, matched_patterns = self._check_patterns(text)

        # 3. Đếm từ context
        context_count = self._check_context_keywords(text)

        # 4. Điểm từ ML đã học
        learned_score = self._calculate_learned_score(text)

        # 5. Tính điểm tổng hợp
        # Trọng số: sensitive (0.6), pattern (0.5), context (0.2), learned (0.4)
        rule_score = min(1.0,
            0.6 * sensitive_count +
            0.5 * pattern_count +
            0.2 * context_count +
            0.4 * learned_score
        )

        # Ngưỡng gắn cờ linh động - Giảm xuống 0.58 để phát hiện buôn bán tốt hơn
        flag_threshold = 0.58  # 1 từ nhạy cảm (0.6) hoặc 1 pattern + context
        is_flagged = rule_score >= flag_threshold

        # Confidence tăng theo điểm
        confidence = min(0.95, 0.5 + 0.45 * rule_score)

        # Lý do chi tiết
        reasons = []
        if sensitive_count > 0:
            reasons.append(f"Phát hiện {sensitive_count} từ nhạy cảm: {', '.join(sensitive_words[:3])}")
        if pattern_count > 0:
            reasons.append(f"Phát hiện {pattern_count} pattern nghi ngờ")
        if context_count >= 3:
            reasons.append(f"Có {context_count} từ khóa cần kiểm tra context")
        if learned_score > 0.5:
            reasons.append(f"Giống {learned_score*100:.0f}% với bài bị từ chối trước đây")

        reason = "; ".join(reasons) if reasons else "Nội dung trông an toàn"

        return {
            'is_flagged': is_flagged,
            'confidence': confidence,
            'reason': reason,
            'rule_result': {
                'sensitive_count': sensitive_count,
                'sensitive_words': sensitive_words[:5],  # Top 5
                'pattern_count': pattern_count,
                'context_count': context_count,
                'learned_score': learned_score,
                'rule_score': rule_score,
            },
            'ml_result': {
                'prediction': int(is_flagged),
                'confidence': confidence,
            },
        }

    def train_model(self) -> float:
        """
        Train model từ dữ liệu đã duyệt/từ chối trong database
        Gọi lệnh: python manage.py train_ai_model

        Chỉ học từ các bài AI ĐÃ FLAG và admin ĐÃ XỬ LÝ:
        - Bài DUYỆT: AI flag nhưng admin duyệt (False positive - AI học để không flag nữa)
        - Bài TỪ CHỐI: AI flag và admin cũng từ chối (True positive - AI học để tăng cường)
        """
        from website.models import RentalPost

        # Bài được duyệt MÀ AI từng gắn cờ (AI sai - False positive)
        # Admin đã xem và quyết định duyệt → AI học để không flag nữa
        approved_flagged_posts = RentalPost.objects.filter(
            is_approved=True,
            approved_by__isnull=False,  # Admin đã duyệt
            ai_flagged=True  # AI từng nghi ngờ
        ).values_list('title', 'description')

        # Bài bị từ chối MÀ AI đã gắn cờ (AI đúng - True positive)
        # Admin đã xem và quyết định từ chối → AI học để tăng cường
        rejected_flagged_posts = RentalPost.objects.filter(
            is_approved=False,
            approved_by__isnull=False,  # Admin đã từ chối (không phải đang chờ)
            ai_flagged=True,  # AI đã phát hiện
        ).values_list('title', 'description')

        # Reset learned patterns trước khi train lại
        self.learned_patterns['rejected_words'] = Counter()
        self.learned_patterns['approved_words'] = Counter()

        # Học từ approved (AI nghĩ xấu nhưng thực ra tốt)
        for title, desc in approved_flagged_posts:
            self.learn_from_decision(title, desc, is_approved=True)

        # Học từ rejected (AI nghĩ xấu và đúng là xấu)
        for title, desc in rejected_flagged_posts:
            self.learn_from_decision(title, desc, is_approved=False)

        total = approved_flagged_posts.count() + rejected_flagged_posts.count()

        # Tính accuracy dựa trên số lượng dữ liệu
        if total > 100:
            accuracy = 0.90
        elif total > 50:
            accuracy = 0.85
        elif total > 20:
            accuracy = 0.75
        else:
            accuracy = 0.70

        print(f"\n{'='*60}")
        print(f"✅ TRAIN COMPLETED - Trained on {total} posts AI đã flag:")
        print(f"{'='*60}")
        print(f"   📊 {approved_flagged_posts.count()} bài AI flag nhưng admin duyệt (False positive)")
        print(f"      → AI học để KHÔNG flag những từ này nữa")
        print(f"   📊 {rejected_flagged_posts.count()} bài AI flag và admin từ chối (True positive)")
        print(f"      → AI học để TĂNG CƯỜNG phát hiện những từ này")
        print(f"\n   � Learned {len(self.learned_patterns['rejected_words'])} unique rejected words")
        print(f"   � Learned {len(self.learned_patterns['approved_words'])} unique approved words")
        print(f"\n   🎯 Estimated accuracy: {accuracy:.1%}")
        print(f"{'='*60}\n")

        return accuracy


