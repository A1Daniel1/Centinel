"""Inventory non-ASCII characters and escapechar candidates in fenced code blocks."""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
lines = (BASE / "executive-review-II.md").read_text(encoding="utf-8").split("\n")
fence_re = re.compile(r"^\s*```(\w*)\s*$")

blocks = []
i = 0
while i < len(lines):
    m = fence_re.match(lines[i])
    if m:
        lang = m.group(1)
        start = i + 1
        j = start
        while j < len(lines) and not fence_re.match(lines[j]):
            j += 1
        blocks.append((lang, lines[start:j]))
        i = j + 1
    else:
        i += 1

for idx, (lang, body) in enumerate(blocks):
    chars = {}
    at_count = 0
    pct_count = 0
    for ln in body:
        for ch in ln:
            if ord(ch) > 127:
                chars[ch] = chars.get(ch, 0) + 1
        at_count += ln.count("@")
        pct_count += ln.count("%")
    print(f"block {idx} lang={lang!r}: non_ascii={ {c: (hex(ord(c)), n) for c, n in chars.items()} }  at={at_count} pct={pct_count}")
