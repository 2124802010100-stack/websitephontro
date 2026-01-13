"""
URLs cho hệ thống gợi ý AI
"""
from django.urls import path
from . import views

app_name = 'goiy_ai'

urlpatterns = [
    # API để lấy gợi ý
    path('api/recommendations/', views.get_recommendations_view, name='get_recommendations'),

    # Tracking APIs
    path('track/view/<int:post_id>/', views.track_view, name='track_view'),
    path('track/save/<int:post_id>/', views.track_save, name='track_save'),
    path('track/unsave/<int:post_id>/', views.track_unsave, name='track_unsave'),
    path('track/contact/<int:post_id>/', views.track_contact, name='track_contact'),
    path('track/request/<int:post_id>/', views.track_request, name='track_request'),
    path('track/search/', views.track_search, name='track_search'),

    # Pages
    path('my-recommendations/', views.my_recommendations_page, name='my_recommendations'),
    path('analytics/', views.analytics_view, name='analytics'),
]
