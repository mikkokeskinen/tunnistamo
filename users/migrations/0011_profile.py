# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-08-29 06:44
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('munigeo', '0003_add_modified_time_to_address_and_street'),
        ('thesaurus', '0001_initial'),
        ('users', '0010_add_fields_to_users_applications'),
    ]

    operations = [
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('phone', models.CharField(blank=True, max_length=255, null=True)),
                ('pushbullet_access_token', models.CharField(blank=True, max_length=255, null=True)),
                ('language', models.CharField(choices=[('fi', 'Finnish'), ('en', 'English'), ('sv', 'Swedish')], max_length=7)),
                ('contact_method', models.CharField(choices=[('email', 'Email'), ('pushbullet', 'Pushbullet'), ('sms', 'SMS')], max_length=30)),
                ('concepts_of_interest', models.ManyToManyField(blank=True, to='thesaurus.Concept')),
                ('divisions_of_interest', models.ManyToManyField(blank=True, to='munigeo.AdministrativeDivision')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
