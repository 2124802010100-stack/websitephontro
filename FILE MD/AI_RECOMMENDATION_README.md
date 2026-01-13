# 🎯 Hệ Thống Gợi Ý Phòng Trọ Thông Minh (AI Recommendation System)

## 📂 Vị trí

Toàn bộ code nằm trong folder: **`goiy_ai/`**

## 📖 Tài liệu

- **`goiy_ai/README.md`** - Hướng dẫn chi tiết, API, cách dùng
- **`goiy_ai/SUMMARY.md`** - Tổng quan những gì đã làm
- **`goiy_ai/TESTING_GUIDE.md`** - Hướng dẫn test
- **`goiy_ai/TRACKING_INTEGRATION.md`** - Tích hợp tracking

## 🚀 Quick Start

### 1. Đã cài đặt sẵn

- ✅ App đã add vào `INSTALLED_APPS`
- ✅ URLs đã config
- ✅ Models đã migrate
- ✅ Tích hợp vào trang chủ

### 2. Xem ngay

```bash
python manage.py runserver

# Truy cập: http://127.0.0.1:8000/

# Tìm section "Gợi ý dành riêng cho bạn" (màu tím)

```

### 3. APIs

```

GET /goiy-ai/api/recommendations/          # Lấy gợi ý
GET /goiy-ai/my-recommendations/           # Trang gợi ý cá nhân
POST /goiy-ai/track/view/<post_id>/        # Track xem
POST /goiy-ai/track/save/<post_id>/        # Track lưu
POST /goiy-ai/track/search/                # Track tìm kiếm

```

## 🧠 AI/ML Algorithms

1. **Content-Based Filtering** - Gợi ý dựa trên đặc điểm phòng
2. **Collaborative Filtering** - "Người giống bạn cũng thích..."
3. **Hybrid Recommender** - Kết hợp cả 2

## 📊 Admin

Xem dữ liệu tracking:

```

http://127.0.0.1:8000/admin/goiy_ai/

```

## 🎨 Features

- ✨ AI tự học từ hành vi user
- 🎯 Gợi ý cá nhân hóa
- 📱 Responsive design
- ⚡ Performance tốt
- 🔒 Privacy-friendly

## 📝 TODO

Xem file `goiy_ai/README.md` section "TODO" để biết tính năng có thể mở rộng.

---

**Tất cả code clean, có comments đầy đủ, dễ maintain!** 🎉
