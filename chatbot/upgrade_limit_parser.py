"""
DEPRECATED: upgrade_limit_parser utilities are not used by the current chatbot.
Safe to delete.
"""

raise RuntimeError("Deprecated/unused chatbot script: upgrade_limit_parser.py (safe to delete)")

#!/usr/bin/env python
"""Add quantity parsing to chatbot - user can specify how many rooms to show"""

file_path = r'd:\WEBPYTHON\PHONGTRO\chatbot\views.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check if already patched
if 'def parse_quantity_from_text' in content:
    print("✅ Chatbot đã có quantity parsing rồi!")
    exit(0)

# Find insertion point after parse_area_from_text
insertion_marker = "def number_to_vnd(num_str: str, unit: str | None) -> int | None:"
insertion_point = content.find(insertion_marker)

if insertion_point == -1:
    print("❌ Không tìm thấy điểm chèn!")
    exit(1)

# Code to insert
quantity_parser = '''

def parse_quantity_from_text(message: str) -> int:
    """Parse số lượng phòng muốn hiển thị từ câu.
    Hỗ trợ: 'tìm 1 phòng', 'tìm 3 căn', 'cho tôi xem 5 phòng', 'tìm các' (=all=5)
    Default: 5"""
    text = message.lower()

    # Pattern: "tìm 3 phòng", "cho tôi 2 căn", "xem 4 phòng"
    patterns = [
        r'tìm\s+(\d+)\s*(phòng|căn|cái)',
        r'tim\s+(\d+)\s*(phong|can|cai)',
        r'cho\s+(tôi|toi)\s+(xem)?\s*(\d+)',
        r'xem\s+(\d+)\s*(phòng|căn)',
        r'hiển thị\s+(\d+)',
        r'hien thi\s+(\d+)',
        r'(\d+)\s+phòng',
        r'(\d+)\s+căn',
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                # Lấy số từ group cuối cùng có chữ số
                for group in m.groups():
                    if group and group.isdigit():
                        num = int(group)
                        # Giới hạn từ 1-10
                        return max(1, min(num, 10))
            except:
                pass

    # Nếu có "các", "tất cả", "hết" → hiển thị nhiều (5)
    if any(word in text for word in ['các', 'cac', 'tất cả', 'tat ca', 'hết', 'het', 'all']):
        return 5

    # Default: 1 nếu có "tìm", "cho tôi", không thì 5
    if any(word in text for word in ['tìm', 'tim', 'cho toi', 'cho tôi']):
        return 1

    return 5


'''

# Insert before number_to_vnd
new_content = content[:insertion_point] + quantity_parser + content[insertion_point:]

# Update advanced_room_search to use quantity
old_limit = "        # Sort và lấy kết quả\n        rooms = list(qs.order_by('-created_at')[:5])"
new_limit = "        # Parse số lượng muốn hiển thị\n        limit = parse_quantity_from_text(message)\n        \n        # Sort và lấy kết quả\n        rooms = list(qs.order_by('-created_at')[:limit])"

new_content = new_content.replace(old_limit, new_limit)

# Update result header to show dynamic count
old_header = '        result = [f"🔍 **Tìm thấy {len(rooms)} phòng trọ {header}:**\\n"]'
new_header = '        count_text = f"{len(rooms)}/{limit}" if limit < 10 else f"{len(rooms)}"\n        result = [f"🔍 **Tìm thấy {count_text} phòng trọ {header}:**\\n"]'

new_content = new_content.replace(old_header, new_header)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ Đã nâng cấp chatbot với quantity parsing!")
print("\n📝 Tính năng mới:")
print("  • 'tìm 1 phòng' → hiển thị 1 phòng")
print("  • 'tìm 3 căn hộ mini' → hiển thị 3 phòng")
print("  • 'cho tôi xem 5 phòng' → hiển thị 5 phòng")
print("  • 'tìm các căn hộ' → hiển thị 5 phòng")
print("  • Default: 1 phòng nếu có 'tìm', 5 nếu không")
