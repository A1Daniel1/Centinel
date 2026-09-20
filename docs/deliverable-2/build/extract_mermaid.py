"""Extract the three mermaid fenced blocks from the frozen Markdown verbatim."""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "executive-review-II.md"
OUT = BASE / "build"
OUT.mkdir(parents=True, exist_ok=True)

lines = SRC.read_text(encoding="utf-8").split("\n")
fence_re = re.compile(r"^\s*```(\w*)\s*$")

names = ["c4-level1-context", "c4-level2-containers", "c4-level3-components"]
found = []
i = 0
while i < len(lines):
    m = fence_re.match(lines[i])
    if m:
        lang = m.group(1)
        start = i + 1
        j = start
        while j < len(lines) and not fence_re.match(lines[j]):
            j += 1
        if lang == "mermaid":
            found.append(lines[start:j])
        i = j + 1
    else:
        i += 1

assert len(found) == 3, f"expected 3 mermaid blocks, found {len(found)}"
for name, body in zip(names, found):
    # UTF-8, no BOM; mermaid-cli wants a trailing newline
    content = "\n".join(body) + "\n"
    (OUT / f"{name}.mmd").write_text(content, encoding="utf-8", newline="\n")
    print(f"{name}.mmd -> {len(body)} lines, {len(content.encode('utf-8'))} bytes")
