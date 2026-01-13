from django.core.management.base import BaseCommand
from website.models import VIPPackageConfig


class Command(BaseCommand):
    help = 'Tạo dữ liệu ban đầu cho các gói VIP'

    def handle(self, *args, **options):
        packages = [
            {
                'plan': 'vip1',
                'name': 'Gói VIP 1',
                'posts_per_day': 5,
                'expire_days': 7,
                'title_color': 'red',
                'price': 500000,
                'stars': 4,
                'is_active': True,
            },
            {
                'plan': 'vip2',
                'name': 'Gói VIP 2',
                'posts_per_day': 3,
                'expire_days': 3,
                'title_color': 'blue',
                'price': 300000,
                'stars': 3,
                'is_active': True,
            },
            {
                'plan': 'vip3',
                'name': 'Gói VIP 3',
                'posts_per_day': 1,
                'expire_days': 2,
                'title_color': 'pink',
                'price': 150000,
                'stars': 2,
                'is_active': True,
            },
        ]

        created_count = 0
        updated_count = 0

        for pkg_data in packages:
            pkg, created = VIPPackageConfig.objects.update_or_create(
                plan=pkg_data['plan'],
                defaults=pkg_data
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✅ Đã tạo {pkg.name}'))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f'⚠️ Đã cập nhật {pkg.name}'))

        self.stdout.write(self.style.SUCCESS(f'\n🎉 Hoàn thành! Tạo mới: {created_count}, Cập nhật: {updated_count}'))
