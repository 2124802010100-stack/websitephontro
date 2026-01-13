from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0030_rentalpost_is_rented'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentalpost',
            name='is_approved',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='rentalpost',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='rentalpost',
            name='approved_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='approved_posts', to=settings.AUTH_USER_MODEL),
        ),
    ]


