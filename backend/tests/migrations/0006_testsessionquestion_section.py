from django.db import migrations, models


SECTION_ORDER = ('history', 'reading', 'math_lit', 'profile1', 'profile2')


def populate_sections(apps, schema_editor):
    TestSessionQuestion = apps.get_model('tests', 'TestSessionQuestion')
    TestSectionResult = apps.get_model('tests', 'TestSectionResult')

    for session_id in TestSessionQuestion.objects.values_list('session_id', flat=True).distinct():
        section_sizes = dict(
            TestSectionResult.objects.filter(session_id=session_id).values_list('section', 'total_questions')
        )
        if not section_sizes:
            continue
        position = 1
        for section in SECTION_ORDER:
            count = section_sizes.get(section, 0)
            if count:
                TestSessionQuestion.objects.filter(
                    session_id=session_id,
                    position__gte=position,
                    position__lt=position + count,
                ).update(section=section)
                position += count


class Migration(migrations.Migration):

    dependencies = [
        ('tests', '0005_testsessionquestion'),
    ]

    operations = [
        migrations.AddField(
            model_name='testsessionquestion',
            name='section',
            field=models.CharField(blank=True, choices=[
                ('history', 'История Казахстана'),
                ('reading', 'Грамотность чтения'),
                ('math_lit', 'Математическая грамотность'),
                ('profile1', 'Профильный предмет 1'),
                ('profile2', 'Профильный предмет 2'),
            ], default='', max_length=12),
        ),
        migrations.RunPython(populate_sections, migrations.RunPython.noop),
    ]
