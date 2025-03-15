# Generated by Django 5.1.7 on 2025-03-15 14:28

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Item',
            fields=[
                ('sku', models.CharField(max_length=100, primary_key=True, serialize=False, unique=True)),
                ('description', models.CharField(max_length=250)),
                ('retail_price', models.FloatField()),
                ('quantity', models.IntegerField()),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='ShopItem',
            fields=[
                ('sku', models.CharField(max_length=100, primary_key=True, serialize=False, unique=True)),
                ('description', models.CharField(max_length=250)),
                ('retail_price', models.FloatField()),
                ('quantity', models.IntegerField()),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('shop_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
