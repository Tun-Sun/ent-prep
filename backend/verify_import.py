#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from subjects.models import Question, Answer

# Find the imported questions
questions = Question.objects.filter(
    source_type='authorial',
    external_id__startswith='test_form_001/'
).order_by('created' if hasattr(Question, 'created') else 'id')

print(f"✓ Found {questions.count()} imported questions:\n")

for q in questions:
    print(f"  ID: {q.id}")
    print(f"  Text: {q.text[:60]}...")
    print(f"  External ID: {q.external_id}")
    print(f"  Source: {q.source_type}")
    print(f"  Verification: {q.verification_status}")
    print(f"  Language: {q.language}")
    
    answers = q.answers.all()
    print(f"  Answers: {answers.count()}")
    for ans in answers:
        correct_mark = "✓" if ans.is_correct else "✗"
        print(f"    {correct_mark} {ans.text[:50]}")
    print()
