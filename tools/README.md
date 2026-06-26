# tools/

Standalone utilities — not part of the experiment run path (that's `run_experiment.py`),
just helpers run by hand.

| Tool | What it does |
|---|---|
| [md_to_pdf.py](md_to_pdf.py) | Render a Markdown file to PDF via the `markdown-pdf` package — handles CJK text (embeds a built-in font), inline figures, and `$$…$$` math (rendered to images). Defaults to `REPORT.md` → `REPORT.pdf`. |

**Run from the repo root** so relative paths (`REPORT.md`, `figures/out/*.png`) resolve, and
outputs land at the root:

```sh
python3 tools/md_to_pdf.py                 # REPORT.md -> REPORT.pdf
python3 tools/md_to_pdf.py in.md out.pdf
```
