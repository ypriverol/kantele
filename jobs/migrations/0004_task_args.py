# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2018-09-04 15:21
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0003_auto_20180629_1147'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='args',
            field=models.TextField(default=''),
            preserve_default=False,
        ),
    ]
