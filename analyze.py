import re, sys

with open(r'C:\Users\user\ZCodeProject\ent-prep\variant10_raw.html', 'r', encoding='utf-8') as f:
    html = f.read()

db_start = html.find('const questionDatabase = {')
if db_start == -1:
    print("NOT FOUND questionDatabase")
    sys.exit(1)

# Find the end of the object - matching braces
depth = 0
i = db_start + len('const questionDatabase = ')
while i < len(html):
    if html[i] == '{':
        depth += 1
    elif html[i] == '}':
        depth -= 1
        if depth == 0:
            break
    i += 1

db_content = html[db_start:i+1]
print(f"questionDatabase object length: {len(db_content)}")

# Count questions
q_count = db_content.count("question:")
print(f"Questions found: {q_count}")

# Extract all correct indices
corrects = re.findall(r'correct:\s*(\d+)', db_content)
print(f"Correct answers: {corrects[:10]}...")

# Check for images inside the database
imgs = re.findall(r'[a-zA-Z0-9_/\-]+\.(?:png|jpg|jpeg|gif|svg|webp)', db_content)
print(f"Image refs in DB: {imgs}")

# Print questions 3-5 structure
lines = db_content.split('\n')
q_num = 0
capture = False
captured = 0
for line in lines:
    if 'question:' in line and not line.strip().startswith('//'):
        q_num += 1
        if 3 <= q_num <= 5:
            capture = True
    if capture:
        print(line)
        if line.strip() == '},':
            capture = False
            captured += 1
            print()
    if captured >= 3:
        break

# Also check the end of the DB for any extra tests
print("\n--- Last 500 chars of DB ---")
print(db_content[-500:])
