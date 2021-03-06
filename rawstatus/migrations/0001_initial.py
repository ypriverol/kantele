# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2018-05-16 08:10
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('jobs', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='FileJob',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='jobs.Job')),
            ],
        ),
        migrations.CreateModel(
            name='Producer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('client_id', models.CharField(max_length=100)),
                ('heartbeat', models.DateTimeField(auto_now=True, verbose_name='last seen')),
            ],
        ),
        migrations.CreateModel(
            name='RawFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('source_md5', models.CharField(max_length=32, unique=True)),
                ('size', models.BigIntegerField(verbose_name='size in bytes')),
                ('date', models.DateTimeField(verbose_name='date/time created')),
                ('claimed', models.BooleanField()),
                ('deleted', models.BooleanField(default=False)),
                ('producer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rawstatus.Producer')),
            ],
        ),
        migrations.CreateModel(
            name='ServerShare',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('uri', models.CharField(max_length=100)),
                ('share', models.CharField(max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name='StoredFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filename', models.CharField(max_length=200)),
                ('filetype', models.CharField(max_length=20)),
                ('path', models.CharField(max_length=200)),
                ('md5', models.CharField(max_length=32)),
                ('checked', models.BooleanField()),
                ('rawfile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rawstatus.RawFile')),
                ('servershare', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rawstatus.ServerShare')),
            ],
        ),
        migrations.CreateModel(
            name='SwestoreBackedupFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('swestore_path', models.CharField(max_length=200)),
                ('success', models.BooleanField()),
                ('storedfile', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='rawstatus.StoredFile')),
            ],
        ),
        migrations.AddField(
            model_name='filejob',
            name='storedfile',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='rawstatus.StoredFile'),
        ),
    ]
