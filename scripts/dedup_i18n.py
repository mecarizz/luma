"""Remove duplicate keys from core/i18n.py's _TURKISH dict (keep first occurrence)."""
import re

with open("core/i18n.py", encoding="utf-8") as f:
    content = f.read()

# Find the dict
dict_match = re.search(r"_TURKISH: Dict\[str, str\] = \{", content)
start = dict_match.end()          # just after the opening {

# Find the closing } that ends the dict (before 'def tr(')
tr_def = content.index("def tr(")
dict_end = content.rindex("}", 0, tr_def)

before = content[:start]
middle = content[start:dict_end]
after = content[dict_end:]        # starts with '}'

seen = set()
clean = []
for line in middle.splitlines():
    stripped = line.strip()
    # Skip blank / comment lines unchanged
    if not stripped or stripped.startswith("#"):
        clean.append(line)
        continue
    # Extract key: lines look like  "some key": "translation",
    m = re.match(r'\s*"((?:[^"\\]|\\.)*)"\s*:', line)
    if m:
        key = m.group(1)
        if key in seen:
            continue   # drop duplicate
        seen.add(key)
    clean.append(line)

new_content = before + "\n".join(clean) + "\n" + after
with open("core/i18n.py", "w", encoding="utf-8") as f:
    f.write(new_content)
print(f"Done. {len(seen)} unique keys kept.")
