"""Read-only analysis of the frozen Markdown source to drive the converter."""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "executive-review-II.md"
text = SRC.read_text(encoding="utf-8")
lines = text.split("\n")
print(f"total_lines={len(lines)}")

# Headings
h1 = [i for i, l in enumerate(lines, 1) if re.match(r"^# ", l)]
h2 = [i for i, l in enumerate(lines, 1) if re.match(r"^## ", l)]
h3 = [i for i, l in enumerate(lines, 1) if re.match(r"^### ", l)]
h4 = [i for i, l in enumerate(lines, 1) if re.match(r"^#### ", l)]
h5plus = [i for i, l in enumerate(lines, 1) if re.match(r"^#{5,} ", l)]
print(f"H1={len(h1)} H2={len(h2)} H3={len(h3)} H4={len(h4)} H5+={len(h5plus)}")
print(f"### count(H1..H3) = {len(h1)+len(h2)+len(h3)}")

# Fenced code blocks
fence_re = re.compile(r"^(\s*)```(\w*)\s*$")
blocks = []
i = 0
while i < len(lines):
    m = fence_re.match(lines[i])
    if m:
        lang = m.group(2)
        start = i + 1
        j = start
        while j < len(lines) and not fence_re.match(lines[j]):
            j += 1
        body = lines[start:j]
        blocks.append((lang, start + 1, j, body))
        i = j + 1
    else:
        i += 1

print(f"\nfenced_blocks={len(blocks)}")
tot = 0
for lang, first, last, body in blocks:
    tot += len(body)
    print(f"  lang={lang!r:10} lines {first}-{last} (exclusive end) content_lines={len(body)}")
print(f"total_code_content_lines={tot}")

# Tables: a table block is a set of consecutive lines starting with a header row
# followed by a separator row matching |---|
sep_re = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
tables = []
i = 0
while i < len(lines):
    if "|" in lines[i] and i + 1 < len(lines) and sep_re.match(lines[i + 1]):
        start = i
        j = i + 2
        while j < len(lines) and "|" in lines[j] and lines[j].strip():
            j += 1
        header = lines[start]
        ncols = len([c for c in header.strip().strip("|").split("|")])
        rows = j - start - 2
        tables.append((start + 1, j, ncols, rows))
        i = j
    else:
        i += 1

print(f"\ntables={len(tables)}")
tot_rows = 0
for first, last, ncols, rows in tables:
    tot_rows += rows
    print(f"  lines {first}-{last} cols={ncols} data_rows={rows}")
print(f"total_data_rows={tot_rows}")
