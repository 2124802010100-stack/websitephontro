from django.urls import reverse
from django.utils import timezone
from .models import Notification


def notify(user, type_, title, message="", url="", post=None, rental_request=None, transaction=None):
    try:
        Notification.objects.create(
            user=user,
            type=type_,
            title=title[:200],
            message=message or "",
            url=url or "",
            post=post,
            rental_request=rental_request,
            transaction=transaction,
        )
    except Exception:
        # Fail silently to avoid breaking main flow
        pass


def url_for_post(post):
    try:
        return reverse('post_detail', args=[post.id])
    except Exception:
        return '/'


def url_for_thread(thread):
    try:
        return reverse('chat_thread', args=[thread.id])
    except Exception:
        return reverse('my_chats')


def url_for_my_rooms():
    try:
        return reverse('my_rooms')
    except Exception:
        return '/'
