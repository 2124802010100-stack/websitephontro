"""
Custom social account adapter để tự động tạo username cho user đăng nhập Google
"""
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        """
        Tự động tạo username từ email trước khi user được lưu
        """
        user = super().populate_user(request, sociallogin, data)

        # Đảm bảo username được tạo - dùng toàn bộ email làm username
        if not user.username:
            email = user.email or data.get('email', '')
            if email:
                # Dùng toàn bộ email làm username (ví dụ: abc@gmail.com)
                username = email
                # Đảm bảo username không trùng (nếu trùng thì thêm số)
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    # Nếu trùng, thêm số vào trước @ (ví dụ: abc1@gmail.com)
                    if '@' in base_username:
                        local_part, domain = base_username.split('@', 1)
                        username = f"{local_part}{counter}@{domain}"
                    else:
                        username = f"{base_username}{counter}"
                    counter += 1
                user.username = username
                print(f"✅ [SocialAccountAdapter] Đã tạo username: {user.username} từ email: {email}")
            else:
                # Nếu không có email, dùng random
                import random
                username = f"user_{random.randint(100000, 999999)}"
                while User.objects.filter(username=username).exists():
                    username = f"user_{random.randint(100000, 999999)}"
                user.username = username
                print(f"✅ [SocialAccountAdapter] Đã tạo username random: {user.username}")

        return user

