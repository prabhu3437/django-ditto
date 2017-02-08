# -*- coding: utf-8 -*-
# Generated by Django 1.10.1 on 2016-11-21 13:24
from __future__ import unicode_literals

from django.db import migrations, models


def set_post_year(apps, schema_editor):
    """
    Sets the `post_year` on every Bookmark.
    """
    Tweet = apps.get_model('twitter', 'Tweet')
    for row in Tweet.objects.all():
        row.post_year = row.post_time.year
        row.save()


class Migration(migrations.Migration):

    dependencies = [
        ('twitter', '0052_auto_20161117_1622'),
    ]

    operations = [
        migrations.AddField(
            model_name='tweet',
            name='post_year',
            field=models.PositiveSmallIntegerField(blank=True, db_index=True, help_text='Set automatically on save', null=True),
        ),

        migrations.RunPython(set_post_year, reverse_code=migrations.RunPython.noop),
    ]
