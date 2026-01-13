from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0029_chatthread_visibility_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentalpost',
            name='is_rented',
            field=models.BooleanField(default=False),
        ),
    ]


