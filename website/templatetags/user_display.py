"""
Template tags để hiển thị tên người dùng
"""
from django import template

register = template.Library()


@register.filter
def display_name(user):
    """
    Trả về tên hiển thị của user.
    Ưu tiên: display_name > first_name > username
    Không dùng last_name để tránh hiển thị thừa thông tin.
    """
    if not user:
        return "Ẩn danh"

    # Ưu tiên display_name nếu có CustomerProfile
    if hasattr(user, 'customerprofile') and user.customerprofile.display_name:
        return user.customerprofile.display_name

    # Sau đó dùng first_name (không kèm last_name)
    if user.first_name:
        return user.first_name

    # Cuối cùng fallback về username
    return user.username
