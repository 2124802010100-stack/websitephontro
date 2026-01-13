import re
import string
from typing import List

class TextPreprocessor:
    """Tiền xử lý văn bản tiếng Việt"""
    
    def __init__(self):
        # Stopwords tiếng Việt cơ bản
        self.stopwords = {
            'và', 'của', 'với', 'từ', 'trong', 'cho', 'để', 'có', 'là', 'được',
            'một', 'các', 'những', 'này', 'đó', 'nào', 'gì', 'sao', 'thế',
            'rất', 'quá', 'cũng', 'đều', 'đã', 'sẽ', 'đang', 'vẫn', 'còn',
            'phòng', 'trọ', 'nhà', 'căn', 'hộ', 'thuê', 'cho', 'bán', 'mua'
        }
        
        # Pattern để tách từ tiếng Việt (đơn giản)
        self.word_pattern = re.compile(r'\b\w+\b', re.UNICODE)
    
    def clean_text(self, text: str) -> str:
        """Làm sạch văn bản"""
        if not text:
            return ""
        
        # Chuyển về lowercase
        text = text.lower()
        
        # Loại bỏ ký tự đặc biệt, giữ lại chữ cái và số
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Loại bỏ khoảng trắng thừa
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def tokenize(self, text: str) -> List[str]:
        """Tách từ đơn giản"""
        cleaned = self.clean_text(text)
        tokens = self.word_pattern.findall(cleaned)
        return tokens
    
    def remove_stopwords(self, tokens: List[str]) -> List[str]:
        """Loại bỏ stopwords"""
        return [token for token in tokens if token not in self.stopwords]
    
    def preprocess(self, text: str) -> str:
        """Tiền xử lý hoàn chỉnh"""
        tokens = self.tokenize(text)
        filtered_tokens = self.remove_stopwords(tokens)
        return ' '.join(filtered_tokens)
    
    def extract_features(self, text: str) -> dict:
        """Trích xuất features cơ bản"""
        cleaned = self.clean_text(text)
        tokens = self.tokenize(cleaned)
        
        return {
            'length': len(text),
            'word_count': len(tokens),
            'char_count': len(cleaned),
            'has_numbers': bool(re.search(r'\d', text)),
            'has_special_chars': bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', text)),
            'has_uppercase': bool(re.search(r'[A-Z]', text)),
            'exclamation_count': text.count('!'),
            'question_count': text.count('?'),
        }

