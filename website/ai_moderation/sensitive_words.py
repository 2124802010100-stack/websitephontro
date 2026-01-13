# Từ điển từ nhạy cảm tiếng Việt
SENSITIVE_WORDS = {
    # Từ ngữ không phù hợp
    'fuck', 'shit', 'damn', 'bitch', 'asshole',
    'địt', 'đụ', 'đéo', 'đĩ', 'cặc', 'lồn', 'đụ má', 'địt mẹ',
    'chết tiệt', 'khốn nạn', 'đồ chó', 'đồ súc vật',
    
    # Từ ngữ liên quan đến mại dâm
    'gái gọi', 'massage', 'kích dục', 'sex', 'tình dục',
    'gái làng chơi', 'gái điếm', 'mại dâm', 'prostitute',
    
    # Từ ngữ liên quan đến ma túy
    'ma túy', 'heroin', 'cocaine', 'marijuana', 'cần sa',
    'thuốc lắc', 'ecstasy', 'amphetamine', 'drug',
    
    # Từ ngữ liên quan đến bạo lực
    'giết người', 'đánh nhau', 'bạo lực', 'hành hung',
    'đâm chém', 'súng', 'dao', 'vũ khí',
    
    # Từ ngữ lừa đảo
    'lừa đảo', 'lừa gạt', 'scam', 'fraud', 'gian lận',
    'tiền ảo', 'đa cấp', 'ponzi', 'bitcoin lừa đảo',
    
    # Từ ngữ phân biệt đối xử
    'đồng tính', 'gay', 'lesbian', 'bê đê', 'pê đê',
    'da đen', 'da trắng', 'phụ nữ', 'đàn ông',
    
    # Từ ngữ chính trị nhạy cảm
    'chính trị', 'đảng phái', 'cách mạng', 'biểu tình',
    'chống đối', 'phản động', 'tư tưởng',
}

# Từ ngữ có thể gây hiểu lầm (cần context)
CONTEXT_SENSITIVE = {
    'phòng kín', 'riêng tư', 'một mình', 'đêm khuya',
    'giá rẻ', 'không cần giấy tờ', 'bí mật',
    'nhanh chóng', 'dễ dàng', 'không kiểm tra',
}

# Từ ngữ tích cực (giảm điểm nhạy cảm)
POSITIVE_WORDS = {
    'chính chủ', 'uy tín', 'đáng tin cậy', 'minh bạch',
    'hợp pháp', 'chính thức', 'có giấy tờ', 'đầy đủ',
    'an toàn', 'sạch sẽ', 'thoáng mát', 'tiện nghi',
}

def get_sensitive_words():
    """Trả về danh sách từ nhạy cảm"""
    return SENSITIVE_WORDS

def get_context_sensitive_words():
    """Trả về danh sách từ cần xem xét context"""
    return CONTEXT_SENSITIVE

def get_positive_words():
    """Trả về danh sách từ tích cực"""
    return POSITIVE_WORDS

