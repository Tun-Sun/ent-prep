#!/usr/bin/env python
"""Check/create Physics subject and run import test."""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from subjects.models import Subject, Question, Topic

# Check/create Physics
phys, created = Subject.objects.get_or_create(
    slug='physics',
    defaults={'name': 'Physics', 'icon': '⚛️', 'description': 'Physics and mechanics'}
)

if created:
    print(f"✓ Created Physics subject")
else:
    print(f"✓ Physics subject exists: {phys.name}")

# Count existing questions
count = Question.objects.filter(topic__subject=phys).count()
print(f"  Current questions in Physics: {count}")

# List topics
topics = Topic.objects.filter(subject=phys).values_list('name', flat=True)
if topics:
    print(f"  Topics: {', '.join(topics)}")
