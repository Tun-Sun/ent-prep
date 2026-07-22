#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from subjects.models import Subject
# Get Physics by Russian name
phys = Subject.objects.filter(name__icontains='Физика').first()
if phys:
    print(f"Subject name: {phys.name}")
    print(f"Subject slug: {phys.slug}")
