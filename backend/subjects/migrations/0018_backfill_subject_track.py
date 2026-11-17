from django.db import migrations


def backfill_subject_track(apps, schema_editor):
    """Все существующие предметы — ЕНТ.

    Банк задач собирался под ЕНТ, поэтому новый трек у старого контента один.
    Пустой трек остаётся только у предметов, созданных после этой миграции без
    явного выбора: так они не пропадают ни у одного трека.
    """
    Subject = apps.get_model('subjects', 'Subject')
    Subject.objects.update(track='ent')


def clear_subject_track(apps, schema_editor):
    Subject = apps.get_model('subjects', 'Subject')
    Subject.objects.update(track='')


class Migration(migrations.Migration):

    dependencies = [
        ('subjects', '0017_subject_track'),
    ]

    operations = [
        migrations.RunPython(backfill_subject_track, clear_subject_track),
    ]
