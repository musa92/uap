#!/usr/bin/env python3
"""Render every schema in source/schemas to a reference page.

The schemas are the source of truth. Hand-written reference docs drift from
them within a week; generated ones cannot. Run by `make docs`, and CI fails if
the generated output is stale, so a schema change without a docs rebuild does
not merge.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "source" / "schemas"
OUT = ROOT / "docs" / "reference"
BASE = "https://uap.dev/schemas/"


def type_of(prop: dict) -> str:
    if "$ref" in prop:
        ref = prop["$ref"]
        target = ref.split("#")[0].split("/")[-1].replace(".json", "") or ref
        frag = ref.split("#")[1] if "#" in ref else ""
        name = frag.split("/")[-1] if frag else target
        return f"[`{name}`]({ref_link(ref)})"
    if "enum" in prop:
        vals = ", ".join(f"`{v}`" for v in prop["enum"][:6])
        more = f", … ({len(prop['enum'])} values)" if len(prop["enum"]) > 6 else ""
        return f"enum: {vals}{more}"
    if "const" in prop:
        return f"const `{json.dumps(prop['const'])}`"
    t = prop.get("type")
    if isinstance(t, list):
        t = " \\| ".join(t)
    if t == "array" and "items" in prop:
        return f"array of {type_of(prop['items'])}"
    if t == "string" and "pattern" in prop:
        return f"string `/{prop['pattern'][:40]}{'…' if len(prop['pattern']) > 40 else ''}/`"
    if t == "string" and "format" in prop:
        return f"string ({prop['format']})"
    return t or ("object" if "properties" in prop else "any")


def ref_link(ref: str) -> str:
    path = ref.split("#")[0]
    if not path:
        return "#definitions"
    stem = pathlib.PurePosixPath(path).stem
    return f"{stem}.md"


def constraints(prop: dict) -> str:
    bits = []
    for k in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems",
              "multipleOf", "default"):
        if k in prop:
            bits.append(f"{k} {json.dumps(prop[k])}")
    return ", ".join(bits)


def render_comment(comment: str) -> list[str]:
    """Rationale from `$comment`, split into prose and preformatted runs.

    Schema comments mix prose with column-aligned tables (a CPM band, an enum
    legend). Prose becomes a blockquote; any run of lines with leading
    whitespace is emitted as a fenced text block so the alignment survives and
    markdownlint does not read it as multiple spaces after the quote marker.
    """
    out, prose, pre = [], [], []
    last = {"kind": None}

    def flush_prose():
        if prose:
            if last["kind"] == "prose":
                out[-1] = ">"            # continue the quote across paragraphs
            out.append("> **Rationale.** " + prose[0] if not out else "> " + prose[0])
            out.extend("> " + l for l in prose[1:])
            out.append("")
            prose.clear(); last["kind"] = "prose"

    def flush_pre():
        if pre:
            out.extend(["```text", *pre, "```", ""])
            pre.clear(); last["kind"] = "pre"

    # A line is preformatted if it is indented or column-aligned: any leading
    # whitespace, or a run of two-plus spaces between non-space characters.
    aligned = re.compile(r"\S {2,}\S")

    for line in comment.splitlines():
        if line.strip() and (line[0].isspace() or aligned.search(line)):
            flush_prose(); pre.append(line.rstrip())
        elif line.strip():
            flush_pre(); prose.append(line.strip())
        else:
            flush_prose(); flush_pre()
    flush_prose(); flush_pre()
    if out and not out[0].startswith("> **Rationale.**"):
        out.insert(0, "> **Rationale.**"); out.insert(1, "")
    return out


def render_properties(obj: dict, required: list, depth: int = 0) -> list[str]:
    lines = ["| Property | Type | Required | Description |", "|---|---|---|---|"]
    for name, prop in (obj.get("properties") or {}).items():
        req = "yes" if name in required else ""
        desc = (prop.get("description") or "").replace("\n", " ").replace("|", "\\|")
        cons = constraints(prop)
        if cons:
            desc = f"{desc} *({cons})*" if desc else f"*({cons})*"
        lines.append(f"| `{name}` | {type_of(prop)} | {req} | {desc} |")
    return lines


def render_schema(path: pathlib.Path) -> str:
    doc = json.loads(path.read_text())
    rel = path.relative_to(SRC).as_posix()
    out = [f"# {doc.get('title', path.stem)}", ""]

    meta = []
    if "name" in doc:
        meta.append(f"**Name** `{doc['name']}`")
    if "version" in doc:
        meta.append(f"**Version** `{doc['version']}`")
    meta.append(f"**Schema** [`{rel}`]({BASE}{rel})")
    out.append(" · ".join(meta))
    out.append("")

    if doc.get("description"):
        out += [doc["description"], ""]

    if doc.get("$comment"):
        out += render_comment(doc["$comment"])

    if doc.get("properties"):
        out += ["## Properties", ""]
        out += render_properties(doc, doc.get("required") or [])
        out.append("")

    if doc.get("allOf"):
        conds = [c for c in doc["allOf"] if "if" in c]
        if conds:
            out += ["## Conditional constraints", ""]
            for c in conds:
                title = c.get("title") or "Constraint"
                why = (c.get("$comment") or c.get("description") or "").strip()
                # A bare if/then with no prose still deserves a line, but never
                # a trailing space after the title.
                out += [f"- **{title}.** {why}" if why else f"- **{title}.**"]
            out.append("")

    if doc.get("$defs"):
        out += ["## Definitions", ""]
        for dname, d in doc["$defs"].items():
            out += [f"### `{dname}`", ""]
            if d.get("description"):
                out += [d["description"], ""]
            if d.get("$comment"):
                out += render_comment(d["$comment"])
            if d.get("properties"):
                out += render_properties(d, d.get("required") or [])
                out.append("")
            elif "enum" in d:
                out += ["Values: " + ", ".join(f"`{v}`" for v in d["enum"]), ""]
            elif "type" in d:
                out += [f"Type: `{d['type']}`" + (f", pattern `{d['pattern']}`" if "pattern" in d else ""), ""]

    out += ["---", "", f"*Generated from `source/schemas/{rel}`. Do not edit; run `make docs`.*", ""]
    return "\n".join(out)


def render_index(pages: list[tuple[str, str, str]]) -> str:
    groups: dict[str, list] = {}
    for rel, title, desc in pages:
        group = rel.split("/")[0] if "/" in rel else "meta"
        groups.setdefault(group, []).append((rel, title, desc))
    order = ["meta", "supply", "demand", "settlement", "common"]
    labels = {"meta": "Protocol metadata", "supply": "Supply side", "demand": "Demand side",
              "settlement": "Settlement", "common": "Common types"}
    out = ["# Schema reference", "",
           "Every wire object in the protocol, generated from `source/schemas/`. "
           "The schemas are normative; this page is a rendering of them.", ""]
    for g in order + [g for g in groups if g not in order]:
        if g not in groups:
            continue
        out += [f"## {labels.get(g, g.title())}", ""]
        for rel, title, desc in sorted(groups[g]):
            stem = pathlib.PurePosixPath(rel).stem
            first = (desc or "").split(". ")[0].rstrip(".")
            out.append(f"- [**{title}**]({stem}.md) — {first}." if first else f"- [**{title}**]({stem}.md)")
        out.append("")
    return "\n".join(out)


def main(check: bool = False) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pages, stale = [], []
    for path in sorted(SRC.rglob("*.json")):
        doc = json.loads(path.read_text())
        rel = path.relative_to(SRC).as_posix()
        pages.append((rel, doc.get("title", path.stem), doc.get("description", "")))
        target = OUT / f"{path.stem}.md"
        content = render_schema(path)
        if check:
            if not target.exists() or target.read_text() != content:
                stale.append(str(target.relative_to(ROOT)))
        else:
            target.write_text(content)
    index = render_index(pages)
    if check:
        idx = OUT / "index.md"
        if not idx.exists() or idx.read_text() != index:
            stale.append(str(idx.relative_to(ROOT)))
        if stale:
            print("  stale generated docs (run `make docs`):")
            for s in stale:
                print(f"    {s}")
            return 1
        print(f"  {len(pages)} schema reference pages up to date")
        return 0
    (OUT / "index.md").write_text(index)
    print(f"  rendered {len(pages)} schema reference pages to docs/reference/")
    return 0


if __name__ == "__main__":
    sys.exit(main(check="--check" in sys.argv))
