"""Quick test for specific queries"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PhongTro.settings')
django.setup()

from chatbot.views import parse_area_from_text

# Test area parsing
test_cases = [
    "tim nha 23 m vuong",
    "phong 23m vuong",
    "dien tich 23 met vuong",
]

print("Test area parsing:")
for text in test_cases:
    min_a, max_a, exact_a = parse_area_from_text(text)
    print(f"  '{text}' -> min={min_a}, max={max_a}, exact={exact_a}")
