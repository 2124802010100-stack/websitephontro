# 🚀 Deploy Django lên Render.com (MIỄN PHÍ & CỰC DỄ)

## ✨ Tại sao chọn Render?
- ✅ **HOÀN TOÀN MIỄN PHÍ** mãi mãi
- ✅ PostgreSQL miễn phí
- ✅ Tự động deploy từ GitHub
- ✅ SSL/HTTPS miễn phí
- ✅ Hỗ trợ WebSocket (Django Channels)
- ✅ Không cần config phức tạp

⚠️ **Giới hạn free tier:** App sẽ "ngủ" sau 15 phút không hoạt động (khởi động lại mất ~30 giây khi có request mới)

---

## 📋 BƯỚC 1: Chuẩn bị Code

### Đảm bảo các file đã có:
- ✅ `requirements.txt` - Đã cập nhật
- ✅ `build.sh` - Script build tự động
- ✅ `render.yaml` - Config Render
- ✅ `PhongTro/settings_render.py` - Settings production

### Tạo file `.gitignore` (nếu chưa có):
```bash
*.pyc
__pycache__/
db.sqlite3
.env
staticfiles/
media/
*.log
```

---

## 📋 BƯỚC 2: Push Code lên GitHub

```bash
# Khởi tạo Git (nếu chưa có)
git init

# Add tất cả files
git add .

# Commit
git commit -m "Ready for Render deployment"

# Tạo repo mới trên GitHub
# Truy cập: https://github.com/new
# Tên repo: phongtro (hoặc tên bạn thích)

# Link với GitHub
git remote add origin https://github.com/YOUR_USERNAME/phongtro.git

# Push code
git branch -M main
git push -u origin main
```

---

## 📋 BƯỚC 3: Đăng ký Render.com

1. Truy cập: **https://render.com/**
2. Click **"Get Started"**
3. Đăng ký bằng **GitHub account** (QUAN TRỌNG!)
4. Authorize Render truy cập GitHub của bạn

---

## 📋 BƯỚC 4: Deploy lên Render (5 phút)

### 4.1. Tạo PostgreSQL Database

1. Dashboard → Click **"New +"** → Chọn **"PostgreSQL"**
2. Điền thông tin:
   - **Name:** `phongtro-db`
   - **Database:** `phongtro`
   - **User:** `phongtro`
   - **Region:** Singapore (gần VN nhất)
   - **Plan:** **FREE**
3. Click **"Create Database"**
4. **LƯU LẠI:**
   - Internal Database URL (dạng: `postgresql://...`)
   - Render tự động cung cấp biến `DATABASE_URL`

### 4.2. Tạo Web Service

1. Dashboard → Click **"New +"** → Chọn **"Web Service"**
2. Connect GitHub repository: Chọn repo `phongtro`
3. Điền thông tin:

   **Basic Info:**
   - **Name:** `phongtro` (hoặc tên bạn thích)
   - **Region:** Singapore
   - **Branch:** `main`
   - **Runtime:** `Python 3`

   **Build & Deploy:**
   - **Build Command:** `./build.sh`
   - **Start Command:** `gunicorn PhongTro.wsgi:application`

4. Click **"Advanced"** để thêm Environment Variables:

   **PHẢI CÓ:**
   ```
   PYTHON_VERSION = 3.11.0
   DJANGO_SETTINGS_MODULE = PhongTro.settings_render
   SECRET_KEY = [Click "Generate" để tạo tự động]
   ```

   **TÙY CHỌN (cho Email):**
   ```
   EMAIL_HOST_USER = your-email@gmail.com
   EMAIL_HOST_PASSWORD = your-app-password
   ```

   **TÙY CHỌN (cho Groq AI):**
   ```
   GROP_API_KEY = your-groq-api-key-here
   GROP_MODEL = llama-3.3-70b-versatile
   ```
   ℹ️ Lấy Groq API key miễn phí tại: https://console.groq.com/

5. Scroll xuống **"Plan"** → Chọn **"Free"**

6. Click **"Create Web Service"** 🚀

---

## 📋 BƯỚC 5: Đợi Deploy (3-5 phút)

Render sẽ tự động:
1. ✅ Clone code từ GitHub
2. ✅ Cài đặt dependencies (`requirements.txt`)
3. ✅ Chạy `build.sh` (collectstatic + migrate)
4. ✅ Khởi động server với gunicorn
5. ✅ Tạo URL miễn phí: `https://phongtro-xxx.onrender.com`

**Xem logs:**
- Click vào service vừa tạo
- Tab **"Logs"** để xem quá trình build

**Nếu thành công, bạn sẽ thấy:**
```
==> Build successful 🎉
==> Deploying...
==> Your service is live at https://phongtro-xxx.onrender.com
```

---

## 📋 BƯỚC 6: Tạo Superuser

1. Vào Dashboard → Chọn service `phongtro`
2. Tab **"Shell"** → Click **"Connect"**
3. Chạy lệnh:
```bash
python manage.py createsuperuser
```
4. Nhập username, email, password

---

## 📋 BƯỚC 7: Cấu hình Google OAuth (Tùy chọn)

### 7.1. Google Cloud Console
1. Truy cập: https://console.cloud.google.com/
2. Credentials → Chọn OAuth Client
3. **Authorized redirect URIs** → Thêm:
   ```
   https://phongtro-xxx.onrender.com/accounts/google/login/callback/
   ```
   (Thay `phongtro-xxx` bằng URL Render của bạn)

### 7.2. Django Admin
1. Truy cập: `https://phongtro-xxx.onrender.com/admin`
2. Login với superuser vừa tạo
3. **Sites** → Sửa domain:
   - Domain: `phongtro-xxx.onrender.com`
   - Display name: `PhongTro`
4. **Social applications** → Add Google OAuth:
   - Provider: Google
   - Client ID: (từ Google Cloud Console)
   - Secret key: (từ Google Cloud Console)
   - Sites: Chọn site vừa sửa

---

## 🎉 HOÀN TẤT!

Website của bạn đã LIVE tại: **https://phongtro-xxx.onrender.com**

### Kiểm tra:
- ✅ Trang chủ: `https://phongtro-xxx.onrender.com/`
- ✅ Admin: `https://phongtro-xxx.onrender.com/admin/`
- ✅ SSL/HTTPS tự động

---

## 🔄 Cập nhật Code Sau Này

**CỰC KỲ ĐỆN GIẢN:**

```bash
# Sửa code trong project
git add .
git commit -m "Update features"
git push origin main
```

→ **Render tự động deploy lại!** (3-5 phút)

Xem quá trình deploy trong tab **"Logs"**

---

## 🔧 Xử Lý Lỗi

### ❌ Build failed

**Xem logs để tìm lỗi:**
- Tab "Logs" → Tìm dòng màu đỏ
- Thường là: thiếu package trong `requirements.txt`

**Fix:**
```bash
# Thêm package vào requirements.txt
git add requirements.txt
git commit -m "Fix dependencies"
git push
```

### ❌ Application failed to start

**Kiểm tra:**
1. Environment variables đã đúng chưa?
2. `DJANGO_SETTINGS_MODULE = PhongTro.settings_render`
3. `SECRET_KEY` đã generate chưa?

### ❌ Static files không load

**Trong settings_render.py, kiểm tra:**
```python
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
```

**Re-deploy:**
```bash
git commit --allow-empty -m "Trigger rebuild"
git push
```

### ❌ Database connection error

**Kiểm tra:**
- PostgreSQL đã tạo chưa?
- Render tự động inject `DATABASE_URL` vào environment

---

## 💡 Tips & Tricks

### 1️⃣ Tránh App "Ngủ" (Upgrade)
- Free tier: App ngủ sau 15 phút
- **Giải pháp miễn phí:** Dùng UptimeRobot ping mỗi 5 phút
- **Giải pháp trả phí:** Upgrade lên $7/tháng

### 2️⃣ Custom Domain
1. Mua domain (Namecheap, GoDaddy, etc.)
2. Render Dashboard → Service → Settings → Custom Domain
3. Add domain và config DNS theo hướng dẫn

### 3️⃣ Environment Variables
- Đừng hardcode secrets trong code
- Dùng Environment Variables trong Render Dashboard
- Ví dụ: `SECRET_KEY`, `EMAIL_PASSWORD`, API keys

### 4️⃣ Scheduled Tasks (Cron jobs)
- Free tier KHÔNG hỗ trợ
- Cần upgrade lên Starter ($7/tháng)

### 5️⃣ Logs & Monitoring
- Tab "Logs" để xem real-time logs
- Tab "Metrics" để xem CPU/Memory usage

---

## 📊 So Sánh Plan

| Tính năng | Free | Starter ($7/tháng) |
|-----------|------|-------------------|
| SSL/HTTPS | ✅ | ✅ |
| PostgreSQL | ✅ (1GB) | ✅ (Unlimited) |
| Custom Domain | ✅ | ✅ |
| Auto-deploy | ✅ | ✅ |
| App Sleep | ⚠️ 15 phút | ✅ Không ngủ |
| Cron Jobs | ❌ | ✅ |
| RAM | 512MB | 1GB+ |

---

## 🆘 Cần Giúp Đỡ?

- **Render Docs:** https://render.com/docs
- **Django Deployment:** https://docs.djangoproject.com/en/4.2/howto/deployment/
- **Community:** https://community.render.com/

---

## 🎯 Next Steps

Sau khi deploy thành công:

1. ✅ Test tất cả chức năng
2. ✅ Setup Google Analytics (nếu muốn)
3. ✅ Configure SEO (meta tags, sitemap)
4. ✅ Setup backup database
5. ✅ Monitor performance

**Chúc mừng bạn đã deploy thành công! 🎉**
