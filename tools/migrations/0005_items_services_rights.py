# Generated by Django 3.2.16 on 2022-12-07 17:25
from core.utils import insert_role_right_for_system
from django.db import migrations


def add_rights(apps, schema_editor):
    insert_role_right_for_system(64, 131007, apps)  # items
    insert_role_right_for_system(64, 131008, apps)  # items
    insert_role_right_for_system(64, 131009, apps)  # services
    insert_role_right_for_system(64, 131010, apps)  # services


class Migration(migrations.Migration):

    dependencies = [
        ('tools', '0004_registers_right_for_scheme_admin'),
    ]

    operations = [
        migrations.RunPython(add_rights),
    ]
