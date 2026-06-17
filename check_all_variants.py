"""Check all physics variants for image references."""
import urllib.request
import re
import time

variants = [
    ('variant-10', 'Волны и оптика', '30 вопр.'),
    ('variant-2', 'Динамика', '30 вопр.'),
    ('variant-5', 'Импульс и столкновения', '10 вопр.'),
    ('variant-1', 'Кинематика', '40 вопр.'),
    ('variant-9', 'Магнетизм', '10 вопр.'),
    ('variant-6', 'Молекулярная физика и газы', '10 вопр.'),
    ('variant-4', 'Работа, энергия, мощность', '10 вопр.'),
    ('variant-3', 'Статика и равновесие', '10 вопр.'),
    ('variant-7', 'Термодинамика', '10 вопр.'),
    ('variant-8', 'Электростатика', '10 вопр.'),
]

for var_name, topic, count in variants:
    url = f'https://test-ent.kz/test/physics/{var_name}.php'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')

        # Find questionDatabase
        db_start = html.find('const questionDatabase = {')
        if db_start == -1:
            print(f"❌ {var_name}: No questionDatabase found")
            continue

        # Count questions
        q_count = html.count("question:", db_start)
        db_end = html.find('};', db_start + 2000)
        db_content = html[db_start:db_end]

        # Count images inside DB
        imgs = re.findall(r'[a-zA-Z0-9_/\-]+\.(?:png|jpg|jpeg|gif|svg|webp)', db_content)

        # Check for 'image' key in questions
        has_image_key = 'image:' in db_content or 'img:' in db_content

        print(f"✅ {var_name:15s} | {topic:35s} | {q_count}Q | imgs: {len(imgs)} | image_key: {has_image_key}")
        for img in imgs[:5]:
            print(f"   └─ {img}")

        time.sleep(0.5)
    except Exception as e:
        print(f"❌ {var_name}: {e}")
