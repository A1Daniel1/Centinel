"""Fidelity verification: compare the frozen Markdown with the generated TeX."""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
MD = (BASE / "executive-review-II.md").read_text(encoding="utf-8").split("\n")
TEX = (BASE / "executive-review-II.tex").read_text(encoding="utf-8")

print("================ HEADINGS ================")
md_h = {n: sum(1 for l in MD if re.match(r"^#{%d} " % n, l)) for n in (1, 2, 3, 4)}
md_h13 = md_h[1] + md_h[2] + md_h[3]
tex_sec = len(re.findall(r"\\section\{", TEX))
tex_sub = len(re.findall(r"\\subsection\{", TEX))
tex_subsub = len(re.findall(r"\\subsubsection\{", TEX))
tex_mdh = len(re.findall(r"\\mdhfour\{", TEX))
print(f"MD  H1={md_h[1]} H2={md_h[2]} H3={md_h[3]} H4={md_h[4]}  (H1..H3={md_h13})")
print(f"TEX \\section={tex_sec} \\subsection={tex_sub} \\subsubsection={tex_subsub} "
      f"sum={tex_sec+tex_sub+tex_subsub} \\mdhfour={tex_mdh}")
print(f"  difference (MD H1..H3 - TEX sectioning) = {md_h13 - (tex_sec+tex_sub+tex_subsub)}"
      "  [explained by H1 title + 'Table of Contents' heading]")

print("================ TABLES ================")
sep_re = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
md_tables = 0
rows_total = 0
i = 0
while i < len(MD):
    if "|" in MD[i] and i + 1 < len(MD) and sep_re.match(MD[i + 1]):
        md_tables += 1
        j = i + 2
        while j < len(MD) and MD[j].strip() and "|" in MD[j]:
            rows_total += 1
            j += 1
        i = j
    else:
        i += 1
tex_long = len(re.findall(r"\\begin\{longtable\}", TEX))
tex_tabular = len(re.findall(r"\\begin\{tabular\}", TEX))
print(f"MD table blocks={md_tables}  data rows={rows_total}  "
      f"total pipe rows (header+sep+data)={rows_total + 2*md_tables}")
print(f"TEX longtable={tex_long} tabular(title metadata)={tex_tabular} "
      f"total={tex_long+tex_tabular}")

print("================ CODE ================")
fence_re = re.compile(r"^(\s*)```(\w*)\s*$")
blocks = []
i = 0
while i < len(MD):
    m = fence_re.match(MD[i])
    if m:
        lang = m.group(2)
        start = i + 1
        j = start
        while j < len(MD) and not fence_re.match(MD[j]):
            j += 1
        blocks.append((lang, MD[start:j]))
        i = j + 1
    else:
        i += 1

md_all = sum(len(b) for _, b in blocks)
md_mermaid = sum(len(b) for lang, b in blocks if lang == "mermaid")
md_listing = sum(len(b) for lang, b in blocks if lang != "mermaid")
print(f"MD fenced blocks={len(blocks)}  total content lines={md_all}")
print(f"  mermaid lines (replaced by figures)={md_mermaid}")
print(f"  non-mermaid lines (expect in lstlisting)={md_listing}")
for lang, b in blocks:
    print(f"    lang={lang!r:10} lines={len(b)}")

tex_lst_env = len(re.findall(r"\\begin\{lstlisting\}", TEX))
tex_lst_lines = 0
for m in re.finditer(r"\\begin\{lstlisting\}\n(.*?)\\end\{lstlisting\}", TEX, re.S):
    tex_lst_lines += len(m.group(1).split("\n")) - 1  # trailing newline
print(f"TEX lstlisting environments={tex_lst_env}  content lines={tex_lst_lines}")
tex_figs = len(re.findall(r"\\includegraphics", TEX))
print(f"TEX includegraphics={tex_figs}")

print("================ INLINE ================")
print(f"MD bare '**' bold markers lines: {sum(l.count('**') for l in MD)}")
print(f"TEX \\textbf={len(re.findall(r'\\textbf', TEX))} "
      f"\\emph={len(re.findall(r'\\emph', TEX))} "
      f"\\texttt={len(re.findall(r'\\texttt', TEX))}")
