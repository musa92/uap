#!/usr/bin/env python3
"""Verify every relative markdown link and section anchor resolves.

External URLs are not fetched; a network-dependent CI check is a flaky CI check.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
HEADING = re.compile(r'^#{1,6}\s+(.*)$', re.M)


def slug(text: str) -> str:
    text = re.sub(r'`|\*|_', '', text).strip().lower()
    return re.sub(r'[^a-z0-9\s-]', '', text).replace(' ', '-')


def anchors(path: pathlib.Path) -> set[str]:
    return {slug(h) for h in HEADING.findall(path.read_text())}


def main() -> int:
    failures = []
    checked = 0
    for md in sorted(ROOT.rglob("*.md")):
        if any(p in md.parts for p in (".git", "node_modules", "__pycache__")):
            continue
        for target in LINK.findall(md.read_text()):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            checked += 1
            frag = ""
            if "#" in target:
                target, frag = target.split("#", 1)
            if target:
                resolved = (md.parent / target).resolve()
                if not resolved.exists():
                    failures.append(f"{md.relative_to(ROOT)}: missing target {target}")
                    continue
            else:
                resolved = md
            if frag and resolved.suffix == ".md" and frag not in anchors(resolved):
                failures.append(f"{md.relative_to(ROOT)}: no anchor #{frag} in {resolved.name}")

    for f in failures:
        print(f"  FAIL  {f}")
    print(f"\n  {checked} relative links checked, {len(failures)} broken\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
