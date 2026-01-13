"""
Middleware để kiểm tra và redirect user đăng nhập Google lần đầu đến trang chọn role
"""
from django.shortcuts import redirect
from allauth.socialaccount.models import SocialAccount


class CheckSocialLoginMiddleware:
    """
    Middleware kiểm tra user đăng nhập bằng Google và redirect đến trang chọn role nếu cần
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Chỉ xử lý khi user đã đăng nhập
        if request.user.is_authenticated:
            # Bỏ qua nếu đang ở trang chọn role hoặc đang logout
            if request.path in ['/chon-vai-tro/', '/accounts/logout/', '/dang-xuat/']:
                response = self.get_response(request)
                return response
            
            try:
                from website.models import CustomerProfile
                
                # Kiểm tra xem user có đăng nhập bằng Google không
                has_social_account = SocialAccount.objects.filter(user=request.user).exists()
                
                # Nếu user đăng nhập bằng Google
                if has_social_account:
                    # Kiểm tra xem user có CustomerProfile chưa
                    if not hasattr(request.user, 'customerprofile'):
                        # Tạo CustomerProfile nếu chưa có
                        CustomerProfile.objects.create(
                            user=request.user,
                            role='customer',  # Mặc định là khách hàng
                        )
                        # Redirect đến trang chọn role
                        return redirect('/chon-vai-tro/')
                    
                    # Kiểm tra xem user đã có display_name chưa
                    profile = request.user.customerprofile
                    # Nếu chưa có display_name và chưa có first_name, và chưa từng hiển thị trang chọn role
                    if not profile.display_name and not request.user.first_name and not request.session.get('role_selection_shown'):
                        # Redirect đến trang chọn role
                        return redirect('/chon-vai-tro/')
                            
            except Exception as e:
                print(f"❌ Lỗi trong CheckSocialLoginMiddleware: {e}")
        
        response = self.get_response(request)
        return response

