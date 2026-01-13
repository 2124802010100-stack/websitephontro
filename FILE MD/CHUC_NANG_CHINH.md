# 10 Chức Năng Chính - Hệ Thống PHONGTRO

Tóm tắt 10 chức năng cốt lõi của đề tài website cho thuê phòng trọ.

---

## 1. ĐĂNG KÝ & QUẢN LÝ TÀI KHOẢN

## 1. ĐĂNG KÝ & QUẢN LÝ TÀI KHOẢN

**Làm gì**: Người dùng (khách hàng/chủ trọ) đăng ký tài khoản, đăng nhập, quên mật khẩu, cập nhật thông tin cá nhân.

**Chi tiết**:
- Đăng ký với email/username, mật khẩu, số điện thoại
- Phân quyền: Khách hàng (customer) hoặc Chủ cho thuê (owner)
- Xác thực OTP qua email cho các thao tác nhạy cảm (đổi mật khẩu, cập nhật thông tin)
- Tự động tạo ví tiền (Wallet) cho mỗi tài khoản mới

**Công nghệ**: Django User model, CustomerProfile (role), OTPCode, email backend

---

## 2. ĐĂNG TIN CHO THUÊ PHÒNG

**Làm gì**: Chủ trọ đăng tin cho thuê phòng với thông tin chi tiết và hình ảnh.

**Chi tiết**:
- Nhập: tiêu đề, mô tả, giá, diện tích, địa chỉ (tỉnh/quận/phường), loại phòng (phòng trọ/nhà nguyên căn/căn hộ/mặt bằng)
- Thêm tiện nghi: máy lạnh, nội thất, thang máy, bảo vệ 24/24...
- Upload ảnh (nhiều ảnh) và video
- Số lượng tin đăng/ngày phụ thuộc gói VIP
- Tin cần chờ Admin duyệt trước khi hiển thị công khai
- Chỉnh sửa, xóa, gia hạn tin đã đăng

**Công nghệ**: RentalPost model, RentalPostImage, VIPSubscription, file upload

---

## 3. TÌM KIẾM & LỌC PHÒNG TRỌ

**Làm gì**: Khách hàng tìm kiếm phòng theo tiêu chí (giá, diện tích, vị trí, tiện nghi).

**Chi tiết**:
- Tìm kiếm theo từ khóa (địa điểm, tiêu đề)
- Lọc theo: loại phòng, khoảng giá, diện tích, tỉnh/quận/phường, tiện nghi
- Sắp xếp: mặc định, giá tăng/giảm, diện tích, bài VIP ưu tiên
- Xem chi tiết: mô tả đầy đủ, ảnh, video, bản đồ, thông tin liên hệ, đánh giá chủ trọ
- Lưu phòng yêu thích để xem sau

**Công nghệ**: Django QuerySet filtering, AJAX load địa chỉ động (province/district/ward), SavedPost model

---

## 4. YÊU CẦU THUÊ PHÒNG & ĐẶT CỌC

**Làm gì**: Khách gửi yêu cầu thuê phòng, chủ trọ phản hồi, thực hiện đặt cọc nếu cần.

**Chi tiết**:
- **Khách**: Gửi yêu cầu thuê kèm lời nhắn → Chờ chủ trọ phản hồi
- **Chủ trọ**: Chấp nhận hoặc từ chối yêu cầu
- **Đặt cọc** (tùy chọn): Chủ yêu cầu đặt cọc → Khách thanh toán qua Ví/MoMo/VNPAY → Chủ xác nhận → Hệ thống sinh hóa đơn (DepositBill)
- **Xác nhận thuê**: Khách xác nhận chính thức thuê phòng sau khi chấp nhận/đặt cọc
- **Hủy**: Khách có thể yêu cầu hủy, chủ xác nhận hủy

**Công nghệ**: RentalRequest model, deposit workflow, DepositBill, payment gateway integration

---

## 5. VÍ TIỀN & THANH TOÁN ĐA CỔNG

**Làm gì**: Quản lý ví tiền nội bộ, nạp tiền, thanh toán qua MoMo/VNPAY.

**Chi tiết**:
- **Ví nội bộ**: Mỗi user có 1 ví (Wallet) lưu số dư
- **Nạp tiền**: Qua MoMo, VNPAY, chuyển khoản → Cộng vào ví
- **Chi tiêu**: Thanh toán đặt cọc, đăng ký VIP, gia hạn tin
- **Lịch sử giao dịch**: Nạp tiền (recharge), chi tiêu (spending), nhận tiền (income), mã giao dịch, thời gian
- **Callback tự động**: Cổng thanh toán gọi lại API để cập nhật trạng thái giao dịch real-time

**Công nghệ**: Wallet model, RechargeTransaction, MoMo API, VNPAY API, IPN/Return URL

---

## 6. GÓI VIP & ƯU TIÊN HIỂN THỊ

**Làm gì**: Chủ trọ đăng ký gói VIP để đăng nhiều tin hơn, tin hiển thị nổi bật.

**Chi tiết**:
- **3 gói VIP**: VIP1 (cao nhất), VIP2, VIP3
  - Giá, số tin đăng/ngày, thời gian hết hạn tin, màu tiêu đề khác nhau
- **Đăng ký**: Nạp ví → Chọn gói VIP → Thanh toán → Hệ thống tự động tính phí (include: Tính phí gói VIP)
- **Ưu tiên hiển thị**: Tin VIP hiển thị trước, màu sắc nổi bật (đỏ/xanh/hồng)
- **Cấu hình động**: Admin có thể thay đổi giá, quota trong VIPPackageConfig

**Công nghệ**: VIPSubscription model, VIPPackageConfig, cron job kiểm tra hết hạn

---

## 7. CHAT REAL-TIME & THÔNG BÁO

**Làm gì**: Khách và chủ trọ nhắn tin trực tiếp, nhận thông báo về các sự kiện quan trọng.

**Chi tiết**:
- **Chat**: Tạo thread chat riêng cho mỗi cặp khách-chủ-phòng, lưu lịch sử tin nhắn
- **Thông báo**: Tự động gửi khi:
  - Yêu cầu thuê mới/được chấp nhận/từ chối
  - Tin nhắn mới
  - Đặt cọc thành công
  - Tin đăng hết hạn/VIP hết hạn
  - Admin duyệt/từ chối tin
- **Đánh dấu đã đọc**: Theo dõi tin nhắn/thông báo chưa đọc

**Công nghệ**: ChatThread, ChatMessage, Notification model, WebSocket (tùy chọn cho real-time)

---

## 8. KIỂM DUYỆT & AI CONTENT MODERATION

**Làm gì**: Admin duyệt tin đăng, hệ thống AI tự động phát hiện tin nghi ngờ.

**Chi tiết**:
- **Kiểm duyệt thủ công**: Admin xem tin chờ duyệt → Duyệt hoặc Từ chối kèm lý do
- **AI tự động gắn cờ**: Khi tin mới được tạo, AI kiểm tra:
  - Rule-based: từ khóa spam, giá bất thường, mô tả quá ngắn...
  - ML model: dự đoán tin lừa đảo/spam
  - Kết quả lưu vào: `ai_flagged`, `ai_confidence`, `ai_reason`, `ai_rule_score`, `ai_ml_prediction`
- **Admin xem AI flags** (extend từ Duyệt tin): Xem chi tiết tin bị gắn cờ để quyết định chính xác hơn
- **Xử lý vi phạm**: Xóa tin, cảnh báo chủ trọ, ghi log

**Công nghệ**: RentalPost AI fields, rule engine, scikit-learn (ML), PostReport model

---

## 9. ĐÁNH GIÁ CHỦ TRỌ & BÁO CÁO VI PHẠM

**Làm gì**: Khách đánh giá chủ trọ sau khi thuê; người dùng báo cáo tin vi phạm.

**Chi tiết**:
- **Đánh giá**: Sau khi xác nhận thuê, khách có thể đánh giá chủ trọ (1-5 sao) + nhận xét
  - Mỗi yêu cầu thuê chỉ đánh giá 1 lần (OneToOne relation)
  - Hiển thị điểm trung bình và số lượt đánh giá trên trang chủ trọ
- **Báo cáo vi phạm**: Người dùng báo cáo tin đăng nghi ngờ: lừa đảo, trùng lặp, sai thông tin, không liên hệ được
  - Admin xem, xử lý, quyết định xóa tin hoặc bỏ qua

**Công nghệ**: LandlordReview model, PostReport model, admin workflow

---

## 10. HỆ THỐNG GỢI Ý AI & CHATBOT TƯ VẤN

**Làm gì**: Gợi ý phòng phù hợp dựa trên hành vi người dùng; chatbot tự động tư vấn.

**Chi tiết**:
- **Gợi ý AI (Recommendation)**:
  - Tracking: xem, lưu, liên hệ, tìm kiếm (PostView, UserInteraction, SearchHistory)
  - Thuật toán: Content-based (tương đồng tiêu chí), Collaborative filtering (người dùng tương tự), Hybrid
  - Hiển thị: Tab "Gợi ý cho bạn" trên trang chủ/tìm kiếm
- **Chatbot AI (Gemini)**:
  - Trả lời câu hỏi về: quy trình thuê, giá phòng, vị trí, tiện nghi...
  - RAG (Retrieval-Augmented Generation): Tìm kiếm semantic trong knowledge base (Markdown docs + database posts) → Trả lời chính xác
  - Widget chat nổi trên mọi trang

**Công nghệ**: goiy_ai app (models tracking), scikit-learn, chatbot app (Gemini API, VectorDocument, pgvector), RAG pipeline

---

## TỔNG KẾT 10 CHỨC NĂNG

| # | Chức năng | Người dùng | Mục đích chính |
|---|-----------|-----------|----------------|
| 1 | Đăng ký & Quản lý tài khoản | Tất cả | Xác thực, phân quyền, bảo mật |
| 2 | Đăng tin cho thuê phòng | Chủ trọ | Tạo/quản lý tin đăng |
| 3 | Tìm kiếm & Lọc phòng | Khách hàng | Tìm phòng phù hợp nhanh |
| 4 | Yêu cầu thuê & Đặt cọc | Khách + Chủ | Luồng thuê phòng hoàn chỉnh |
| 5 | Ví tiền & Thanh toán | Tất cả | Quản lý tài chính, nạp/chi tiêu |
| 6 | Gói VIP & Ưu tiên hiển thị | Chủ trọ | Tăng hiệu quả đăng tin |
| 7 | Chat & Thông báo | Khách + Chủ | Giao tiếp, cập nhật real-time |
| 8 | Kiểm duyệt & AI Moderation | Admin | Đảm bảo chất lượng tin đăng |
| 9 | Đánh giá & Báo cáo | Khách + Tất cả | Xây dựng uy tín, chống vi phạm |
| 10 | Gợi ý AI & Chatbot | Khách hàng | Tối ưu trải nghiệm, tư vấn tự động |

---

## CÔNG NGHỆ SỬ DỤNG

- **Backend**: Django (Python), PostgreSQL (pgvector cho semantic search)
- **AI/ML**: Gemini API (chatbot), scikit-learn (recommendation), TF-IDF/embeddings
- **Payment**: MoMo API, VNPAY API
- **Frontend**: HTML/CSS/JS, Bootstrap (có thể tích hợp Alpine.js/Vue)
- **Deployment**: Gunicorn + Nginx, Docker (option)

---

**Kết luận**: Hệ thống PHONGTRO cung cấp đầy đủ tính năng từ cơ bản (đăng tin, tìm kiếm) đến nâng cao (AI moderation, chatbot, gợi ý thông minh, thanh toán đa cổng, VIP, đánh giá), tạo nền tảng cho thuê phòng trọ hiện đại, an toàn và tiện lợi.
