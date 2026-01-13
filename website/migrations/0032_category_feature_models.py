from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0031_rentalpost_approval_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='RoomCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('slug', models.SlugField(max_length=50, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Feature',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('code', models.SlugField(max_length=50, unique=True)),
            ],
        ),
        migrations.AddField(
            model_name='rentalpost',
            name='category_obj',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='posts', to='website.roomcategory'),
        ),
        migrations.AddField(
            model_name='rentalpost',
            name='features_obj',
            field=models.ManyToManyField(blank=True, related_name='posts', to='website.feature'),
        ),
    ]


