"""
Django Management Command: Huấn luyện Collaborative Filtering Model (ALS)
Chạy: python manage.py train_cf_model
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Huấn luyện mô hình Collaborative Filtering (ALS) từ UserInteraction data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
                default=1,
                help='Số ngày lịch sử interactions để lấy (default: 1 = 24h)'
        )
        parser.add_argument(
            '--factors',
            type=int,
            default=64,
            help='Số chiều latent factors (default: 64)'
        )
        parser.add_argument(
            '--iterations',
            type=int,
            default=20,
            help='Số vòng lặp huấn luyện (default: 20)'
        )
        parser.add_argument(
            '--alpha',
            type=float,
            default=40.0,
            help='Confidence weight cho implicit feedback (default: 40.0)'
        )
        parser.add_argument(
            '--regularization',
            type=float,
            default=0.01,
            help='L2 regularization (default: 0.01)'
        )
        parser.add_argument(
            '--output',
            type=str,
            default=None,
            help='Đường dẫn file output (default: goiy_ai/ml_models/trained_models/cf_als_model.pkl)'
        )

    def handle(self, *args, **options):
        from goiy_ai.ml_models.cf_als import ALSRecommender

        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('  HUẤN LUYỆN COLLABORATIVE FILTERING MODEL (ALS)'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))

        # Khởi tạo recommender
        recommender = ALSRecommender()

        # Tham số
        days = options['days']
        factors = options['factors']
        iterations = options['iterations']
        alpha = options['alpha']
        regularization = options['regularization']

        self.stdout.write(f"📋 Tham số huấn luyện:")
        self.stdout.write(f"   - Lịch sử: {days} ngày gần nhất")
        self.stdout.write(f"   - Latent factors: {factors}")
        self.stdout.write(f"   - Iterations: {iterations}")
        self.stdout.write(f"   - Alpha (confidence): {alpha}")
        self.stdout.write(f"   - Regularization: {regularization}\n")

        try:
            # Bước 1: Xây ma trận
            self.stdout.write(self.style.WARNING('Bước 1: Xây dựng ma trận user×item...'))
            recommender.build_interaction_matrix(days=days)

            # Kiểm tra ma trận có đủ dữ liệu không
            if recommender.user_item_matrix.nnz < 10:
                self.stdout.write(self.style.ERROR(
                    '\n❌ Không đủ dữ liệu để huấn luyện! '
                    'Cần ít nhất 10 interactions.\n'
                    'Hãy đảm bảo có UserInteraction data trong DB.\n'
                ))
                return

            # Bước 2: Huấn luyện
            self.stdout.write(self.style.WARNING('\nBước 2: Huấn luyện ALS model...'))
            recommender.train(
                factors=factors,
                regularization=regularization,
                iterations=iterations,
                alpha=alpha
            )

            # Bước 3: Lưu model
            if options['output']:
                output_path = options['output']
            else:
                # Default path
                models_dir = os.path.join(
                    settings.BASE_DIR,
                    'goiy_ai',
                    'ml_models',
                    'trained_models'
                )
                os.makedirs(models_dir, exist_ok=True)
                output_path = os.path.join(models_dir, 'cf_als_model.pkl')

            self.stdout.write(self.style.WARNING(f'\nBước 3: Lưu model...'))
            recommender.save_model(output_path)

            # Thành công
            self.stdout.write(self.style.SUCCESS('\n' + '='*60))
            self.stdout.write(self.style.SUCCESS('  ✅ HUẤN LUYỆN THÀNH CÔNG!'))
            self.stdout.write(self.style.SUCCESS('='*60))
            self.stdout.write(self.style.SUCCESS(f'\n📂 Model đã lưu tại: {output_path}\n'))

            # Hướng dẫn sử dụng
            self.stdout.write(self.style.WARNING('📖 Cách sử dụng model:'))
            self.stdout.write('   1. Trong code Python:')
            self.stdout.write('      from goiy_ai.ml_models.cf_als import ALSRecommender')
            self.stdout.write(f'      recommender = ALSRecommender(model_path="{output_path}")')
            self.stdout.write('      posts = recommender.get_recommendations(user=request.user, limit=10)')
            self.stdout.write('')
            self.stdout.write('   2. Tích hợp vào Hybrid:')
            self.stdout.write('      Xem file goiy_ai/ml_models/hybrid.py\n')

        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Lỗi import: {e}'))
            self.stdout.write(self.style.WARNING(
                '\n💡 Cài đặt thư viện cần thiết:\n'
                '   pip install implicit numpy scipy\n'
                'Nếu lỗi C++ compiler trên Windows:\n'
                '   pip install implicit --only-binary :all:\n'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Lỗi: {e}'))
            import traceback
            self.stdout.write(traceback.format_exc())
