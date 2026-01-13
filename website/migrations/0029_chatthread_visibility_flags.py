from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0028_remove_chatthread_deleted_by_guest_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatthread',
            name='hidden_for_guest',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='chatthread',
            name='hidden_for_owner',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='chatthread',
            name='hidden_for_guest_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chatthread',
            name='hidden_for_owner_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]



