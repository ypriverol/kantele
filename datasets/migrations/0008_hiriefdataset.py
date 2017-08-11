# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-11 08:41
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0007_auto_20170810_1153'),
    ]

    operations = [
        migrations.CreateModel(
            name='HiriefDataset',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dataset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='datasets.Dataset')),
                ('hirief', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='datasets.HiriefRange')),
            ],
        ),
    ]
