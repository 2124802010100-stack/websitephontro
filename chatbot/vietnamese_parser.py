"""
Vietnamese Text Parser
Parse Vietnamese number words to numeric values
"""

import re
from typing import Optional, Dict, List, Tuple
from django.utils import timezone


class VietnameseNumberParser:
    """Parse Vietnamese number words like 'năm triệu', 'ba trăm nghìn' to numbers"""

    # Vietnamese digit words
    DIGITS = {
        'không': 0, 'zero': 0,
        'một': 1, 'mốt': 1, 'môt': 1,
        'hai': 2,
        'ba': 3,
        'bốn': 4, 'bon': 4, 'tư': 4,
        'năm': 5, 'lăm': 5,
        'sáu': 6,
        'bảy': 7, 'bay': 7,
        'tám': 8,
        'chín': 9,
        'mười': 10, 'mươi': 10,
        'chục': 10,
    }

    # Vietnamese multipliers
    MULTIPLIERS = {
        'nghìn': 1_000,
        'ngàn': 1_000,
        'vạn': 10_000,
        'triệu': 1_000_000,
        'trieu': 1_000_000,
        'tỷ': 1_000_000_000,
        'ty': 1_000_000_000,
    }

    # Common compound patterns
    COMPOUND_PATTERNS = [
        # "hai triệu năm" = 2,500,000
        (r'(\w+)\s+triệu\s+(\w+)(?:\s+(?:nghìn|ngàn))?', lambda m: (
            VietnameseNumberParser.DIGITS.get(m.group(1), 0) * 1_000_000 +
            VietnameseNumberParser.DIGITS.get(m.group(2), 0) * 100_000
        )),
        # "ba trăm nghìn" = 300,000
        (r'(\w+)\s+trăm\s+(?:nghìn|ngàn)', lambda m: (
            VietnameseNumberParser.DIGITS.get(m.group(1), 0) * 100_000
        )),
        # "hai mươi nghìn" = 20,000
        (r'(\w+)\s+(?:mươi|mười)\s+(?:nghìn|ngàn)', lambda m: (
            VietnameseNumberParser.DIGITS.get(m.group(1), 0) * 10_000
        )),
        # "năm triệu" = 5,000,000
        (r'(\w+)\s+(triệu|trieu|tỷ|ty|nghìn|ngàn|vạn)', lambda m: (
            VietnameseNumberParser.DIGITS.get(m.group(1), 0) *
            VietnameseNumberParser.MULTIPLIERS.get(m.group(2), 1)
        )),
    ]

    @classmethod
    def parse_price(cls, text: str) -> Optional[int]:
        """
        Parse price from Vietnamese text

        Examples:
            "năm triệu" -> 5000000
            "ba triệu năm" -> 3500000
            "hai trăm nghìn" -> 200000
            "5 triệu" -> 5000000
            "3tr5" -> 3500000

        Returns:
            int: Price in VND, or None if not found
        """
        text_lower = text.lower()

        # Try numeric patterns first (more common)
        numeric_result = cls._parse_numeric_price(text_lower)
        if numeric_result:
            return numeric_result

        # Try compound patterns (Vietnamese words)
        for pattern, calculator in cls.COMPOUND_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    return calculator(match)
                except:
                    continue

        return None

    @classmethod
    def _parse_numeric_price(cls, text: str) -> Optional[int]:
        """Parse numeric price patterns like '5 triệu', '3tr5', '500k'"""

        # Pattern: "3tr5" (3.5 triệu) - handle before "3 triệu"
        match = re.search(r'(\d+)tr(\d+)', text)
        if match:
            value = float(f"{match.group(1)}.{match.group(2)}")
            return int(value * 1_000_000)

        # Pattern: "5 triệu" or "5triệu"
        match = re.search(r'(\d+(?:\.\d+)?)\s*(?:triệu|trieu|tr)', text)
        if match:
            value = float(match.group(1))
            return int(value * 1_000_000)

        # Pattern: "500k5" (500,500)
        match = re.search(r'(\d+)k(\d+)', text)
        if match:
            value = float(f"{match.group(1)}.{match.group(2)}")
            return int(value * 1_000)

        # Pattern: "500 nghìn" or "500k"
        match = re.search(r'(\d+(?:\.\d+)?)\s*(?:nghìn|ngàn|k)', text)
        if match:
            value = float(match.group(1))
            return int(value * 1_000)

        return None

    @classmethod
    def parse_area(cls, text: str) -> Optional[int]:
        """
        Parse area from Vietnamese text

        Examples:
            "ba mươi mét" -> 30
            "30m2" -> 30
            "25 mét vuông" -> 25

        Returns:
            int: Area in m2, or None if not found
        """
        text_lower = text.lower()

        # Pattern: "30 m2" or "30m2" or "30 mét"
        match = re.search(r'(\d+(?:\.\d+)?)\s*(?:m2|m²|mét|met)', text_lower)
        if match:
            return int(float(match.group(1)))

        # Pattern: "ba mươi mét"
        match = re.search(r'(\w+)\s+(?:mươi|mười)\s+(?:mét|met)', text_lower)
        if match:
            digit = cls.DIGITS.get(match.group(1), 0)
            return digit * 10

        return None

    @classmethod
    def extract_price_range(cls, text: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Extract price range from text

        Examples:
            "từ 3 triệu đến 5 triệu" -> (3000000, 5000000)
            "dưới 2 triệu" -> (None, 2000000)
            "trên 4 triệu" -> (4000000, None)

        Returns:
            (min_price, max_price) tuple, either can be None
        """
        text_lower = text.lower()

        # Pattern: "từ X đến Y" - need to extract X and Y parts carefully
        # Look for number + unit before "đến"
        match = re.search(r'từ\s+(\d+(?:\.\d+)?)\s*(triệu|trieu|tr|nghìn|ngàn|k)?\s+đến\s+(\d+(?:\.\d+)?)\s*(triệu|trieu|tr|nghìn|ngàn|k)?', text_lower)
        if match:
            min_val = float(match.group(1))
            min_unit = match.group(2) or 'triệu'  # Default to triệu
            max_val = float(match.group(3))
            max_unit = match.group(4) or min_unit  # Use same unit as min if not specified

            # Convert to VND
            min_multiplier = 1_000_000 if any(u in min_unit for u in ['triệu', 'trieu', 'tr']) else 1_000
            max_multiplier = 1_000_000 if any(u in max_unit for u in ['triệu', 'trieu', 'tr']) else 1_000

            return (int(min_val * min_multiplier), int(max_val * max_multiplier))

        # Pattern: "trên X" or "trên X triệu" - should return (X, None)
        match = re.search(r'(?:trên|tren|lớn hơn|lon hon|>)\s+(\d+(?:\.\d+)?)\s*(triệu|trieu|tr|nghìn|ngàn|k)?', text_lower)
        if match:
            val = float(match.group(1))
            unit = match.group(2) or 'triệu'
            multiplier = 1_000_000 if any(u in unit for u in ['triệu', 'trieu', 'tr']) else 1_000
            return (int(val * multiplier), None)

        # Pattern: "dưới X" or "dưới X triệu"
        match = re.search(r'(?:dưới|duoi|nhỏ hơn|nho hon|<)\s+(\d+(?:\.\d+)?)\s*(triệu|trieu|tr|nghìn|ngàn|k)?', text_lower)
        if match:
            val = float(match.group(1))
            unit = match.group(2) or 'triệu'
            multiplier = 1_000_000 if any(u in unit for u in ['triệu', 'trieu', 'tr']) else 1_000
            return (None, int(val * multiplier))

        # Single price mentioned - treat as max
        single_price = cls.parse_price(text_lower)
        if single_price:
            return (None, single_price)

        return (None, None)


class ConversationMemory:
    """Store conversation context in session"""

    MAX_HISTORY = 5  # Keep last 5 exchanges

    @classmethod
    def add_message(cls, session, user_message: str, bot_response: str, metadata: Dict = None):
        """
        Add exchange to conversation history

        Args:
            session: Django session
            user_message: User's message
            bot_response: Bot's response
            metadata: Optional dict with extra info like {'post_id': 123, 'post_title': '...'}
        """
        if 'chat_history' not in session:
            session['chat_history'] = []

        exchange = {
            'user': user_message,
            'bot': bot_response,
            'timestamp': timezone.now().isoformat()
        }

        # Add metadata if provided
        if metadata:
            exchange['metadata'] = metadata

        session['chat_history'].append(exchange)

        # Keep only last N exchanges
        if len(session['chat_history']) > cls.MAX_HISTORY:
            session['chat_history'] = session['chat_history'][-cls.MAX_HISTORY:]

        session.modified = True

    @classmethod
    def get_history(cls, session) -> List[Dict]:
        """Get conversation history"""
        return session.get('chat_history', [])

    @classmethod
    def get_context_string(cls, session) -> str:
        """Get conversation history as formatted string"""
        history = cls.get_history(session)
        if not history:
            return ""

        context_parts = ["LỊCH SỬ HỘI THOẠI GÀN ĐÂY:"]
        for i, exchange in enumerate(history[-3:], 1):  # Last 3 exchanges
            context_parts.append(f"\nLần {i}:")
            context_parts.append(f"Người dùng: {exchange['user']}")
            context_parts.append(f"Bot: {exchange['bot'][:200]}...")  # Truncate long responses

        return "\n".join(context_parts)

    @classmethod
    def clear_history(cls, session):
        """Clear conversation history"""
        if 'chat_history' in session:
            del session['chat_history']
            session.modified = True

    @classmethod
    def extract_context(cls, session) -> Dict:
        """
        Extract useful context from conversation history

        Returns:
            {
                'mentioned_province': str or None,
                'mentioned_price_range': (min, max) or None,
                'mentioned_categories': List[str],
                'mentioned_features': List[str],
                'last_post_id': int or None,
                'last_post_title': str or None,
            }
        """
        from .views import find_province_in_text

        history = cls.get_history(session)
        if not history:
            return {}

        context = {
            'mentioned_province': None,
            'mentioned_price_range': (None, None),
            'mentioned_categories': [],
            'mentioned_features': [],
            'last_post_id': None,
            'last_post_title': None,
        }

        # Analyze last 3 messages for context
        recent_messages = [h['user'] for h in history[-3:]]
        combined_text = ' '.join(recent_messages)

        # Extract province
        province = find_province_in_text(combined_text)
        if province:
            context['mentioned_province'] = province

        # Extract price range
        price_range = VietnameseNumberParser.extract_price_range(combined_text)
        if price_range[0] or price_range[1]:
            context['mentioned_price_range'] = price_range

        # Extract last mentioned post from metadata
        for exchange in reversed(history):
            metadata = exchange.get('metadata', {})
            if metadata.get('post_id'):
                context['last_post_id'] = metadata['post_id']
                context['last_post_title'] = metadata.get('post_title')
                break

        return context


class TypoTolerance:
    """Fuzzy matching for common typos in province names"""

    # Common typos for province names
    PROVINCE_TYPOS = {
        'hcm': 'Thành phố Hồ Chí Minh',
        'tphcm': 'Thành phố Hồ Chí Minh',
        'tp hcm': 'Thành phố Hồ Chí Minh',
        'tp.hcm': 'Thành phố Hồ Chí Minh',
        'sai gon': 'Thành phố Hồ Chí Minh',
        'sài gòn': 'Thành phố Hồ Chí Minh',
        'saigon': 'Thành phố Hồ Chí Minh',
        'ho chi minh': 'Thành phố Hồ Chí Minh',
        'hồ chí minh': 'Thành phố Hồ Chí Minh',

        'ha noi': 'Hà Nội',
        'hà nội': 'Hà Nội',
        'hanoi': 'Hà Nội',

        'da nang': 'Đà Nẵng',
        'đà nẵng': 'Đà Nẵng',
        'danang': 'Đà Nẵng',

        'binh duong': 'Bình Dương',
        'bình dương': 'Bình Dương',
        'binhduong': 'Bình Dương',

        'dong nai': 'Đồng Nai',
        'đồng nai': 'Đồng Nai',
        'dongnai': 'Đồng Nai',
    }

    @classmethod
    def normalize_province(cls, text: str) -> Optional[str]:
        """
        Normalize province name from text with typo tolerance

        Returns:
            Official province name or None
        """
        text_lower = text.lower().strip()

        # Direct match
        if text_lower in cls.PROVINCE_TYPOS:
            return cls.PROVINCE_TYPOS[text_lower]

        # Fuzzy match - check if any typo pattern is in text
        for typo, official in cls.PROVINCE_TYPOS.items():
            if typo in text_lower:
                return official

        return None
