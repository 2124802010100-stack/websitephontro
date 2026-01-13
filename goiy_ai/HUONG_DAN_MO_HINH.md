# HƯỚNG DẪN MÔ HÌNH GỢI Ý TIN ĐĂNG

## 0. KIẾN TRÚC TỔNG QUAN

### Hệ thống dùng 3 thành phần

#### 1. Recommendation System (Hệ thống gợi ý)

- Đây là **TÊN CHUNG** của toàn bộ hệ thống
- KHÔNG phải là 1 thuật toán cụ thể
- Bao gồm cả Collaborative Filtering + Content-based

#### 2. Collaborative Filtering (Lọc cộng tác) - THUẬT TOÁN CHÍNH

- Dùng **Machine Learning** với thuật toán **ALS**
- Học từ **hành vi user** (xem, click, lưu bài)
- File: `goiy_ai/ml_models/cf_als.py`

#### 3. Content-based Filtering (Lọc dựa nội dung) - THUẬT TOÁN PHỤ

- **KHÔNG dùng ML**, chỉ là **rules-based** (lọc theo từ khóa)
- Dùng làm **backup** khi CF không khả dụng
- File: `goiy_ai/ml_models/content_based.py`

### Cách hoạt động

```text
User yêu cầu gợi ý
   ↓
Hybrid System kiểm tra
   ↓
[CÓ model ML?]
   ├─ CÓ → Dùng Collaborative Filtering (ALS) - 60%
   │        + Content-based - 40%
   │
   └─ KHÔNG → Fallback toàn bộ sang Content-based
```

**File hybrid:** `goiy_ai/ml_models/hybrid.py`

---

## 1. THUẬT TOÁN MACHINE LEARNING CHÍNH

### Thuật toán: **ALS (Alternating Least Squares)** - Collaborative Filtering

**ALS là gì?**

- ALS là thuật toán **Matrix Factorization** (phân rã ma trận) dùng cho **Collaborative Filtering**
- Thuộc nhóm Machine Learning **không giám sát** (Unsupervised Learning)
- Chuyên dùng cho hệ thống gợi ý với **implicit feedback** (tương tác ngầm: xem, click, lưu...)

**ALS làm gì?**

1. **Phân rá ma trận User×Item** thành 2 ma trận nhỏ hơn:
   - Ma trận User Embeddings (2 users × 32 factors)
   - Ma trận Item Embeddings (10 items × 32 factors)

2. **Học các đặc trưng ẩn** (latent factors):
   - Mỗi user được biểu diễn bằng 32 con số (embedding vector)
   - Mỗi bài đăng cũng được biểu diễn bằng 32 con số
   - Các con số này **tự động học** từ hành vi user, không cần định nghĩa trước

3. **Dự đoán sở thích**:
   - Tính tích vô hướng (dot product) giữa user vector và item vector
   - Điểm số cao = user có khả năng thích item đó cao

**File code:** `goiy_ai/ml_models/cf_als.py`

---

## 2. ĐIỀU KIỆN ĐỂ MÔ HÌNH LỌC RA CÁC BÀI

### Điều kiện lọc dữ liệu training

#### a) Dữ liệu đầu vào (UserInteraction)

```python
# Lấy tương tác trong 90 ngày gần nhất (mặc định)
interactions = UserInteraction.objects.filter(
    timestamp__gte=timezone.now() - timedelta(days=90)
)
```

- Chỉ lấy tương tác trong **90 ngày** gần nhất (có thể điều chỉnh)
- Các loại tương tác được tính:
  - `view`: Xem bài (trọng số = 1)
  - `click`: Click vào bài (trọng số = 2)
  - `save`: Lưu bài (trọng số = 5)

#### b) Trọng số tương tác

```python
# Công thức tính trọng số
weight = view_count * 1 + click_count * 2 + save_count * 5
```

#### c) Yêu cầu tối thiểu

- Cần ít nhất **2 users** có tương tác
- Cần ít nhất **2 bài đăng** được tương tác
- Nếu không đủ → Tự động fallback sang Content-based (lọc theo từ khóa)

### Điều kiện lọc khi gợi ý

#### Khi dự đoán cho user

1. **Loại bỏ bài đã tương tác:** Không gợi ý lại bài user đã xem/lưu
2. **Chỉ lấy bài approved:** `status='approved'`
3. **Sắp xếp theo điểm dự đoán:** Từ cao xuống thấp
4. **Top N bài:** Mặc định lấy 10 bài điểm cao nhất

**File code:** `goiy_ai/ml_models/hybrid.py` (dòng ~45-80)

---

## 3. THƯ VIỆN SỬ DỤNG

### Thư viện Machine Learning chính

#### a) implicit (v0.7.2)

```python
from implicit.als import AlternatingLeastSquares
```

- **Mục đích:** Huấn luyện mô hình ALS Collaborative Filtering
- **Lý do chọn:**
  - Tối ưu cho implicit feedback (xem, click, save)
  - Nhanh với sparse matrix (ma trận thưa)
  - Hỗ trợ GPU nếu có

#### b) numpy (v1.26.4)

```python
import numpy as np
```

- **Mục đích:** Tính toán ma trận, vector operations
- **Sử dụng:** Xử lý embeddings, tính dot product

#### c) scipy (v1.15.1)

```python
from scipy.sparse import csr_matrix
```

- **Mục đích:** Lưu trữ ma trận thưa (sparse matrix)
- **Lý do:** Tiết kiệm bộ nhớ khi có nhiều bài nhưng ít tương tác

#### d) pickle (Python standard library)

```python
import pickle
```

- **Mục đích:** Lưu và load model đã huấn luyện
- **File lưu:** `goiy_ai/ml_models/trained_models/cf_als_model.pkl`

### Cài đặt

```bash
pip install implicit==0.7.2 numpy scipy
```

**File code:** `goiy_ai/ml_models/cf_als.py` (dòng 1-10)

---

## 4. KHI NÀO HUẤN LUYỆN MÔ HÌNH

### Lệnh huấn luyện

```bash
# Lệnh cơ bản (dùng tham số mặc định)
python manage.py train_cf_model

# Lệnh đầy đủ với tùy chỉnh
python manage.py train_cf_model --days 90 --factors 32 --iterations 10 --alpha 40 --regularization 0.01
```

#### Giải thích tham số

- `--days 90`: Lấy dữ liệu tương tác trong 90 ngày gần nhất
- `--factors 32`: Số chiều của embedding vector (latent factors)
- `--iterations 10`: Số vòng lặp huấn luyện
- `--alpha 40`: Trọng số cho implicit feedback (càng cao càng tin tưởng vào tương tác)
- `--regularization 0.01`: Hệ số regularization (tránh overfitting)

### Khi nào nên huấn luyện?

#### A. Lần đầu

- Ngay sau khi cài đặt xong hệ thống
- Cần có ít nhất 2 users có tương tác với 2 bài

#### B. Định kỳ

| Kích thước hệ thống | Tần suất huấn luyện lại |
|---------------------|------------------------|
| **Nhỏ** (<100 users) | **1 tuần/lần** |
| **Trung bình** (100-1000 users) | **3-4 ngày/lần** |
| **Lớn** (>1000 users) | **Mỗi ngày** |

#### C. Khi có sự kiện đặc biệt

- Có nhiều bài đăng mới (>50 bài/ngày)
- User tăng đột biến
- Phát hiện gợi ý không chính xác

### Nếu KHÔNG huấn luyện có sao không?

#### Trường hợp 1: Chưa từng huấn luyện

- ❌ Model file không tồn tại
- ✅ Hệ thống **TỰ ĐỘNG** chuyển sang **Content-based** (lọc theo từ khóa)
- ✅ Website vẫn hoạt động bình thường, KHÔNG bị lỗi

#### Trường hợp 2: Đã huấn luyện nhưng lâu rồi

- ⚠️ Gợi ý **KHÔNG CẬP NHẬT** theo hành vi mới của user
- ⚠️ Bài đăng mới có thể **KHÔNG ĐƯỢC GỢI Ý**
- ⚠️ Độ chính xác **GIẢM DẦN** theo thời gian

#### Kết luận

- Không huấn luyện → **Hệ thống vẫn chạy** (fallback sang Content-based)
- Nhưng **NÊN** huấn luyện định kỳ để có gợi ý ML chính xác hơn

### Tự động hóa huấn luyện (Tùy chọn)

#### Windows Task Scheduler

```bash
schtasks /create /tn "TrainML" /tr "python D:\WEBPYTHON\PHONGTRO\manage.py train_cf_model" /sc weekly /d SUN /st 02:00
```

- Tự động chạy **mỗi Chủ nhật lúc 2 giờ sáng**
- Không cần can thiệp thủ công

**File code:** `goiy_ai/management/commands/train_cf_model.py`

---

## TÓM TẮT NHANH

| Câu hỏi | Trả lời ngắn |
|---------|--------------|
| **Recommendation System là gì?** | Tên chung của cả hệ thống, KHÔNG phải 1 thuật toán |
| **Content-based Filtering?** | Thuật toán PHỤ (backup), rules-based, KHÔNG dùng ML, lọc theo từ khóa/giá/danh mục |
| **Collaborative Filtering?** | Thuật toán CHÍNH (ML), dùng ALS, học từ hành vi user |
| **1. Thuật toán ML?** | ALS (Alternating Least Squares), phân rã ma trận User×Item thành embedding vectors |
| **2. Điều kiện lọc?** | Tương tác 90 ngày gần nhất, trọng số view=1/click=2/save=5, loại bỏ bài đã xem, chỉ lấy approved |
| **3. Thư viện ML?** | `implicit` (ALS), `numpy` (tính toán), `scipy` (sparse matrix), `pickle` (lưu model) |
| **4. Khi nào train?** | Lệnh: `python manage.py train_cf_model`, Tần suất: 1 tuần/lần (hệ thống nhỏ), Không train → tự động dùng Content-based |

### Sơ đồ kiến trúc

```text
┌─────────────────────────────────────────┐
│   RECOMMENDATION SYSTEM (Hệ thống)     │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │  Hybrid Recommender (Kết hợp)    │ │
│  │                                   │ │
│  │  ┌──────────────────────────┐    │ │
│  │  │ Collaborative Filtering  │    │ │
│  │  │  (ML - ALS) - 60%       │    │ │
│  │  │  ✓ Học từ hành vi       │    │ │
│  │  │  ✓ Dự đoán sở thích     │    │ │
│  │  └──────────────────────────┘    │ │
│  │              +                    │ │
│  │  ┌──────────────────────────┐    │ │
│  │  │ Content-based Filtering  │    │ │
│  │  │  (Rules) - 40%          │    │ │
│  │  │  ✓ Lọc từ khóa/giá      │    │ │
│  │  │  ✓ Không cần train      │    │ │
│  │  └──────────────────────────┘    │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

---

**Ngày cập nhật:** 01/11/2025
**Version:** 1.1
