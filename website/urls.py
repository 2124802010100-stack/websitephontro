from django.urls import path
from . import views
from .analytics_views import (
    owner_dashboard,
    analytics_overview_api,
    analytics_chart_data_api,
    analytics_top_posts_api,
    analytics_post_detail_api,
    analytics_insights_api,
    analytics_revenue_api,
    analytics_pie_chart_api,
    analytics_views_detail_api,
    analytics_saves_detail_api,
    analytics_contacts_detail_api
)
from .map_views import (
    map_view,
    map_data_api,
    poi_data_api,
    nearby_pois_api
)

urlpatterns = [
    path('', views.home, name='home'),

    # Analytics Dashboard
    path('analytics/', owner_dashboard, name='owner_analytics'),
    path('analytics/api/overview/', analytics_overview_api, name='analytics_overview_api'),
    path('analytics/api/chart-data/', analytics_chart_data_api, name='analytics_chart_data_api'),
    path('analytics/api/top-posts/', analytics_top_posts_api, name='analytics_top_posts_api'),
    path('analytics/api/post/<int:post_id>/', analytics_post_detail_api, name='analytics_post_detail_api'),
    path('analytics/api/insights/', analytics_insights_api, name='analytics_insights_api'),
    path('analytics/api/revenue/', analytics_revenue_api, name='analytics_revenue_api'),
    path('analytics/api/pie-chart/', analytics_pie_chart_api, name='analytics_pie_chart_api'),
    path('analytics/api/views-detail/', analytics_views_detail_api, name='analytics_views_detail_api'),
    path('analytics/api/saves-detail/', analytics_saves_detail_api, name='analytics_saves_detail_api'),
    path('analytics/api/contacts-detail/', analytics_contacts_detail_api, name='analytics_contacts_detail_api'),
    # Articles
    path('bai-viet/<slug:slug>/', views.article_detail, name='article_detail'),
    path('dang-ky/', views.register_view, name='register'),
    path('dang-nhap/', views.login_view, name='login'),
    path('quen-mat-khau/', views.forgot_password, name='forgot_password'),
    path('dang-xuat/', views.logout_view, name='logout'),
    path('dang-tin/', views.post_create, name='post_create'),
    path('category/<slug:category_slug>/', views.post_by_category, name='post_by_category'),
    path('quan-ly-phong/', views.manage_rooms, name='manage_rooms'),
    path('quan-ly-thue/', views.rental_management, name='rental_management'),
    path('bai-dang-het-han/', views.expired_posts, name='expired_posts'),
    path('chon-bai-gia-han/', views.select_posts_to_renew, name='select_posts_to_renew'),
    path('post/<int:pk>/', views.post_detail, name='post_detail'),
    path("sua-phong/<int:room_id>/", views.edit_room, name="edit_room"),
    path("xoa-phong/<int:room_id>/", views.delete_room, name="delete_room"),
    path("delete-room-image/<int:image_id>/", views.delete_room_image, name="delete_room_image"),
    path('rooms/<int:room_id>/toggle-rented/', views.toggle_rented, name='toggle_rented'),
    path('saved/', views.saved_posts_list, name='saved_posts'),
    path('saved/toggle/<int:post_id>/', views.toggle_save_post, name='toggle_save_post'),
    path('my-rooms/', views.my_rooms, name='my_rooms'),
    path('deleted-logs/', views.deletion_logs, name='deletion_logs'),
    path("bang-gia-dich-vu/", views.bang_gia_dich_vu, name="bang_gia_dich_vu"),
    path('dang-ky-vip/', views.subscribe_vip, name='subscribe_vip'),
    path('saved/request/<int:post_id>/', views.send_rental_request, name='send_rental_request'),
    path('saved/confirm/<int:request_id>/', views.confirm_rental_request, name='confirm_rental_request'),
    # Reviews
    path('reviews/submit/<int:request_id>/', views.submit_landlord_review, name='submit_landlord_review'),
    path('landlord/<int:user_id>/reviews/', views.landlord_reviews, name='landlord_reviews'),
    path('reviews/delete/<int:review_id>/', views.delete_landlord_review, name='delete_landlord_review'),

    # Account settings + OTP
    path('account/', views.account_settings, name='account_settings'),
    path('chon-vai-tro/', views.select_role, name='select_role'),
    path('account/send-otp/', views.send_account_otp, name='send_account_otp'),
    path('account/change-password/', views.change_password, name='change_password'),

    # Chat URLs
    path('chat/<int:thread_id>/', views.chat_thread, name='chat_thread'),
    path('chat/<int:thread_id>/send/', views.send_chat_message, name='send_chat_message'),
    path('chat/<int:thread_id>/delete/', views.delete_thread, name='delete_thread'),
    path('chat/<int:thread_id>/hard-delete/', views.hard_delete_thread, name='hard_delete_thread'),
    path('chat/start/<int:post_id>/', views.start_chat, name='start_chat'),
    path('delete-message/<int:message_id>/', views.delete_message, name='delete_message'),
    path('my-chats/', views.my_chats, name='my_chats'),
    path('my-chats/mark-all-read/', views.mark_all_chats_read, name='mark_all_chats_read'),

    # Rental list + AJAX
    path('phong-tro/', views.rental_list, name='rental_list'),
    path("ajax/load-provinces/", views.load_provinces, name="ajax_load_provinces"),
    path("ajax/load-districts/", views.load_districts, name="ajax_load_districts"),
    path("ajax/load-wards/", views.load_wards, name="ajax_load_wards"),

    # Moderation actions (called from admin widget)
    path('moderation/approve/<int:post_id>/', views.approve_post, name='approve_post'),
    path('moderation/reject/<int:post_id>/', views.reject_post, name='reject_post'),

    # Wallet & Recharge URLs
    path('vi-tien/', views.wallet_view, name='wallet'),
    path('nap-tien/', views.recharge_view, name='recharge'),
    path('lich-su-nap-tien/', views.recharge_history, name='recharge_history'),
    path('giao-dich-nap-tien/<str:transaction_id>/', views.recharge_transaction_detail, name='recharge_transaction_detail'),
    path('lich-su-thanh-toan/', views.payment_history, name='payment_history'),
    path('giao-dich-thanh-toan/<str:transaction_id>/', views.payment_transaction_detail, name='payment_transaction_detail'),
    path('lich-su-nhan-tien/', views.income_history, name='income_history'),
    path('giao-dich-nhan-tien/<str:transaction_id>/', views.income_transaction_detail, name='income_transaction_detail'),
    path('api/wallet-balance/', views.get_wallet_balance, name='get_wallet_balance'),
    # MoMo sandbox endpoints
    path('payments/momo/create/', views.initiate_momo_payment, name='momo_create'),
    path('payments/momo/notify/', views.momo_notify, name='momo_notify'),
    path('payments/momo/return/', views.momo_return, name='momo_return'),
    # VNPAY
    path('payments/vnpay/create/', views.initiate_vnpay_payment, name='vnpay_create'),
    path('payments/vnpay/notify/', views.vnpay_notify, name='vnpay_notify'),
    path('payments/vnpay/return/', views.vnpay_return, name='vnpay_return'),
    path('payments/vnpay/diag/', views.vnpay_diag, name='vnpay_diag'),
    path('accept-rental-request/<int:request_id>/', views.accept_rental_request, name='accept_rental_request'),
    path('decline-rental-request/<int:request_id>/', views.decline_rental_request, name='decline_rental_request'),path('cancel-rental-request/<int:request_id>/', views.cancel_rental_request, name='cancel_rental_request'),
    # Đặt cọc
    path('rental-request/<int:request_id>/deposit/request/', views.owner_request_deposit, name='owner_request_deposit'),
    path('rental-request/<int:request_id>/deposit/waive/', views.owner_waive_deposit, name='owner_waive_deposit'),
    path('rental-request/<int:request_id>/deposit/pay/', views.customer_pay_deposit, name='customer_pay_deposit'),
    path('rental-request/<int:request_id>/deposit/cancel/', views.customer_cancel_deposit, name='customer_cancel_deposit'),
    path('rental-request/<int:request_id>/deposit/payment/<str:method>/', views.deposit_payment_gateway, name='deposit_payment_gateway'),
    path('rental-request/<int:request_id>/deposit/confirm/', views.owner_confirm_deposit, name='owner_confirm_deposit'),
    path('rental-request/<int:request_id>/deposit/bill/', views.view_deposit_bill, name='view_deposit_bill'),
    # Deposit payment callbacks
    path('payments/deposit/momo/return/', views.deposit_momo_return, name='deposit_momo_return'),
    path('owner-cancel-rental-request/<int:request_id>/', views.owner_cancel_rental_request, name='owner_cancel_rental_request'),
    path('owner-confirm-cancel/<int:request_id>/', views.owner_confirm_cancel, name='owner_confirm_cancel'),
    path('delete-rental-request/<int:request_id>/', views.delete_rental_request, name='delete_rental_request'),
    # Báo cáo vi phạm
    path('post/<int:post_id>/report/', views.submit_report, name='submit_report'),
    path('lich-su-bao-cao/', views.report_history, name='report_history'),
    path('lich-su-bao-cao/xoa/<int:report_id>/', views.delete_report, name='delete_report'),
    # Notifications
    path('notifications/', views.notifications_center, name='notifications_center'),
    path('notifications/go/<int:notif_id>/', views.notification_go, name='notification_go'),
    path('notifications/mark-all-read/', views.notifications_mark_all_read, name='notifications_mark_all_read'),
    path('notifications/delete/<int:notif_id>/', views.notification_delete, name='notification_delete'),
    path('notifications/delete-all/', views.notifications_delete_all, name='notifications_delete_all'),

    # Interactive Map
    path('map/', map_view, name='map_view'),
    path('api/map/posts/', map_data_api, name='map_data_api'),
    path('api/map/pois/', poi_data_api, name='poi_data_api'),
    path('api/map/post/<int:post_id>/nearby-pois/', nearby_pois_api, name='nearby_pois_api'),
]

