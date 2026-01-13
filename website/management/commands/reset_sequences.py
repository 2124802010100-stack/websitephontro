from django.core.management.base import BaseCommand
from django.db import connection


TABLES = [
    "website_province",
    "website_district",
    "website_ward",
]


class Command(BaseCommand):
    help = "Reset PostgreSQL ID sequences for location tables to MAX(id). Prevents duplicate key errors when adding new records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tables",
            nargs="*",
            default=TABLES,
            help="Custom list of tables to reset (defaults to province/district/ward)",
        )

    def handle(self, *args, **options):
        tables = options["tables"]
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute(
                    f'''
                    SELECT setval(
                        pg_get_serial_sequence('"{table}"','id'),
                        COALESCE((SELECT MAX(id) FROM "{table}"), 1),
                        true
                    );
                    '''
                )
        self.stdout.write(self.style.SUCCESS("Sequences reset for: " + ", ".join(tables)))


