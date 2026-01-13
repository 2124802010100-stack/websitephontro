from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from website.models import RentalPost, Province, District, Ward, RentalRequest
from chatbot.grop_service import GropChatbot


class GropDeterministicIntentsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Owner and customer users
        cls.owner = User.objects.create(username="owner1")
        cls.customer = User.objects.create(username="customer1")
        # Location
        cls.prov = Province.objects.create(name="Hồ Chí Minh")
        cls.dist = District.objects.create(name="Quận 1", province=cls.prov)
        cls.ward = Ward.objects.create(name="Phường Bến Nghé", district=cls.dist)

    def _mk_post(self, title: str, price: int, area: float = 20.0, created_at=None):
        p = RentalPost.objects.create(
            user=self.owner,
            title=title,
            description="desc",
            price=price,  # stored as 'triệu' style per project
            area=area,
            province=self.prov,
            district=self.dist,
            ward=self.ward,
            address="123 Đường A",
            is_approved=True,
            is_deleted=False,
            category='phongtro',
        )
        if created_at:
            # Force created_at ordering by updating field directly
            RentalPost.objects.filter(id=p.id).update(created_at=created_at)
            p.refresh_from_db()
        return p

    def _mk_requests(self, post: RentalPost, n: int, hours_ago: int = 1):
        when = timezone.now() - timezone.timedelta(hours=hours_ago)
        for _ in range(n):
            rr = RentalRequest.objects.create(customer=self.customer, post=post, status='pending')
            # Backdate a bit but keep within 24h window
            RentalRequest.objects.filter(id=rr.id).update(created_at=when)

    def setUp(self):
        # Monkeypatch GropChatbot.__init__ to avoid requiring API client init
        self._orig_init = GropChatbot.__init__
        GropChatbot.__init__ = lambda self: None

    def tearDown(self):
        GropChatbot.__init__ = self._orig_init

    def test_quota_cooldown_fallback(self):
        """Simulate quota cooldown and ensure fallback response is returned immediately."""
        # Access module-level globals to simulate quota exhaustion
        import chatbot.grop_service as gs
        gs._LAST_QUOTA_EXHAUSTED_AT = timezone.now().timestamp()  # just occurred
        # Build bot and call _call_grop_with_retry directly with a minimal prompt
        bot = GropChatbot()
        # Monkeypatch client.chat.completions.create to ensure it would succeed (but should be skipped due to cooldown)
        class DummyResponse:
            def __init__(self):
                self.usage = None
                self.choices = []

        class DummyCompletions:
            def create(self, *args, **kwargs):
                return DummyResponse()

        class DummyChat:
            def __init__(self):
                self.completions = DummyCompletions()

        class DummyClient:
            def __init__(self):
                self.chat = DummyChat()

        bot.client = DummyClient()
        resp = bot._call_grop_with_retry("test prompt")
        self.assertIn("Xin lỗi, AI chatbot tạm thời gặp vấn đề", resp)
        # Cleanup
        gs._LAST_QUOTA_EXHAUSTED_AT = None

    def test_most_expensive_ordering_and_visibility(self):
        # One visible expensive, one visible cheap, one expired (should not show)
        self._mk_post("Đắt", price=15)
        self._mk_post("Rẻ", price=10)
        expired = self._mk_post("Hết hạn nhưng đắt", price=20)
        # Mark expired post
        from website.models import RentalPost
        from django.utils import timezone
        RentalPost.objects.filter(id=expired.id).update(expired_at=timezone.now() - timezone.timedelta(days=1))

        bot = GropChatbot()
        resp = bot._direct_answer_if_applicable("cho mình 3 phòng đắt nhất")

        self.assertIsNotNone(resp)
        self.assertIn("ĐẮT NHẤT", resp)
        # Expired '20 triệu' should not appear
        self.assertNotIn("20 triệu", resp)
        # 15 should appear before 10
        self.assertLess(resp.find("15 triệu"), resp.find("10 triệu"))

    def test_newest_ordering(self):
        # Older first
        self._mk_post("Cũ", price=8, created_at=timezone.now() - timezone.timedelta(days=2))
        self._mk_post("Mới", price=9, created_at=timezone.now())

        bot = GropChatbot()
        resp = bot._direct_answer_if_applicable("liệt kê 2 phòng mới nhất ở Hồ Chí Minh")
        self.assertIsNotNone(resp)
        self.assertIn("MỚI NHẤT", resp)
        self.assertLess(resp.find("Mới"), resp.find("Cũ"))
        # No deeplink expected
        self.assertNotIn("/phong-tro/", resp)

    def test_requests_24h_popularity(self):
        p1 = self._mk_post("Nhiều yêu cầu", price=7)
        p2 = self._mk_post("Ít yêu cầu", price=7)
        self._mk_requests(p1, 5, hours_ago=2)
        self._mk_requests(p2, 2, hours_ago=2)

        bot = GropChatbot()
        resp = bot._direct_answer_if_applicable("phòng nào nhiều yêu cầu 24h qua")
        self.assertIsNotNone(resp)
        self.assertIn("24h", resp)
        self.assertLess(resp.find("Nhiều yêu cầu"), resp.find("Ít yêu cầu"))

    def test_price_intent_exact_with_deeplink_price_range(self):
        # Create posts around 10 triệu
        self._mk_post("Đúng 10", price=10)
        self._mk_post("Khoảng 10.1", price=10)

        bot = GropChatbot()
        resp = bot._direct_answer_if_applicable("tìm phòng giá 10 triệu ở Hồ Chí Minh")
        self.assertIsNotNone(resp)
        self.assertIn("giá 10 triệu/tháng", resp)
        # No deeplink expected anymore
        self.assertNotIn("/phong-tro/", resp)

    def test_price_intent_respects_quantity_one(self):
        # Three posts at ~11 triệu; request '1' should return only one detail card
        self._mk_post("P1", price=11)
        self._mk_post("P2", price=11)
        self._mk_post("P3", price=11)

        bot = GropChatbot()
        resp = bot._direct_answer_if_applicable("tìm 1 căn hộ mini giá 11 triệu nhé bạn")
        self.assertIsNotNone(resp)
        # Expect a detail block (starts with **Title** line) rather than a numbered list
        self.assertTrue(resp.strip().startswith("**"))
        # Should not include numbering for list items like '2.' or '3.'
        self.assertNotIn("\n2.", resp)
        self.assertNotIn("\n3.", resp)

    def test_price_min_threshold_and_category_apartment(self):
        # Create mix of categories and prices
        # Apartment >= 10
        apt_ok = self._mk_post("CHCC 12tr", price=12)
        # Apartment below threshold (should be excluded)
        apt_low = self._mk_post("CHCC 9tr", price=9)
        # Non-apartment above threshold (should be excluded by category)
        non_apt = self._mk_post("Phòng trọ 15tr", price=15)
        # Adjust categories accordingly
        from website.models import RentalPost
        RentalPost.objects.filter(id=apt_ok.id).update(category='canho')
        RentalPost.objects.filter(id=apt_low.id).update(category='canho')
        RentalPost.objects.filter(id=non_apt.id).update(category='phongtro')

        bot = GropChatbot()
        resp = bot._direct_answer_if_applicable("tìm 1 căn hộ chung cư giá trên 10 triệu")
        self.assertIsNotNone(resp)
        # Expect a detail block for the 12tr apartment
        self.assertTrue(resp.strip().startswith("**"))
        self.assertIn("12 triệu", resp)
        self.assertNotIn("15 triệu", resp)
        self.assertNotIn("9 triệu", resp)

    def test_category_detection_specificity(self):
        # Test category từ cụ thể → tổng quát
        bot = GropChatbot()

        # Căn hộ mini (cụ thể)
        self.assertEqual(bot._detect_category("tìm căn hộ mini"), 'canho_mini')
        self.assertEqual(bot._detect_category("studio giá rẻ"), 'canho_mini')

        # Căn hộ dịch vụ (cụ thể)
        self.assertEqual(bot._detect_category("căn hộ dịch vụ gần trung tâm"), 'canho_dichvu')

        # Căn hộ chung cư (tổng quát)
        self.assertEqual(bot._detect_category("căn hộ chung cư"), 'canho')
        self.assertEqual(bot._detect_category("chung cư"), 'canho')

        # Phòng trọ
        self.assertEqual(bot._detect_category("phòng trọ gần đại học"), 'phongtro')

        # Nhà nguyên căn
        self.assertEqual(bot._detect_category("nhà nguyên căn 3 tầng"), 'nhanguyencan')

        # Ở ghép
        self.assertEqual(bot._detect_category("tìm người ở ghép"), 'oghep')

        # Mặt bằng
        self.assertEqual(bot._detect_category("cho thuê mặt bằng kinh doanh"), 'matbang')

    def test_feature_detection_comprehensive(self):
        bot = GropChatbot()

        # Máy lạnh
        feats = bot._detect_features("phòng có máy lạnh")
        self.assertIn('co_may_lanh', feats)

        # Thang máy
        feats = bot._detect_features("chung cư có thang máy")
        self.assertIn('co_thang_may', feats)

        # Bảo vệ 24/24
        feats = bot._detect_features("có bảo vệ 24/24")
        self.assertIn('bao_ve_24_24', feats)

        # Nhiều feature cùng lúc - test với input đã normalize
        feats = bot._detect_features("can ho day du noi that co may lanh tu lanh khong chung chu")
        self.assertIn('day_du_noi_that', feats)
        self.assertIn('co_may_lanh', feats)
        self.assertIn('co_tu_lanh', feats)
        self.assertIn('khong_chung_chu', feats)

    def test_area_threshold_intent(self):
        # Create posts with different areas
        self._mk_post("Nhỏ 15m²", price=5, area=15)
        self._mk_post("Vừa 25m²", price=7, area=25)
        big = self._mk_post("Lớn 40m²", price=10, area=40)

        bot = GropChatbot()

        # Test "trên 30m²"
        resp = bot._direct_answer_if_applicable("tìm phòng trên 30m²")
        self.assertIsNotNone(resp)
        self.assertIn("40", resp)  # Should include 40m² post
        self.assertNotIn("15", resp)  # Should not include smaller ones

        # Test "dưới 20m²"
        resp = bot._direct_answer_if_applicable("tìm phòng dưới 20m²")
        self.assertIsNotNone(resp)
        self.assertIn("15", resp)
        self.assertNotIn("40", resp)

    def test_price_area_separation(self):
        # Ensure price and area parsing don't conflict
        bot = GropChatbot()

        # "10 triệu" should parse as price, not area
        price_parsed = bot._parse_price_million("phòng giá 10 triệu")
        self.assertIsNotNone(price_parsed)
        self.assertEqual(price_parsed[0], 10)

        # "20m²" should parse as area, not price
        area_parsed = bot._parse_area_range("phòng 20m²")
        self.assertIsNotNone(area_parsed)
        self.assertEqual(area_parsed[0], 20)

    def test_price_range_with_category_strict(self):
        """Ensure query 'căn hộ mini giá trên 8 và dưới 11' returns only mini apt in range, no category fallback."""
        # Create posts
        p_ok = self._mk_post("Mini 9tr", price=9)
        p_hi = self._mk_post("Mini 12tr", price=12)
        p_other_cat = self._mk_post("Nhà 9tr", price=9)
        # Adjust categories
        from website.models import RentalPost
        RentalPost.objects.filter(id=p_ok.id).update(category='canho_mini')
        RentalPost.objects.filter(id=p_hi.id).update(category='canho_mini')
        RentalPost.objects.filter(id=p_other_cat.id).update(category='nhanguyencan')

        bot = GropChatbot()
        resp = bot._direct_answer_if_applicable("tìm 1 căn hộ mini giá trên 8 triệu và dưới 11 triệu")
        self.assertIsNotNone(resp)
        # Should return detail of the 9tr mini apartment
        self.assertTrue(resp.strip().startswith("**"))
        self.assertIn("9 triệu", resp)
        # Must not include 12tr (out of range) or any 'nhà nguyên căn'
        self.assertNotIn("12 triệu", resp)
        self.assertNotIn("Nhà 9tr", resp)

        # Mixed: "10 triệu 20m²" should parse both correctly
        price_parsed = bot._parse_price_million("phòng giá 10 triệu diện tích 20m²")
        area_parsed = bot._parse_area_range("phòng giá 10 triệu diện tích 20m²")
        self.assertIsNotNone(price_parsed)
        self.assertIsNotNone(area_parsed)
        self.assertEqual(price_parsed[0], 10)
        self.assertEqual(area_parsed[0], 20)
