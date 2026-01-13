from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

class SeparateSessionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Quy tắc đơn giản: chỉ dùng cookie `admin_sessionid` khi request hướng tới admin
        # (đường dẫn bắt đầu bằng '/admin'). Điều này đảm bảo admin không vô tình được
        # nhận diện trên phần website khi reload trang public.
        if request.path.startswith('/admin'):
            settings.SESSION_COOKIE_NAME = 'admin_sessionid'
        else:
            settings.SESSION_COOKIE_NAME = 'user_sessionid'

        # Ghi nhận lượt truy cập đơn giản.
        # AuthenticationMiddleware chạy sau middleware này, nên request.user
        # có thể chưa tồn tại — kiểm tra an toàn trước khi sử dụng.
        try:
            from website.models import SiteVisit
            ip = request.META.get('REMOTE_ADDR')
            user = getattr(request, 'user', None)
            if not request.path.startswith('/admin'):
                SiteVisit.objects.create(path=request.path[:255], ip=ip, user=user if getattr(user, 'is_authenticated', False) else None)
        except Exception:
            pass
