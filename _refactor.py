"""One-off refactor: remove the inline MathML converter from parse_testent.py
(lines 51..405, the block between BASE_URL and extract_js_variants) and replace
it with an import from subjects.mathml_conv.
"""
import io

path = r'C:\Users\user\ZCodeProject\ent-prep\backend\subjects\management\commands\parse_testent.py'

with io.open(path, encoding='utf-8') as f:
    lines = f.readlines()

# Locate boundaries by content to be safe.
start = None  # line index of the "# ---..." comment opening the converter block
end = None    # line index of the blank line right before "def extract_js_variants"
for i, ln in enumerate(lines):
    if start is None and 'MathML → LaTeX converter (recursive, no external deps)' in ln:
        start = i
    if 'def extract_js_variants' in ln:
        end = i
        break

assert start is not None, "start marker not found"
assert end is not None, "extract_js_variants not found"

# Walk back from end over blank lines so we land right after the converter.
while end > start and lines[end - 1].strip() == '':
    end -= 1

print(f"Removing lines {start + 1}..{end} (0-idx {start}..{end - 1})")
print("First removed:", repr(lines[start]))
print("Last removed :", repr(lines[end - 1]))
print("Kept after   :", repr(lines[end]))

replacement = [
    "from subjects.mathml_conv import mathml_to_latex, convert_single_math\n",
    "\n",
    "\n",
]

new_lines = lines[:start] + replacement + lines[end:]

with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(new_lines)

print(f"Done. New file has {len(new_lines)} lines (was {len(lines)}).")
