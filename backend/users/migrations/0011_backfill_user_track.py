from django.db import migrations


def backfill_user_track(apps, schema_editor):
    """Проставить трек тем, кто уже учится.

    Платформа выросла из тренажёра 11 класса, поэтому все выпускники получают
    `ent`. Младшие классы — школа. Ученики без класса и сотрудники остаются без
    трека: угадывать за них нельзя, а `None` — честное «ещё не выбрано».
    """
    User = apps.get_model('users', 'User')
    User.objects.filter(role='student', grade=11).update(track='ent')
    User.objects.filter(role='student', grade__gte=5, grade__lte=10).update(track='school')
    User.objects.exclude(role='student').update(track=None)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0010_user_track'),
    ]

    operations = [
        migrations.RunPython(backfill_user_track, migrations.RunPython.noop),
    ]
