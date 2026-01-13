from django.core.management.base import BaseCommand
from django.conf import settings
from website.models import Province, District, Ward
import json
import os

class Command(BaseCommand):
    help = 'Load location data from vn_admin.json'

    def handle(self, *args, **options):
        json_path = os.path.join(settings.BASE_DIR, 'website', 'static', 'locations', 'vn_admin.json')
        print("JSON path:", json_path)

        with open(json_path, encoding="utf-8") as f:   # ✅ sửa ở đây
            data = json.load(f)
            for province in data['provinces']:
                p, _ = Province.objects.update_or_create(
                    id=province['id'],
                    defaults={'name': province['name']}
                )
                for district in province['districts']:
                    d, _ = District.objects.update_or_create(
                        id=district['id'],
                        defaults={'name': district['name'], 'province': p}
                    )
                    for ward in district['wards']:
                        Ward.objects.update_or_create(
                            id=ward['id'],
                            defaults={'name': ward['name'], 'district': d}
                        )
        self.stdout.write(self.style.SUCCESS('Successfully loaded location data'))
