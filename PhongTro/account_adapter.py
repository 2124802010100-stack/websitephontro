"""
Custom account adapter cho django-allauth
Để redirect đến trang chọn role sau khi đăng nhập Google lần đầu
"""
from allauth.account.adapter import DefaultAccountAdapter


class CustomAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        # Kiểm tra flag trong session (được set bởi signal)
        if request.session.get('show_role_selection'):
            return '/chon-vai-tro/'
        
        # Kiểm tra thêm: nếu user đã đăng nhập nhưng chưa có CustomerProfile
        # hoặc user đăng nhập bằng Google lần đầu (có SocialAccount nhưng chưa chọn role)
        if request.user.is_authenticated:
            try:
                from allauth.socialaccount.models import SocialAccount
                from website.models import CustomerProfile
                
                # Kiểm tra xem user có đăng nhập bằng Google không
                has_social_account = SocialAccount.objects.filter(user=request.user).exists()
                
                # Kiểm tra xem user có CustomerProfile chưa
                if not hasattr(request.user, 'customerprofile'):
                    # Tạo CustomerProfile nếu chưa có
                    CustomerProfile.objects.create(
                        user=request.user,
                        role='customer',  # Mặc định là khách hàng
                    )
                    # Set flag để redirect đến trang chọn role
                    request.session['show_role_selection'] = True
                    request.session.save()
                    return '/chon-vai-tro/'
                
                # Nếu user đăng nhập bằng Google và chưa có display_name, cũng redirect
                # (để họ có thể nhập tên hiển thị)
                if has_social_account:
                    profile = request.user.customerprofile
                    # Nếu chưa có display_name và chưa có first_name, redirect để nhập
                    if not profile.display_name and not request.user.first_name:
                        request.session['show_role_selection'] = True
                        request.session.save()
                        return '/chon-vai-tro/'
                        
            except Exception as e:
                print(f"❌ Lỗi kiểm tra CustomerProfile trong adapter: {e}")
        
        return super().get_login_redirect_url(request)

