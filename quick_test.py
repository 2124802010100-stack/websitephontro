#!/usr/bin/env python
"""Quick test for listing queries"""
import os
import django
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PhongTro.settings')
django.setup()

from chatbot.grop_service import get_grop_chatbot
from website.models import RentalPost

bot = get_grop_chatbot()

tests = [
    ('cho xem ở ghép ở Bình Dương', 'oghep'),
    ('cho xem mặt bằng ở Bình Dương', 'matbang'),
]

print("=" * 80)
for query, expected_slug in tests:
    print(f"\n🔍 {query}")
    response = bot.get_response(query)

    # Extract IDs
    ids = re.findall(r'\(ID:(\d+)\)', response)
    print(f"   Found {len(ids)} posts: {ids}")

    # Verify each
    for pid in ids:
        p = RentalPost.objects.get(id=pid)
        cat_ok = '✅' if p.category == expected_slug else '❌'
        prov_ok = '✅' if p.province and 'Bình Dương' in p.province.name else '❌'
        print(f"   {cat_ok} {prov_ok} ID {pid}: cat={p.category}, prov={p.province.name if p.province else 'None'}")
print("\n" + "=" * 80)
