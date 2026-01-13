"""
Django Admin cho hệ thống gợi ý AI
"""
from django.contrib import admin
from .models import PostView, SearchHistory, UserInteraction, RecommendationLog


@admin.register(PostView)
class PostViewAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'post', 'viewed_at', 'duration', 'ip_address')
    list_filter = ('viewed_at',)
    search_fields = ('user__username', 'post__title', 'session_id', 'ip_address')
    raw_id_fields = ('user', 'post')
    date_hierarchy = 'viewed_at'
    ordering = ('-viewed_at',)

    def has_add_permission(self, request):
        return False  # Chỉ đọc, không cho thêm manual


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'query', 'category', 'province', 'searched_at', 'results_count')
    list_filter = ('searched_at', 'category', 'province')
    search_fields = ('user__username', 'query', 'session_id')
    raw_id_fields = ('user', 'province', 'district')
    date_hierarchy = 'searched_at'
    ordering = ('-searched_at',)

    def has_add_permission(self, request):
        return False


@admin.register(UserInteraction)
class UserInteractionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'post', 'interaction_type', 'created_at', 'weight_display')
    list_filter = ('interaction_type', 'created_at')
    search_fields = ('user__username', 'post__title', 'session_id')
    raw_id_fields = ('user', 'post')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    def weight_display(self, obj):
        return f"{obj.weight:.1f}"
    weight_display.short_description = 'Trọng số'

    def has_add_permission(self, request):
        return False


@admin.register(RecommendationLog)
class RecommendationLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'algorithm_used', 'created_at', 'post_count', 'conversion_rate')
    list_filter = ('algorithm_used', 'created_at')
    search_fields = ('user__username', 'session_id')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    def post_count(self, obj):
        return len(obj.recommended_posts)
    post_count.short_description = 'Số bài gợi ý'

    def has_add_permission(self, request):
        return False
