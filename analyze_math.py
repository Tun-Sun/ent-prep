"""Analyze MathML structures in variant HTML files."""
import re
import glob
import sys

files = sorted(glob.glob(r'C:\Users\user\ZCodeProject\ent-prep\variant*_raw.html'))
if not files:
    print("No HTML files found")
    sys.exit(1)

all_structures = {}
for fname in files:
    with open(fname, 'r', encoding='utf-8') as f:
        html = f.read()
    maths = re.findall(r'<math>.*?</math>', html, re.DOTALL)
    print(f"\n=== {fname}: {len(maths)} math blocks ===")
    for m in maths:
        tags = tuple(re.findall(r'<(m\w+|math)\b', m))
        if tags not in all_structures:
            all_structures[tags] = m

print(f"\n\n=== {len(all_structures)} UNIQUE MathML tag-signatures ===")
for i, (sig, sample) in enumerate(all_structures.items(), 1):
    print(f"\n{i}. TAGS: {sig}")
    print(f"   SAMPLE: {sample[:250]}")
