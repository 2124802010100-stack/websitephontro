from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Make a user staff member to access admin moderation features'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to make staff')
        parser.add_argument(
            '--superuser',
            action='store_true',
            help='Also make the user a superuser',
        )
        parser.add_argument(
            '--revoke',
            action='store_true',
            help='Revoke staff/superuser permissions instead of granting them',
        )

    def handle(self, *args, **options):
        username = options['username']
        make_superuser = options['superuser']
        revoke = options['revoke']
        
        try:
            user = User.objects.get(username=username)
            
            if revoke:
                # Revoke permissions
                user.is_staff = False
                user.is_superuser = False
                user.save()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully revoked staff and superuser permissions from user "{username}"!'
                    )
                )
            else:
                # Grant permissions
                user.is_staff = True
                if make_superuser:
                    user.is_superuser = True
                
                user.save()
                
                status = "staff"
                if make_superuser:
                    status = "staff and superuser"
                    
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully made user "{username}" a {status}!'
                    )
                )
            
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'User "{username}" does not exist!'
                )
            )
            
            # Show available users
            users = User.objects.all().values_list('username', flat=True)
            self.stdout.write('Available users:')
            for u in users:
                self.stdout.write(f'  - {u}')
