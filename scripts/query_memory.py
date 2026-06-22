#!/usr/bin/env python3
"""Return small relevant snippets from SKILL.md and references/ for role memory."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = [
    ROOT / "SKILL.md",
    *sorted(path for path in (ROOT / "references").glob("*.md") if not path.name.startswith("._")),
]


@dataclass
class Snippet:
    file: Path
    heading: str
    text: str
    score: int


def terms(query: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query) if len(term) > 1]


def split_sections(path: Path) -> list[tuple[str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    sections: list[tuple[str, str]] = []
    current_heading = path.name
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
                current_lines = []
            current_heading = line.lstrip("#").strip() or path.name
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))
    return [(heading, body) for heading, body in sections if body]


def score_section(query_terms: list[str], heading: str, body: str) -> int:
    haystack = f"{heading}\n{body}".lower()
    score = 0
    for term in query_terms:
        count = haystack.count(term)
        if count:
            score += count
            if term in heading.lower():
                score += 3
    return score


def trim(text: str, max_chars: int) -> str:
    compact = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--max-chars", type=int, default=1200)
    parser.add_argument("--file", action="append", help="Restrict search to a file path relative to skill root")
    args = parser.parse_args()

    selected_files = [ROOT / name for name in args.file] if args.file else DEFAULT_FILES
    query_terms = terms(args.query)
    if not query_terms:
        print(json.dumps({"ok": False, "error": "query must contain searchable terms"}))
        return 2

    snippets: list[Snippet] = []
    for path in selected_files:
        if not path.exists() or not path.is_file():
            continue
        for heading, body in split_sections(path):
            score = score_section(query_terms, heading, body)
            if score:
                snippets.append(Snippet(file=path, heading=heading, text=body, score=score))

    snippets.sort(key=lambda item: (-item.score, str(item.file), item.heading))
    results = [
        {
            "id": f"{snippet.file.relative_to(ROOT)}::{snippet.heading}",
            "file": str(snippet.file.relative_to(ROOT)),
            "heading": snippet.heading,
            "score": snippet.score,
            "text": trim(snippet.text, args.max_chars),
        }
        for snippet in snippets[: args.top_k]
    ]
    print(json.dumps({"ok": True, "query": args.query, "results": results}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
