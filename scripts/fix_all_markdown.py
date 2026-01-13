import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD_DIR = ROOT / "FILE MD"

# Regexes
FENCE_TEXT = re.compile(r"^```text\s*$", re.M)
ONLY_EMPH = re.compile(r"^\s*([*_]{1,3})([^\n*_].*?)\1\s*$", re.M)
# Add blank line before/after fenced code blocks
FENCE_OPEN = re.compile(r"(?m)(?<!\n)\n```[a-zA-Z0-9_-]*\n")
FENCE_CLOSE = re.compile(r"(?m)\n```(?!\n)\n?([^`])")

# Simpler robust approach for blanks:
BEFORE_FENCE = re.compile(r"(?m)([^\n])\n```")
AFTER_FENCE = re.compile(r"(?m)```\n([^\n])")

changed_files = 0

for path in MD_DIR.rglob("*.md"):
    text = path.read_text(encoding="utf-8")
    orig = text

    # 1) Replace any closing or opening '```text' with plain '```'
    text = FENCE_TEXT.sub("```", text)

    # 2) Ensure blank line before/after fenced code blocks
    # before
    text = BEFORE_FENCE.sub(r"\1\n\n```", text)
    # after
    text = AFTER_FENCE.sub(r"```\n\n\1", text)

    # 3) Convert lines that are only emphasis into plain text (MD036)
    text = ONLY_EMPH.sub(r"\2", text)

    if text != orig:
        path.write_text(text, encoding="utf-8")
        changed_files += 1
        print(f"Fixed: {path.relative_to(ROOT)}")

print(f"Done. Updated {changed_files} Markdown files.")
