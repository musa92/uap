#!/usr/bin/env python3
"""Enforce canonical spelling of names a spellchecker structurally cannot catch.

cspell tokenises on case boundaries, so `openRTB` reads as "open" + "RTB" and
passes, and `Open RTB` is two valid words. Those are the gaps this closes.

Scope is deliberately narrow. An earlier and broader version of this script
produced 76 findings of which almost all were correct: `sha256:` is the digest
format defined in SPEC.md §4.4, `ed25519` is legitimate inside a key id such as
`uax-ed25519-2026-08`, and title case is correct in a table header. A check that
cries wolf teaches reviewers to skip it, so every rule here is one where there
is no context in which the flagged form is right.

Prose only: code fences, inline spans, URLs and identifiers are skipped.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# canonical, pattern, why it can never be correct
RULES: list[tuple[str, str, str]] = [
    ("OpenRTB",      r"\b(?:Open[- ]RTB|openRTB|OpenRtb|OPENRTB)\b",
     "IAB Tech Lab spells it OpenRTB, one word"),
    ("AdSense",      r"\b(?:Ad[- ]Sense|AdSence|Adsence)\b",
     "Google spells it AdSense, one word"),
    ("AdCP",         r"\b(?:Ad CP|AdCp|ADCP|adcp)\b",
     "AgenticAdvertising.org spells it AdCP"),
    ("IAB Tech Lab", r"\b(?:IAB ?TechLab|Iab Tech Lab|IAB tech lab)\b",
     "the organisation's own spelling"),
    ("JavaScript",   r"\bJavascript\b",
     "Oracle spells it JavaScript"),
    ("GitHub",       r"\bGithub\b",
     "GitHub spells it GitHub"),
    ("OpenRTB 2.6",  r"\bOpenRTB ?2\.6\.\d",
     "there is no OpenRTB 2.6.x; the version is 2.6"),
]

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "site"}
SKIP_FILES = {"package-lock.json", "check_terminology.py"}
FENCE = re.compile(r"```.*?```", re.S)
SPAN = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+")


def prose(text: str) -> str:
    """Blank non-prose while preserving offsets, so line numbers stay true."""
    blank = lambda m: " " * len(m.group(0))          # noqa: E731
    for pat in (FENCE, SPAN, URL):
        text = pat.sub(blank, text)
    return text


def check_rules_are_sane() -> list[str]:
    """A rule that matches its own canonical form reports every correct use.

    Two rules did exactly that while this file was being written, so the
    invariant is asserted rather than remembered.
    """
    return [f"rule {c!r} matches its own canonical form"
            for c, pattern, _ in RULES if re.search(pattern, c)]


def main() -> int:
    broken = check_rules_are_sane()
    for b in broken:
        print(f"  BROKEN RULE  {b}")
    if broken:
        return 1

    findings: list[tuple[str, int, str, str, str]] = []
    checked = 0

    for path in sorted(ROOT.rglob("*.md")):
        if any(p in SKIP_DIRS for p in path.parts) or path.name in SKIP_FILES:
            continue
        try:
            text = prose(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
        checked += 1
        rel = str(path.relative_to(ROOT))
        for canonical, pattern, why in RULES:
            for m in re.finditer(pattern, text):
                findings.append((rel, text[: m.start()].count("\n") + 1,
                                 m.group(0), canonical, why))

    for rel, line, found, canonical, why in findings:
        print(f"  FAIL  {rel}:{line}  {found!r} should be {canonical!r} — {why}")

    print(f"\n  {checked} markdown files, {len(RULES)} rules, "
          f"{len(findings)} violation(s)\n")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
