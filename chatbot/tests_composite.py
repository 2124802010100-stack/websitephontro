from django.test import TestCase
from django.contrib.auth.models import User
from website.models import RentalPost, Province, District, Ward
from chatbot.grop_service import GropChatbot

class CompositeFilterExplanationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create(username="owner_cf")
        cls.prov = Province.objects.create(name="Hà Nội")
        cls.dist = District.objects.create(name="Quận Hoàn Kiếm", province=cls.prov)
        cls.ward = Ward.objects.create(name="Phường Hàng Trống", district=cls.dist)

    def setUp(self):
        # Bypass Grop API init
        self._orig_init = GropChatbot.__init__
        GropChatbot.__init__ = lambda self: None

    def tearDown(self):
        GropChatbot.__init__ = self._orig_init

    def _mk(self, title, price_million, area, category='canho_mini'):
        return RentalPost.objects.create(
            user=self.owner,
            title=title,
            description="desc",
            price=price_million,  # stored as 'triệu style'
            area=area,
            province=self.prov,
            district=self.dist,
            ward=self.ward,
            address="Địa chỉ X",
            is_approved=True,
            is_deleted=False,
            category=category,
        )

    def test_composite_price_area_category_explanation(self):
        # Matching post (~6 triệu, ~10m²)
        match = self._mk("Mini chuẩn", 6, 10)
        # Price ok, area wrong
        self._mk("Mini sai diện tích", 6, 20)
        # Area ok, price wrong
        self._mk("Mini sai giá", 8, 10)
        # Different category
        self._mk("Khác loại", 6, 10, category='phongtro')

        bot = GropChatbot()
        query = "tìm 1 căn hộ mini giá 6 triệu diện tích 10m² ở Hà Nội"
        resp = bot._direct_answer_if_applicable(query)
        self.assertIsNotNone(resp)
        # Should contain detail block for matching post
        self.assertIn("Mini chuẩn", resp)
        self.assertNotIn("Mini sai diện tích", resp)
        self.assertNotIn("Mini sai giá", resp)
        self.assertNotIn("Khác loại", resp)
        # Explanation line present
        self.assertIn("ℹ️ Lọc áp dụng", resp)
        self.assertIn("giá ≈6 triệu", resp)
        self.assertIn("diện tích", resp)
        self.assertIn("10m²", resp)
        # label mapping from code to verbose choice
        self.assertIn("loại=Cho thuê căn hộ mini", resp)
        self.assertIn("khu vực=Hà Nội", resp)

    def test_price_range_and_area_explanation(self):
        # Create posts spanning price range 5-7 triệu and area around 12m²
        self._mk("Mini 5tr 12m2", 5, 12)
        self._mk("Mini 6tr 11m2", 6, 11)
        self._mk("Mini 7tr 13m2", 7, 13)
        # Out of area tolerance
        self._mk("Mini 6tr 25m2", 6, 25)

        bot = GropChatbot()
        query = "tìm căn hộ mini giá 5-7 triệu diện tích khoảng 12m² ở Hà Nội"
        resp = bot._direct_answer_if_applicable(query)
        self.assertIsNotNone(resp)
        self.assertIn("ℹ️ Lọc áp dụng", resp)
        self.assertIn("giá 5-7 triệu", resp)
        # area may be interpreted as exact (≈) or range depending on parser; check presence
        self.assertIn("diện tích", resp)
        self.assertIn("12m²", resp)
        # Ensure out-of-area post excluded
        self.assertNotIn("25m2", resp)

    def test_min_price_with_area_filter(self):
        self._mk("Mini 9tr 18m2", 9, 18)
        self._mk("Mini 10tr 20m2", 10, 20)
        self._mk("Mini 11tr 20m2", 11, 20)
        # Area mismatch
        self._mk("Mini 12tr 40m2", 12, 40)

        bot = GropChatbot()
        query = "căn hộ mini giá trên 10 triệu diện tích 20m² Hà Nội"
        resp = bot._direct_answer_if_applicable(query)
        self.assertIsNotNone(resp)
        self.assertIn("ℹ️ Lọc áp dụng", resp)
        self.assertIn("giá từ", resp)
        self.assertIn("diện tích", resp)
        self.assertIn("20m²", resp)
        self.assertNotIn("40m2", resp)

