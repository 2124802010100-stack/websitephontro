# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0064_alter_customerprofile_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerprofile',
            name='display_name',
            field=models.CharField(blank=True, help_text='Tên hiển thị cho người dùng đăng nhập bằng Google', max_length=100, null=True),
        ),
    ]

