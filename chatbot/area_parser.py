"""
DEPRECATED: area_parser utilities are not used by the current chatbot.
Kept as a stub to prevent accidental imports. Safe to delete.
"""

raise RuntimeError("Deprecated/unused chatbot script: area_parser.py (safe to delete)")

# Temporary file for area parsing logic
import re

def parse_area_from_text(message: str):
    """Parse diện tích từ câu. Trả về (min_area, max_area, exact_area).
    Hỗ trợ: 'trên 90m²', 'dưới 50m²', '30-50m²', 'khoảng 40m²'"""
    text = message.lower()
    text = text.replace('m2', 'm²').replace('met vuong', 'm²').replace('mét vuông', 'm²')

    # Khoảng: 30-50m², 30 đến 50m²
    range_pattern = r"(\d+[\.,]?\d*)\s*(đến|toi|tới|->|–|-|~)\s*(\d+[\.,]?\d*)\s*m"
    m = re.search(range_pattern, text)
    if m:
        n1, _, n2 = m.group(1), m.group(2), m.group(3)
        try:
            v1, v2 = float(n1.replace(',', '.')), float(n2.replace(',', '.'))
            return (min(v1, v2), max(v1, v2), None)
        except:
            pass

    # Trên X: trên 90m², từ 50m²
    above_pattern = r"(trên|từ|tu|>|>=)\s*(\d+[\.,]?\d*)\s*m"
    m2 = re.search(above_pattern, text)
    if m2:
        try:
            val = float(m2.group(2).replace(',', '.'))
            return (val, None, None)  # min only
        except:
            pass

    # Dưới X: dưới 50m², tối đa 30m²
    below_pattern = r"(dưới|duoi|tối đa|toi da|<|<=)\s*(\d+[\.,]?\d*)\s*m"
    m3 = re.search(below_pattern, text)
    if m3:
        try:
            val = float(m3.group(2).replace(',', '.'))
            return (None, val, None)  # max only
        except:
            pass

    # Exact: khoảng 40m², diện tích 35m²
    exact_pattern = r"(khoảng|diện tích|dien tich|dt|=|là)\s*(\d+[\.,]?\d*)\s*m"
    m4 = re.search(exact_pattern, text)
    if m4:
        try:
            val = float(m4.group(2).replace(',', '.'))
            tolerance = val * 0.1  # ±10%
            return (val - tolerance, val + tolerance, val)
        except:
            pass

    # Fallback: "diện tích trên 90" không có m²
    if 'diện tích' in text or 'dien tich' in text:
        above_no_m = re.search(r"(trên|tu|từ)\s*(\d+)", text)
        if above_no_m:
            try:
                val = float(above_no_m.group(2))
                return (val, None, None)
            except:
                pass

    return (None, None, None)

# Test
if __name__ == "__main__":
    test_cases = [
        "tìm phòng có diện tích trên 90m²",
        "phòng diện tích 30-50m²",
        "dưới 25m²",
        "khoảng 40m²"
    ]
    for tc in test_cases:
        result = parse_area_from_text(tc)
        print(f"{tc} → {result}")
