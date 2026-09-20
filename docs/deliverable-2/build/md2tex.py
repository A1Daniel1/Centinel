#!/usr/bin/env python3
r"""Deterministic converter: executive-review-II.md -> executive-review-II.tex.

Reads the frozen Markdown source and emits a standalone LaTeX document that
mirrors main.tex (Deliverable 1). No content is summarised or dropped:
paragraphs, tables, lists, blockquotes and every line of every fenced code
block are reproduced. The three Mermaid blocks are replaced by the rendered
PNGs under figures/.

Design notes
------------
* Headings follow the required mapping but shifted so the H1 title block is
  consumed by the front matter (it must not reappear as a body section):
      H2 -> \subsection, H3 -> \subsubsection, H4 -> \mdhfour (unnumbered).
  Automatic numbering is disabled (secnumdepth=-2) because the source already
  carries its own numbering in the heading text, which is preserved verbatim.
* Tables -> longtable + booktabs, with per-column p{} widths computed from the
  cell content, ragged-right, and a size chosen from the column count.
* Code -> lstlisting with breaklines. Non-ASCII glyphs that T1/lmtt cannot
  typeset (box drawing, arrows, accented Latin) are pre-mapped to ASCII art or
  to LaTeX escapes wrapped in the listing escapechar '@'. The '@' character
  does not occur anywhere in the code blocks (verified).
"""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "executive-review-II.md"
OUT = BASE / "executive-review-II.tex"

TEXTWIDTH_IN = 6.5
TABCOLSEP_PT = 5.0
FIGURE_NAMES = [
    "diagramas-c4/01-nivel1-contexto",
    "diagramas-c4/02-nivel2-contenedores",
    "diagramas-c4/03-nivel3-componentes-inferencia",
]

# ---------------------------------------------------------------- inline ----

SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Characters that need an explicit LaTeX spelling (T1/inputenc does not cover
# all of these; verified empirically).
UNICODE_MAP = {
    "≥": r"\ensuremath{\geq}",
    "≤": r"\ensuremath{\leq}",
    "→": r"\ensuremath{\rightarrow}",
    "≈": r"\ensuremath{\approx}",
    "≠": r"\ensuremath{\neq}",
    "×": r"\ensuremath{\times}",
    "·": r"\ensuremath{\cdot}",
    "−": r"\ensuremath{-}",
    "—": r"\textemdash{}",
    "–": r"\textendash{}",
    "…": r"\ldots{}",
    "“": "``",
    "”": "''",
    "‘": "`",
    "’": "'",
    "§": r"\S{}",
    "°": r"\ensuremath{^\circ}",
    "µ": r"\ensuremath{\mu}",
    "\u00a0": "~",
    "\u2009": r"\,",
    "\u2011": "-",
}

# Accented Latin vowels used inside code blocks (mapped through escapechar).
CODE_ACCENTS = {
    "á": r"\'a", "é": r"\'e", "í": r"\'i", "ó": r"\'o", "ú": r"\'u",
    "Á": r"\'A", "É": r"\'E", "Í": r"\'I", "Ó": r"\'O", "Ú": r"\'U",
    "ñ": r"\~n", "Ñ": r"\~N", "ü": r"\"u", "Ü": r"\"U",
}


def escape_text(s: str) -> str:
    """Escape a plain-text run for LaTeX, expanding known Unicode glyphs."""
    out = []
    for ch in s:
        if ch in UNICODE_MAP:
            out.append(UNICODE_MAP[ch])
        elif ch in SPECIALS:
            out.append(SPECIALS[ch])
        else:
            out.append(ch)
    return "".join(out)


def escape_code(s: str) -> str:
    """Escape an inline-code run and add break opportunities for long tokens."""
    s = escape_text(s)
    # allow line breaks after separators commonly found in identifiers/URIs
    s = s.replace(r"\_", r"\_\allowbreak{}")
    s = s.replace("/", r"/\allowbreak{}")
    s = s.replace(".", r".\allowbreak{}")
    s = s.replace("-", r"-\allowbreak{}")
    s = s.replace(":", r":\allowbreak{}")
    s = s.replace("=", r"=\allowbreak{}")
    s = s.replace(",", r",\allowbreak{}")
    return s


CAMEL_RE = re.compile(r"([a-z\u00e0-\u00ff])([A-Z])")
WORD_RE = re.compile(r"[A-Za-z\u00c0-\u00ff]+")


def camel_break(s: str) -> str:
    """Add optional break points inside long CamelCase tokens (table cells).

    Only tokens of 14+ characters are split, so compact identifiers such as
    ArchiMate or DataObject stay intact while ApplicationComponent or
    BusinessCapability become breakable inside narrow columns.
    """

    def repl(m):
        w = m.group(0)
        if len(w) < 14:
            return w
        return CAMEL_RE.sub(r"\1\\allowbreak{}\2", w)

    return WORD_RE.sub(repl, s)


INLINE_RE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)")


def inline(s: str) -> str:
    """Convert inline Markdown (**bold**, *italic*, `code`) to LaTeX."""
    parts = []
    pos = 0
    for m in INLINE_RE.finditer(s):
        parts.append(escape_text(s[pos:m.start()]))
        tok = m.group(0)
        if tok[0] == "`":
            parts.append(r"\texttt{" + escape_code(tok[1:-1]) + "}")
        elif tok.startswith("**"):
            parts.append(r"\textbf{" + inline(tok[2:-2]) + "}")
        else:
            parts.append(r"\emph{" + inline(tok[1:-1]) + "}")
        pos = m.end()
    parts.append(escape_text(s[pos:]))
    return "".join(parts)


# ---------------------------------------------------------------- parsing ---

SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
HR_RE = re.compile(r"^\s*-{3,}\s*$")
FENCE_RE = re.compile(r"^(\s*)```(\w*)\s*$")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
UL_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
OL_RE = re.compile(r"^(\s*)\d+\.\s+(.*)$")


def parse_blocks(lines):
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue

        m = FENCE_RE.match(raw)
        if m:
            lang = m.group(2)
            j = i + 1
            body = []
            while j < n and not FENCE_RE.match(lines[j]):
                body.append(lines[j])
                j += 1
            blocks.append(("code", lang, body))
            i = j + 1
            continue

        m = HEAD_RE.match(raw)
        if m:
            blocks.append(("heading", len(m.group(1)), m.group(2).strip()))
            i += 1
            continue

        if HR_RE.match(s):
            blocks.append(("hr",))
            i += 1
            continue

        if s.startswith(">"):
            j = i
            quote = []
            while j < n and lines[j].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[j]))
                j += 1
            blocks.append(("quote", " ".join(q.strip() for q in quote)))
            i = j
            continue

        if "|" in raw and i + 1 < n and SEP_RE.match(lines[i + 1]):
            j = i + 2
            rows = [split_row(raw)]
            while j < n and lines[j].strip() and "|" in lines[j]:
                rows.append(split_row(lines[j]))
                j += 1
            blocks.append(("table", rows))
            i = j
            continue

        if UL_RE.match(raw):
            items = []
            j = i
            while j < n and lines[j].strip():
                mu = UL_RE.match(lines[j])
                if mu:
                    items.append(mu.group(2).strip())
                elif items:
                    items[-1] += " " + lines[j].strip()
                j += 1
            blocks.append(("ul", items))
            i = j
            continue

        if OL_RE.match(raw):
            items = []
            j = i
            while j < n and lines[j].strip():
                mo = OL_RE.match(lines[j])
                if mo:
                    items.append(mo.group(2).strip())
                elif items:
                    items[-1] += " " + lines[j].strip()
                j += 1
            blocks.append(("ol", items))
            i = j
            continue

        # paragraph: join soft-wrapped lines
        j = i
        para = []
        while j < n:
            s2 = lines[j].strip()
            if not s2:
                break
            if FENCE_RE.match(lines[j]) or HEAD_RE.match(lines[j]) or HR_RE.match(lines[j]):
                break
            if lines[j].strip().startswith(">"):
                break
            if UL_RE.match(lines[j]) or OL_RE.match(lines[j]):
                break
            if "|" in lines[j] and j + 1 < n and SEP_RE.match(lines[j + 1]):
                break
            para.append(s2)
            j += 1
        blocks.append(("para", " ".join(para)))
        i = j
    return blocks


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


# ---------------------------------------------------------------- tables ----

def plain_len(s):
    return len(re.sub(r"[*`\\{}]", "", s))


BREAK_RUN_RE = re.compile(r"[\s\-/_.=,:;()\[\]{}<>|]+")


def longest_run_len(s):
    """Longest stretch with no legal break opportunity (used to size columns)."""
    s = re.sub(r"[*`]", "", s)
    return max((len(p) for p in BREAK_RUN_RE.split(s)), default=0)


def table_fontsize(ncols):
    if ncols >= 6:
        return 7.0   # \scriptsize
    if ncols == 5:
        return 8.0   # \footnotesize
    return 9.0       # \small


def compute_widths(rows, ncols, fontsize_pt):
    weights = []
    for c in range(ncols):
        lens = sorted((plain_len(r[c]) for r in rows), reverse=True)
        take = max(1, len(lens) // 3)
        w = sum(lens[:take]) / take
        weights.append(max(w, 3.0))
    total = sum(weights)
    avail = TEXTWIDTH_IN - 2 * TABCOLSEP_PT * ncols / 72.0
    widths = [avail * w / total for w in weights]

    # Minimum width per column = widest unbreakable run at the table font size.
    # Bold runs are ~15% wider than regular text, so scale those up.
    charw = 0.60 * fontsize_pt / 72.0

    def run_width(c):
        best = 0.0
        for r in rows:
            w = longest_run_len(r[c])
            if "**" in r[c]:
                w *= 1.15
            best = max(best, w)
        return best * charw

    mins = [max(0.40, run_width(c)) for c in range(ncols)]
    for _ in range(50):
        deficit = sum(m - w for w, m in zip(widths, mins) if w < m - 1e-9)
        if deficit <= 1e-9:
            break
        slack = [max(0.0, w - m) for w, m in zip(widths, mins)]
        total_slack = sum(slack)
        if total_slack <= 1e-9:
            break
        take = min(deficit, total_slack)
        for k in range(ncols):
            if slack[k] > 0:
                widths[k] -= take * slack[k] / total_slack
        widths = [max(w, m) for w, m in zip(widths, mins)]
    if sum(widths) > avail + 1e-9:
        print(f"WARN: table with {ncols} cols demands {sum(mins):.2f}in "
              f"of minima but only {avail:.2f}in is available; scaling down")
        widths = [w * avail / sum(widths) for w in widths]
    return widths


def table_size(ncols):
    if ncols >= 6:
        return r"\scriptsize"
    if ncols == 5:
        return r"\footnotesize"
    return r"\small"


# Exact header rewrites for tables whose multi-word headers cannot fit their
# column at the available size. Content of the body rows is never altered.
HEADER_REWRITE = {
    "Elegida: Cloud-native multi-fuente":
        "\\shortstack{Elegida\\\\(cloud-native\\\\multi-fuente)}",
    "API de IA de terceros": "\\shortstack{API de IA\\\\de terceros}",
    "Pipeline sólo óptico": "\\shortstack{Pipeline\\\\sólo óptico}",
    "3 clasificadores binarios": "\\shortstack{3 clasificadores\\\\binarios}",
    "Relación al\u00a0modelo": "Relación al modelo",
}


def render_table(rows, out):
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    widths = compute_widths(rows, ncols, table_fontsize(ncols))
    spec = "@{}" + "".join("L{%.2fin}" % w for w in widths) + "@{}"
    header_cells = [
        HEADER_REWRITE.get(c.strip(), inline(c)) for c in rows[0]
    ]
    header = " & ".join(header_cells) + r" \\"
    out.append("{" + table_size(ncols))
    out.append(r"\begin{longtable}{" + spec + "}")
    out.append(r"\toprule")
    out.append(header)
    out.append(r"\midrule")
    out.append(r"\endfirsthead")
    out.append(r"\toprule")
    out.append(header)
    out.append(r"\midrule")
    out.append(r"\endhead")
    out.append(r"\bottomrule")
    out.append(r"\endlastfoot")
    for r in rows[1:]:
        out.append(" & ".join(inline(c) for c in r) + r" \\")
    out.append(r"\end{longtable}")
    out.append("}")
    out.append("")


def render_title_table(rows, out, width_a=1.20, width_b=3.55):
    spec = "@{}L{%.2fin}L{%.2fin}@{}" % (width_a, width_b)
    out.append(r"{\small")
    out.append(r"\begin{tabular}{" + spec + "}")
    out.append(r"\toprule")
    out.append(" & ".join(inline(c) for c in rows[0]) + r" \\")
    out.append(r"\midrule")
    for r in rows[1:]:
        out.append(" & ".join(inline(c) for c in r) + r" \\")
    out.append(r"\bottomrule")
    out.append(r"\end{tabular}\par}")
    out.append("")


# ---------------------------------------------------------------- code ------

def prep_code(body):
    """Map glyphs T1/lmtt cannot typeset; '@' is the listing escapechar."""
    prepped = []
    for ln in body:
        ln = ln.replace("→", "@\\ensuremath{\\rightarrow}@")
        ln = ln.replace("─", "-")
        ln = ln.replace("│", "|")
        ln = ln.replace("└", "`")
        ln = ln.replace("├", "+")
        for ch, rep in CODE_ACCENTS.items():
            if ch in ln:
                ln = ln.replace(ch, "@" + rep + "@")
        prepped.append(ln.rstrip())
    return prepped


# ---------------------------------------------------------------- assemble --

def build():
    lines = SRC.read_text(encoding="utf-8").split("\n")
    blocks = parse_blocks(lines)

    title = None
    subtitle = None
    meta_rows = None
    body = []
    in_body = False
    seen_meta = False

    for b in blocks:
        kind = b[0]
        if kind == "heading":
            level, text = b[1], b[2]
            if level == 1 and title is None:
                title = text
                continue
            if level == 2 and text.strip().lower() == "table of contents":
                continue
            in_body = True
            body.append(b)
            continue
        if kind == "para" and subtitle is None and not seen_meta:
            subtitle = b[1]
            continue
        if kind == "table" and not seen_meta:
            meta_rows = b[1]
            seen_meta = True
            continue
        if not in_body:
            continue
        body.append(b)

    if title is None:
        raise SystemExit("H1 title not found in source")
    if meta_rows is None:
        raise SystemExit("metadata table not found in source")

    def meta_lookup(field):
        for r in meta_rows:
            if len(r) >= 2 and r[0].strip().strip("*").lower() == field.lower():
                return r[1].strip()
        return None

    authors_raw = meta_lookup("Authors") or (
        "Juan Pablo Vélez Muñoz · Luiza Mariana Gonzalez Veloza · "
        "Daniel Alexander Ahumada León"
    )
    authors = [a.strip() for a in re.split(r"[·]", authors_raw) if a.strip()]
    date_raw = meta_lookup("Date") or "September 2026"
    course = "Enterprise Architecture and Digital Transformation"

    out = []
    out.append(r"% !TEX program = pdflatex")
    out.append("% Generated by build/md2tex.py from executive-review-II.md (frozen).")
    out.append(r"\documentclass{article}")
    out.append(r"\usepackage[utf8]{inputenc}")
    out.append(r"\usepackage[T1]{fontenc}")
    out.append(r"\usepackage[spanish,es-nodecimaldot]{babel}")
    out.append(r"\usepackage[margin=1in]{geometry}")
    out.append(r"\usepackage{booktabs}")
    out.append(r"\usepackage{longtable}")
    out.append(r"\usepackage{array}")
    out.append(r"\usepackage{tabularx}")
    out.append(r"\usepackage{graphicx}")
    out.append(r"\usepackage{listings}")
    out.append(r"\usepackage{xcolor}")
    out.append(r"\usepackage{amssymb}")
    out.append(r"\usepackage[")
    out.append("  colorlinks=true,")
    out.append("  linkcolor=blue,")
    out.append("  urlcolor=blue,")
    out.append("  citecolor=blue,")
    out.append("  bookmarks=true,")
    out.append("  bookmarksopen=true")
    out.append(r"]{hyperref}")
    out.append(r"\hypersetup{")
    out.append("  pdftitle={Deliverable 2 - Executive Review II: Enterprise "
               "Architecture and System Implementation},")
    out.append("  pdfauthor={Velez Munoz, Gonzalez Veloza, Ahumada Leon}")
    out.append("}")
    out.append(r"\graphicspath{{docs/deliverable-2/figures/}{figures/}{../figures/}"
               r"{docs/deliverable-2/diagramas-c4/}{diagramas-c4/}"
               r"{docs/deliverable-2/}}")
    out.append(r"\setcounter{secnumdepth}{-2}")
    out.append(r"\setlength{\emergencystretch}{3em}")
    out.append(r"\setlength{\tabcolsep}{5pt}")
    out.append(r"\newcolumntype{L}[1]{>{\raggedright\arraybackslash"
               r"\hyphenpenalty=10000\exhyphenpenalty=10000}p{#1}}")
    out.append(r"\lstset{")
    out.append(r"  basicstyle=\ttfamily\scriptsize,")
    out.append(r"  breaklines=true,")
    out.append(r"  breakatwhitespace=false,")
    out.append(r"  frame=single,")
    out.append(r"  columns=fullflexible,")
    out.append(r"  keepspaces=true,")
    out.append(r"  escapechar=@,")
    out.append(r"  showstringspaces=false")
    out.append("}")
    out.append(r"\newcommand{\mdhfour}[1]{\par\medskip\noindent\textbf{#1}"
               r"\par\nobreak\smallskip}")
    out.append("")
    out.append(r"\begin{document}")
    out.append(r'\shorthandoff{<>"}')
    out.append("")
    # -------- title page --------
    out.append(r"\begin{titlepage}")
    out.append(r"  \centering")
    out.append(r"  \vspace*{1.2cm}")
    out.append("  {\\Large \\textbf{" + inline(title) + "}\\par}")
    out.append(r"  \vspace{0.9cm}")
    if subtitle:
        out.append("  {\\large " + inline(subtitle) + r"\par}")
    out.append(r"  \vspace{1.0cm}")
    out.append("  {\\large " + inline(course) + r"\par}")
    out.append(r"  \vspace{1.4cm}")
    out.append("  {\\large")
    for a in authors:
        out.append("  " + inline(a) + r" \\")
    out.append(r"  \par}")
    out.append(r"  \vspace{1.0cm}")
    out.append("")
    render_title_table(meta_rows, out)
    out.append(r"  \vfill")
    out.append("  {\\large " + inline(date_raw) + r"\par}")
    out.append(r"\end{titlepage}")
    out.append("")
    out.append(r"\tableofcontents")
    out.append(r"\newpage")
    out.append("")

    # -------- body --------
    fig_idx = 0
    for b in body:
        kind = b[0]
        if kind == "heading":
            level, text = b[1], b[2]
            t = inline(text)
            if level == 2:
                out.append(r"\subsection{" + t + "}")
            elif level == 3:
                out.append(r"\subsubsection{" + t + "}")
            else:
                out.append(r"\mdhfour{" + t + "}")
            out.append("")
        elif kind == "para":
            out.append(inline(b[1]))
            out.append("")
        elif kind == "hr":
            out.append(r"\par\medskip\noindent\rule{\linewidth}{0.3pt}\par\medskip")
            out.append("")
        elif kind == "quote":
            out.append(r"\begin{quote}")
            out.append(inline(b[1]))
            out.append(r"\end{quote}")
            out.append("")
        elif kind == "ul":
            out.append(r"\begin{itemize}")
            for it in b[1]:
                out.append(r"  \item " + inline(it))
            out.append(r"\end{itemize}")
            out.append("")
        elif kind == "ol":
            out.append(r"\begin{enumerate}")
            for it in b[1]:
                out.append(r"  \item " + inline(it))
            out.append(r"\end{enumerate}")
            out.append("")
        elif kind == "table":
            render_table(b[1], out)
        elif kind == "code":
            lang, content = b[1], b[2]
            if lang == "mermaid":
                name = FIGURE_NAMES[fig_idx]
                fig_idx += 1
                out.append(r"\begin{center}")
                out.append(r"  \includegraphics[width=\textwidth,"
                           r"height=0.90\textheight,keepaspectratio]{" + name + "}")
                out.append(r"\end{center}")
                out.append("")
            elif lang == "figure":
                # Content is exactly one line: "relative/path.pdf | Caption text".
                spec = content[0] if content else ""
                path, _, caption = spec.partition("|")
                path = path.strip()
                caption = inline(caption.strip())
                out.append(r"\begin{figure}[htbp]")
                out.append(r"  \centering")
                out.append(r"  \includegraphics[width=\textwidth,"
                           r"height=0.92\textheight,keepaspectratio]{" + path + "}")
                out.append(r"  \caption{" + caption + "}")
                out.append(r"\end{figure}")
                out.append("")
            else:
                out.append(r"\begin{lstlisting}")
                out.extend(prep_code(content))
                out.append(r"\end{lstlisting}")
                out.append("")

    out.append(r"\end{document}")
    out.append("")

    OUT.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(out)} lines)")
    print(f"title={title!r}")
    print(f"subtitle={subtitle!r}")
    print(f"authors={authors!r}")
    print(f"date={date_raw!r}")
    print(f"body_blocks={len(body)} mermaid_used={fig_idx}")


if __name__ == "__main__":
    build()
