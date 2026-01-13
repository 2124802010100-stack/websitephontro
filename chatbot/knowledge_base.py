"""
Knowledge Base - Kiến thức về website PhongTro
Chatbot sẽ dùng thông tin này để trả lời câu hỏi về tính năng, hướng dẫn
"""

WEBSITE_KNOWLEDGE = """
# TRANG WEB CHO THUÊ PHÒNG TRỌ PHONGTRO

## 1. TÍNH NĂNG CHÍNH

### Tìm kiếm phòng trọ:
- Tìm theo tỉnh/thành phố (Hà Nội, TP.HCM, Đà Nẵng, Cần Thơ, v.v.)
- Lọc theo giá (triệu VNĐ/tháng)
- Lọc theo diện tích (m²)
- Lọc theo loại phòng: Phòng trọ, Chung cư mini, Nhà nguyên căn, Căn hộ dịch vụ

### Gợi ý AI thông minh:
- Hệ thống AI gợi ý phòng dựa trên lịch sử tìm kiếm
- Dữ liệu 24 giờ gần nhất để gợi ý mới nhất
- Cá nhân hóa theo sở thích người dùng
- Guest (khách) cũng nhận được gợi ý dựa trên session

### Đăng tin cho thuê (có gói VIP trả phí):
- Upload ảnh (tối đa 10 ảnh) và video giới thiệu phòng
- Thông tin chi tiết: địa chỉ, giá, diện tích, tiện ích
- AI kiểm duyệt nội dung tự động (chống từ nhạy cảm)

### Bảng giá gói VIP:
- (Được lấy động từ database khi người dùng hỏi; luôn hiển thị dữ liệu mới nhất.)

### Chatbot hỗ trợ:
- Trả lời câu hỏi 24/7
- Tìm phòng theo yêu cầu tự nhiên (VD: "Tìm phòng Hà Nội giá 2 triệu")
- Hiểu tiếng Việt lóng, thân mật

### Quản lý yêu cầu thuê:
- Người thuê gửi yêu cầu thuê phòng
- Chủ nhà xem và chấp nhận/từ chối
- Theo dõi trạng thái: pending, approved, rejected, cancelled
- Người thuê có thể hủy yêu cầu

### Đánh giá & Review:
- Đánh giá chủ nhà/người thuê
- Hệ thống sao 1-5
- Comment và phản hồi

## 2. LOẠI PHÒNG TRỌ

1. **Phòng trọ**: Phòng đơn giản, giá rẻ, sinh viên/người đi làm
2. **Chung cư mini**: Cao cấp hơn, có thang máy, đầy đủ tiện nghi
3. **Nhà nguyên căn**: Cho thuê cả nhà, gia đình/nhóm bạn
4. **Căn hộ dịch vụ**: Đầy đủ tiện nghi, dọn phòng định kỳ

## 3. GIÁ PHÒNG

- Từ 500,000 VNĐ - 15,000,000 VNĐ/tháng
- Phổ biến: 1-3 triệu cho phòng trọ
- Chung cư mini: 3-7 triệu
- Căn hộ dịch vụ: 5-15 triệu

## 4. KHU VỰC PHỦ SÓNG

Các tỉnh/thành phố lớn:
- Hà Nội
- TP. Hồ Chí Minh
- Đà Nẵng
- Cần Thơ
- Hải Phòng
- Nha Trang
- ... và nhiều tỉnh thành khác

## 5. HƯỚNG DẪN SỬ DỤNG

### Tìm phòng:
1. Vào trang chủ
2. Chọn tỉnh/thành phố
3. Điều chỉnh bộ lọc: giá, diện tích, loại phòng
4. Xem danh sách phòng
5. Click vào phòng để xem chi tiết
6. Gửi yêu cầu thuê hoặc liên hệ chủ nhà

### Đăng tin:
1. Đăng nhập tài khoản
2. Vào "Đăng tin mới"
3. Điền đầy đủ thông tin
4. Upload ảnh/video
5. Submit → AI kiểm duyệt tự động
6. Tin đăng sau khi duyệt

### Chat với AI:
- Gõ câu hỏi tự nhiên như nói chuyện bình thường
- VD: "Tìm phòng Hà Nội giá mềm", "Có phòng nào gần ĐH Bách Khoa không?"
- AI sẽ hiểu và tìm phòng phù hợp

## 6. TIỆN ÍCH

- Wifi miễn phí
- Điều hòa
- Nóng lạnh
- Giường, tủ
- Bếp riêng
- WC riêng
- Gửi xe miễn phí
- An ninh 24/7

## 7. QUY ĐỊNH

- Không nuôi thú cưng (một số phòng cho phép)
- Không hút thuốc trong phòng
- Giờ giấc hợp lý
- Giữ vệ sinh chung
- Đóng tiền đúng hạn

## 8. THANH TOÁN

- Tiền cọc: 1-2 tháng
- Thanh toán: Đầu tháng/cuối tháng
- Phương thức: Tiền mặt, chuyển khoản

## 9. HỖ TRỢ

- Chatbot AI 24/7
- Email: support@phongtroNMA.vn
- Hotline: (chưa có)

## 10. ƯU ĐIỂM CỦA WEBSITE

✅ AI gợi ý thông minh - cá nhân hóa
✅ Giao diện đẹp, dễ dùng
✅ Tìm kiếm nhanh, chính xác
✅ Chatbot hỗ trợ 24/7
✅ Kiểm duyệt AI - an toàn
✅ Gói VIP đa dạng, dễ nâng hạng hiển thị
✅ Cập nhật liên tục
"""

# FAQ - Câu hỏi thường gặp
FAQ = {
    "đăng tin": "Đăng nhập → Click 'Đăng tin mới' → Điền thông tin → Upload ảnh → Submit. AI sẽ kiểm duyệt tự động!",
    "giá": "Giá phòng từ 500,000 - 15,000,000 VNĐ/tháng. Phòng trọ thường 1-3 triệu, chung cư mini 3-7 triệu.",
    # Pricing-related entries now point to dynamic DB source instead of hard-code
    "phí": "Gói VIP có tính phí. Chatbot sẽ lấy bảng giá mới nhất trực tiếp từ database (VIP1, VIP2, VIP3).",
    "mất phí": "Có. Khi hỏi 'bảng giá vip' hoặc 'nâng cấp tài khoản' chatbot sẽ truy vấn database để trả lời giá, thời hạn, số tin/ngày.",
    "vip": "Gõ 'bảng giá vip' để nhận thông tin mới nhất từ database (không dùng file tĩnh).",
    "bảng giá": "Bảng giá VIP được lấy động từ database để luôn chính xác. Hỏi: 'bảng giá vip' hoặc 'giá gói vip'.",
    "tìm phòng": "Vào trang chủ → Chọn tỉnh/thành → Điều chỉnh bộ lọc (giá, diện tích, loại phòng) → Xem kết quả!",
    "ai gợi ý": "Hệ thống AI học từ lịch sử tìm kiếm của bạn (24h gần nhất) để gợi ý phòng phù hợp nhất!",
    "yêu cầu thuê": "Xem chi tiết phòng → Click 'Gửi yêu cầu thuê' → Điền thông tin → Chờ chủ nhà phản hồi.",
    "hủy yêu cầu": "Vào 'Yêu cầu của tôi' → Chọn yêu cầu cần hủy → Click 'Hủy yêu cầu'.",
    "loại phòng": "Có 4 loại: Phòng trọ (rẻ), Chung cư mini (cao cấp), Nhà nguyên căn (gia đình), Căn hộ dịch vụ (sang).",
}

# Bảng giá VIP (fallback khi database không truy cập được)
PRICING_FALLBACK = {
    "effective_date": "(fallback)",
    "packages": [
        {"name": "VIP 1", "posts_per_day": 5, "duration": "1 tuần", "title_color": "MÀU ĐỎ", "price_vnd": 500_000},
        {"name": "VIP 2", "posts_per_day": 3, "duration": "3 ngày", "title_color": "MÀU XANH", "price_vnd": 300_000},
        {"name": "VIP 3", "posts_per_day": 2, "duration": "1 ngày", "title_color": "MÀU HỒNG", "price_vnd": 150_000},
    ]
}

# Common keywords - Từ khóa thường gặp
KEYWORDS_MAP = {
    "giá rẻ": "500000-2000000",
    "giá mềm": "500000-2000000",
    "bình dân": "1000000-3000000",
    "cao cấp": "5000000-15000000",
    "sang": "7000000-15000000",
    "mini": "chung cư mini",
    "dịch vụ": "căn hộ dịch vụ",
    "nguyên căn": "nhà nguyên căn",
    "gần": "trong bán kính",  # Cần xử lý địa điểm
}
