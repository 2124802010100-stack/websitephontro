from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = "Check if pgvector extension is installed in PostgreSQL"

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM pg_available_extensions WHERE name = 'vector';")
            row = cursor.fetchone()
            if row:
                self.stdout.write(self.style.SUCCESS(
                    f"✅ pgvector extension is available: {row}"
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    "⚠️ pgvector extension NOT found. Install it:\n"
                    "   Windows: Download from https://github.com/pgvector/pgvector/releases\n"
                    "   Linux: apt install postgresql-15-pgvector\n"
                    "   Then: CREATE EXTENSION vector; in PostgreSQL"
                ))
