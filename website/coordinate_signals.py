"""
Signal để tự động gán tọa độ cho RentalPost khi được tạo hoặc cập nhật
"""

# Mapping tọa độ chính xác cho các quận/huyện/thành phố
DISTRICT_COORDS = {
    # TP.HCM
    'Quận 1': (10.7756, 106.7019),
    'Quận 2': (10.7899, 106.7532),
    'Quận 3': (10.7828, 106.6908),
    'Quận 4': (10.7598, 106.7031),
    'Quận 5': (10.7546, 106.6677),
    'Quận 6': (10.7476, 106.6345),
    'Quận 7': (10.7332, 106.7221),
    'Quận 8': (10.7382, 106.6768),
    'Quận 9': (10.8495, 106.7894),
    'Quận 10': (10.7727, 106.6673),
    'Quận 11': (10.7622, 106.6503),
    'Quận 12': (10.8633, 106.6701),
    'Quận Bình Thạnh': (10.8098, 106.7129),
    'Quận Gò Vấp': (10.8376, 106.6765),
    'Quận Phú Nhuận': (10.7980, 106.6833),
    'Quận Tân Bình': (10.8009, 106.6525),
    'Quận Tân Phú': (10.7874, 106.6281),
    'Quận Bình Tân': (10.7503, 106.6086),
    'Quận Thủ Đức': (10.8509, 106.7624),
    'Huyện Bình Chánh': (10.6886, 106.5898),
    'Huyện Củ Chi': (10.9743, 106.4925),
    'Huyện Hóc Môn': (10.8835, 106.5913),
    'Huyện Nhà Bè': (10.6948, 106.7314),
    'Huyện Cần Giờ': (10.4086, 106.9575),
    'Thành phố Thủ Đức': (10.8509, 106.7624),

    # Bình Dương
    'Thành phố Thủ Dầu Một': (10.9804, 106.6519),
    'Thành phố Dĩ An': (10.9067, 106.7644),
    'Thành phố Thuận An': (10.9123, 106.7077),
    'Thị xã Tân Uyên': (11.0833, 106.7167),
    'Thị xã Bến Cát': (11.1545, 106.5960),
    'Huyện Bàu Bàng': (11.3167, 106.5833),
    'Huyện Dầu Tiếng': (11.2967, 106.4358),
    'Huyện Bắc Tân Uyên': (11.1667, 106.6333),
    'Huyện Phú Giáo': (11.1167, 106.5833),

    # Đồng Nai
    'Thành phố Biên Hòa': (10.9510, 106.8230),
    'Thành phố Long Khánh': (10.9467, 107.2231),
    'Huyện Long Thành': (10.7333, 107.0167),
    'Huyện Nhơn Trạch': (10.6833, 106.8500),
    'Huyện Trảng Bom': (10.9167, 107.0167),
    'Huyện Vĩnh Cửu': (10.7667, 107.1500),
    'Huyện Định Quán': (11.1333, 107.3667),
    'Huyện Tân Phú': (11.0667, 107.4333),
    'Huyện Thống Nhất': (10.9833, 106.9667),
    'Huyện Cẩm Mỹ': (10.8500, 107.2833),
    'Huyện Xuân Lộc': (10.9333, 107.4167),

    # Hà Nội
    'Quận Ba Đình': (21.0333, 105.8197),
    'Quận Hoàn Kiếm': (21.0283, 105.8521),
    'Quận Tây Hồ': (21.0724, 105.8194),
    'Quận Long Biên': (21.0364, 105.8938),
    'Quận Cầu Giấy': (21.0333, 105.7944),
    'Quận Đống Đa': (21.0167, 105.8272),
    'Quận Hai Bà Trưng': (21.0069, 105.8550),
    'Quận Hoàng Mai': (20.9817, 105.8469),
    'Quận Thanh Xuân': (20.9950, 105.8053),
    'Quận Nam Từ Liêm': (21.0333, 105.7500),
    'Quận Bắc Từ Liêm': (21.0667, 105.7667),
    'Quận Hà Đông': (20.9667, 105.7667),
    'Thị xã Sơn Tây': (21.1389, 105.5050),
    'Huyện Ba Vì': (21.2500, 105.3833),
    'Huyện Phúc Thọ': (21.0833, 105.5667),
    'Huyện Đan Phượng': (21.0667, 105.6500),
    'Huyện Hoài Đức': (21.0167, 105.6833),
    'Huyện Quốc Oai': (21.0167, 105.6167),
    'Huyện Thạch Thất': (21.0500, 105.5500),
    'Huyện Chương Mỹ': (20.8833, 105.6167),
    'Huyện Thanh Oai': (20.8500, 105.7667),
    'Huyện Thường Tín': (20.8667, 105.8667),
    'Huyện Phú Xuyên': (20.7333, 105.9167),
    'Huyện Ứng Hòa': (20.7333, 105.7667),
    'Huyện Mỹ Đức': (20.6667, 105.7167),
    'Huyện Sóc Sơn': (21.2667, 105.8333),
    'Huyện Đông Anh': (21.1333, 105.8333),
    'Huyện Gia Lâm': (21.0333, 105.9667),
    'Huyện Mê Linh': (21.1833, 105.7167),

    # Đà Nẵng
    'Quận Hải Châu': (16.0471, 108.2208),
    'Quận Thanh Khê': (16.0606, 108.1817),
    'Quận Sơn Trà': (16.0861, 108.2431),
    'Quận Ngũ Hành Sơn': (16.0333, 108.2500),
    'Quận Liên Chiểu': (16.0722, 108.1500),
    'Quận Cẩm Lệ': (16.0167, 108.1833),
    'Huyện Hòa Vang': (16.0667, 108.0833),
    'Huyện Hoàng Sa': (16.0833, 112.3333),

    # Cần Thơ
    'Quận Ninh Kiều': (10.0333, 105.7833),
    'Quận Ô Môn': (10.1167, 105.6167),
    'Quận Bình Thuỷ': (10.0833, 105.7667),
    'Quận Cái Răng': (10.0167, 105.8000),
    'Quận Thốt Nốt': (10.2833, 105.5167),
    'Huyện Vĩnh Thạnh': (10.2500, 105.4833),
    'Huyện Cờ Đỏ': (10.1167, 105.4500),
    'Huyện Phong Điền': (10.0167, 105.6500),
    'Huyện Thới Lai': (10.0167, 105.5833),

    # Hải Phòng
    'Quận Hồng Bàng': (20.8625, 106.6808),
    'Quận Ngô Quyền': (20.8569, 106.6964),
    'Quận Lê Chân': (20.8456, 106.6986),
    'Quận Hải An': (20.8611, 106.7542),
    'Quận Kiến An': (20.8033, 106.6072),
    'Quận Đồ Sơn': (20.7189, 106.7975),
    'Quận Dương Kinh': (20.7764, 106.7014),
    'Huyện An Dương': (20.8833, 106.5833),
    'Huyện An Lão': (20.8667, 106.5667),
    'Huyện Kiến Thuỵ': (20.8500, 106.7167),
    'Huyện Tiên Lãng': (20.7333, 106.5667),
    'Huyện Vĩnh Bảo': (20.7333, 106.6333),
    'Huyện Cát Hải': (20.7333, 107.0167),
    'Huyện Bạch Long Vĩ': (20.1333, 107.7167),
}

# Tọa độ tâm tỉnh - fallback nếu không có tọa độ quận/huyện
PROVINCE_COORDS = {
    'Thành phố Hà Nội': (21.0285, 105.8542),
    'Thành phố Hồ Chí Minh': (10.8231, 106.6297),
    'Thành phố Hải Phòng': (20.8449, 106.6881),
    'Thành phố Đà Nẵng': (16.0544, 108.2022),
    'Thành phố Cần Thơ': (10.0452, 105.7469),
    'Tỉnh Bình Dương': (11.3254, 106.4770),
    'Tỉnh Đồng Nai': (11.0686, 107.1676),
    'Tỉnh Bà Rịa - Vũng Tàu': (10.5417, 107.2430),
    'Tỉnh Long An': (10.6956, 106.2431),
    'Tỉnh Tiền Giang': (10.4493, 106.3420),
    'Tỉnh Bến Tre': (10.2433, 106.3757),
    'Tỉnh Trà Vinh': (9.8127, 106.2992),
    'Tỉnh Vĩnh Long': (10.2397, 105.9722),
    'Tỉnh Đồng Tháp': (10.4938, 105.6881),
    'Tỉnh An Giang': (10.5216, 105.1258),
    'Tỉnh Kiên Giang': (10.0125, 105.0811),
    'Tỉnh Cà Mau': (9.1527, 105.1960),
    'Tỉnh Bạc Liêu': (9.2515, 105.7244),
    'Tỉnh Sóc Trăng': (9.6025, 105.9739),
    'Tỉnh Hậu Giang': (9.7579, 105.6412),
}


def auto_assign_coordinates(sender, instance, **kwargs):
    """
    Tự động gán tọa độ cho bài viết dựa trên quận/huyện hoặc tỉnh/thành
    """
    # Chỉ gán tọa độ nếu chưa có
    if instance.latitude is None or instance.longitude is None:
        district_name = instance.district.name if instance.district else None
        province_name = instance.province.name if instance.province else None

        # Ưu tiên tọa độ quận/huyện
        if district_name and district_name in DISTRICT_COORDS:
            lat, lng = DISTRICT_COORDS[district_name]
            instance.latitude = lat
            instance.longitude = lng
            print(f"✓ Auto-assigned coords for {district_name}: ({lat}, {lng})")
        # Fallback về tọa độ tâm tỉnh
        elif province_name and province_name in PROVINCE_COORDS:
            lat, lng = PROVINCE_COORDS[province_name]
            instance.latitude = lat
            instance.longitude = lng
            print(f"⚠ Auto-assigned province center coords for {province_name}: ({lat}, {lng})")
        else:
            print(f"✗ Cannot auto-assign coords: District={district_name}, Province={province_name}")
