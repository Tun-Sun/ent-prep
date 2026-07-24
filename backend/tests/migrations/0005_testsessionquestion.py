import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subjects', '0010_variant_topic_variant'),
        ('tests', '0004_alter_testsession_started_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='TestSessionQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveIntegerField()),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='subjects.question')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='session_questions', to='tests.testsession')),
            ],
            options={'ordering': ['position']},
        ),
        migrations.AddConstraint(
            model_name='testsessionquestion',
            constraint=models.UniqueConstraint(fields=('session', 'question'), name='unique_session_question'),
        ),
        migrations.AddConstraint(
            model_name='testsessionquestion',
            constraint=models.UniqueConstraint(fields=('session', 'position'), name='unique_session_question_position'),
        ),
    ]
