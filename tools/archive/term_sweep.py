#!/usr/bin/env python3
"""One-shot CN/EN terminology unifier for REPORT.md (review item: 統一中英術語密度).

Policy (user): technical terms stay English (kernel, page cache, prefetch, workload,
baseline, B+tree, madvise, readahead, layout, first-query, e2e, hotset, working set...);
NON-technical English words that were randomly Englished revert to Chinese. We touch ONLY
prose: fenced/inline code, markdown link & image URLs, heading lines, and $math$ are
protected so paths like 05_strategy_comparison.png and code spans are never rewritten.
"""
import re, sys

# ordered (longest phrase first); each is a plain non-technical word/phrase -> Chinese
GLOSSARY = [
    ("orders of magnitude", "量級"),
    ("order of magnitude", "量級"),
    ("magnitude", "量級"),
    ("measurement", "量測"),
    ("deployment", "部署"),
    ("comparison", "比較"),
    ("conclusion", "結論"),
    ("validation", "驗證"),
    ("framework", "框架"),
    ("isolation", "隔離"),
    ("recommendation", "建議"),
    ("experiment", "實驗"),
    ("預取", "prefetch"),            # CN technical term -> English, per user rule
]

SENT = "\uE000"          # private-use-area sentinel; never in markdown text
PLACEHOLDER = SENT + "{}" + SENT

def protect(text):
    """Replace protected regions with placeholders; return (masked_text, regions)."""
    regions = []
    def stash(m):
        regions.append(m.group(0))
        return PLACEHOLDER.format(len(regions) - 1)
    text = re.sub(r"```.*?```", stash, text, flags=re.S)   # fenced code
    text = re.sub(r"`[^`\n]*`", stash, text)               # inline code
    text = re.sub(r"\]\([^)]*\)", stash, text)             # markdown link/image URL
    text = re.sub(r"\${1,2}[^$]*\${1,2}", stash, text)     # $math$ / $$math$$
    return text, regions

def restore(text, regions):
    for i, r in enumerate(regions):
        text = text.replace(PLACEHOLDER.format(i), r)
    return text

CJK = r"一-鿿"

def sweep_line(line, counts):
    masked, regions = protect(line)
    for en, zh in GLOSSARY:
        if en in masked:
            counts[en] = counts.get(en, 0) + masked.count(en)
            masked = masked.replace(en, zh)
            # the English word often had separating spaces; drop a stray space only when it
            # now sits between two CJK chars (keep CJK<->Latin spacing intact).
            z = re.escape(zh)
            masked = re.sub(rf"(?<=[{CJK}]) ({z})", r"\1", masked)
            masked = re.sub(rf"({z}) (?=[{CJK}])", r"\1", masked)
    return restore(masked, regions)

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "REPORT.md"
    counts = {}
    out = []
    for line in open(path, encoding="utf-8"):
        # protect heading lines wholesale (English section titles stay English)
        out.append(line if re.match(r"\s*#{1,6}\s", line) else sweep_line(line, counts))
    open(path, "w", encoding="utf-8").write("".join(out))
    table = dict(GLOSSARY)
    for en, _ in GLOSSARY:
        if counts.get(en):
            print(f"  {en:22} -> {table[en]:6} x{counts[en]}")
    print(f"total replacements: {sum(counts.values())}  ({path})")

if __name__ == "__main__":
    main()
