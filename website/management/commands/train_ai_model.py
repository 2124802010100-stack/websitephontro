from django.core.management.base import BaseCommand
from website.ai_moderation.content_moderator import ContentModerator

class Command(BaseCommand):
    help = 'Train AI content moderation model từ dữ liệu đã duyệt/từ chối'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force retrain even if model exists',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('🚀 Bắt đầu train AI model...'))

        try:
            moderator = ContentModerator()
            accuracy = moderator.train_model()

            self.stdout.write(
                self.style.SUCCESS(f'✅ AI model trained successfully with accuracy: {accuracy:.2f}')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error training model: {str(e)}')
            )
            import traceback
            traceback.print_exc()























































