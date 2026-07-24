from django.db import migrations


def hide_kazakh_literature(apps, schema_editor):
    Subject = apps.get_model('subjects', 'Subject')
    Subject.objects.filter(slug='literature_kazakh').update(is_visible=False)


class Migration(migrations.Migration):

    dependencies = [
        ('subjects', '0008_subject_show_in_profiles'),
    ]

    operations = [
        migrations.RunPython(hide_kazakh_literature, reverse_code=migrations.RunPython.noop),
    ]
