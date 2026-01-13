"""
Management command để sửa các user có username rỗng
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Sửa các user có username rỗng hoặc None'

    def handle(self, *args, **options):
        # Tìm các user có username rỗng hoặc None
        users_with_empty_username = User.objects.filter(
            username__in=['', None]
        ) | User.objects.filter(username__isnull=True)
        
        count = 0
        for user in users_with_empty_username:
            # Tạo username từ email
            if user.email:
                username = user.email.split('@')[0]
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                user.username = username
            else:
                # Nếu không có email, dùng random
                username = f"user_{random.randint(100000, 999999)}"
                while User.objects.filter(username=username).exists():
                    username = f"user_{random.randint(100000, 999999)}"
                user.username = username
            
            user.save(update_fields=['username'])
            count += 1
            self.stdout.write(
                self.style.SUCCESS(f'✅ Đã sửa user ID {user.id}: username = {user.username}')
            )
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ Không có user nào cần sửa')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Đã sửa {count} user(s)')
            )

