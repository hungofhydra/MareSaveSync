"""Comparing the contents of one file (text/JSON line diff or hex diff)."""
from __future__ import annotations

import difflib
import json


def decode_text(data: bytes):
    """Return (text, was_pretty_printed_json) or None if the data looks binary."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            text = data.decode("utf-16")
        except UnicodeDecodeError:
            return None
    else:
        if b"\x00" in data[:8192]:
            return None
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None
    s = text.strip()
    if s and s[0] in "{[":
        try:
            return json.dumps(json.loads(s), indent=2, ensure_ascii=False), True
        except ValueError:
            pass
    return text, False


def text_diff_lines(cloud_text: str, local_text: str, context: int = 3, limit: int = 20000):
    out = []
    for ln in difflib.unified_diff(cloud_text.splitlines(), local_text.splitlines(),
                                   "cloud", "this PC", lineterm="", n=context):
        if ln.startswith(("---", "+++")):
            tag = "meta"
        elif ln.startswith("@@"):
            tag = "hunk"
        elif ln.startswith("+"):
            tag = "add"
        elif ln.startswith("-"):
            tag = "rem"
        else:
            tag = ""
        out.append((ln, tag))
        if len(out) >= limit:
            out.append(("... diff truncated ...", "meta"))
            break
    return out


def _hex(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b).ljust(47)


def _asc(b: bytes) -> str:
    return "".join(chr(x) if 32 <= x < 127 else "." for x in b)


def hex_diff_lines(cloud: bytes, local: bytes, context: int = 2, max_rows: int = 300):
    """Return (summary, [(line, tag), ...]) comparing two binary blobs."""
    n = max(len(cloud), len(local))
    rows = (n + 15) // 16
    diff_rows = [r for r in range(rows) if cloud[r * 16:r * 16 + 16] != local[r * 16:r * 16 + 16]]
    ndiff = sum(1 for x, y in zip(cloud, local) if x != y) + abs(len(cloud) - len(local))
    first = next((i for i, (x, y) in enumerate(zip(cloud, local)) if x != y), None)
    if first is None and len(cloud) != len(local):
        first = min(len(cloud), len(local))
    if first is None:
        return "Contents are identical.", []
    summary = (f"{ndiff:,} byte(s) differ · first difference at offset 0x{first:x} ({first:,}) · "
               f"cloud {len(cloud):,} B vs this PC {len(local):,} B")
    show = set()
    for r in diff_rows:
        show.update(k for k in range(r - context, r + context + 1) if 0 <= k < rows)
    lines, prev, shown = [], None, 0
    for r in sorted(show):
        if prev is not None and r != prev + 1:
            lines.append(("   ...", "meta"))
        a, b = cloud[r * 16:r * 16 + 16], local[r * 16:r * 16 + 16]
        if a == b:
            lines.append((f"{r * 16:08x}         {_hex(a)}  {_asc(a)}", ""))
        else:
            lines.append((f"{r * 16:08x}  cloud  {_hex(a)}  {_asc(a)}", "rem"))
            lines.append((f"{'':8}  PC     {_hex(b)}  {_asc(b)}", "add"))
            shown += 1
        prev = r
        if shown >= max_rows:
            lines.append(("   ... more differences not shown", "meta"))
            break
    return summary, lines
