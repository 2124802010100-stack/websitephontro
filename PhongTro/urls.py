
from django.contrib import admin
from django.urls import path,include
from django.conf.urls.static import static
from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from website import views as website_views
urlpatterns = [
    # Admin-scoped moderation endpoints so admin AJAX calls use admin session
    path('admin/moderation/approve/<int:post_id>/', admin.site.admin_view(website_views.approve_post), name='admin_approve_post'),
    path('admin/moderation/reject/<int:post_id>/', admin.site.admin_view(website_views.reject_post), name='admin_reject_post'),
    path('admin/', admin.site.urls),
    path('', include('website.urls')),
    path('chatbot/', include('chatbot.urls')),
    path('goiy-ai/', include('goiy_ai.urls')),  # Hệ thống gợi ý AI
    # django-allauth URLs
    path('accounts/', include('allauth.urls')),
]

# Static files (serve admin and app static in DEBUG)
urlpatterns += staticfiles_urlpatterns()

# Media files
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)