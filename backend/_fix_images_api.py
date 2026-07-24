import os, sys, io, requests
sys.path.insert(0, 'backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
os.environ['GOOGLE_SERVICE_ACCOUNT_FILE'] = r'C:\Users\user\ZCodeProject\ent-prep\backend\service-account.json'
import django; django.setup()
from django.core.files.images import ImageFile
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from subjects.models import Question

creds = Credentials.from_service_account_file(
    r'C:\Users\user\ZCodeProject\ent-prep\backend\service-account.json',
    scopes=['https://www.googleapis.com/auth/forms.body.readonly'])
service = build('forms', 'v1', credentials=creds)

FORMS_TO_FIX = [
    '1lzgYOS0qil__-zO0ozMPz6bB0K_HdNvySA8f4WTv91k',  # V27 math
    '1c7nsbqYf9w2V16f6KE1XWSkxW9wqOH5XAwZ-HaLX-Mg',  # V27 physics
    '1qTbEu9B4qpzhY9LZgob9L3JRZ9xaVO7XGxuexiIFbqo',  # V27 history
    '1ENM_azRq_AzU_GRlyqpznEOXqYeJkI42QFv2RUMwlTs',  # V27 reading
]

def _detect_ext(content):
    magic_map = {b'\xff\xd8\xff': 'jpg', b'\x89PNG\r\n\x1a\n': 'png', b'GIF87a': 'gif', b'GIF89a': 'gif', b'RIFF': 'webp'}
    for magic, ext in magic_map.items():
        if content[:len(magic)] == magic:
            return ext
    return 'jpg'

fixed = 0
errors = 0
skipped = 0

for form_id in FORMS_TO_FIX:
    print(f'\n=== {form_id} ===')
    form = service.forms().get(formId=form_id).execute()

    for item in form.get('items', []):
        qi = item.get('questionItem')
        if not qi:
            continue
        q = qi.get('question', {})
        if not q.get('choiceQuestion'):
            continue
        item_id = item.get('itemId', '')
        ext_id = f'{form_id}/{item_id}'
        img_url = qi.get('image', {}).get('contentUri', '')
        if not img_url:
            continue

        qs = Question.objects.filter(external_id=ext_id, source_type='authorial')
        for db_q in qs:
            if db_q.image and db_q.image.name:
                skipped += 1
                continue

            print(f'  Q{db_q.id} downloading... ', end='')
            try:
                resp = requests.get(img_url, timeout=15)
                if resp.status_code == 200 and len(resp.content) > 100:
                    ext = _detect_ext(resp.content)
                    filename = f'q_{db_q.id}_{form_id[:8]}_{item_id[:8]}.{ext}'
                    db_q.image.save(filename, ImageFile(io.BytesIO(resp.content), name=filename), save=True)
                    fixed += 1
                    print(f'OK ({len(resp.content)} bytes)')
                else:
                    errors += 1
                    print(f'HTTP {resp.status_code}')
            except Exception as e:
                errors += 1
                print(f'ERROR: {e}')

print(f'\nDone: {fixed} fixed, {errors} errors, {skipped} skipped')
