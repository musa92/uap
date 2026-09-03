"""RFC 8785 JSON Canonicalization Scheme.

Every signature and digest in UAP is computed over the canonical form produced
here. SPEC.md §4.3 requires signatures without defining a canonicalization rule;
absent one, two conformant serializers emit different bytes for the same object
and every cross-implementation verification fails.

Conformance is exact-bytes. `test_canonical.py` carries the RFC 8785 vectors.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal

__all__ = ["canonicalize", "serialize"]

_ESCAPES = {
    0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r",
    0x22: '\\"', 0x5C: "\\\\",
}


def _number(value: float | int) -> str:
    """Serialize per ECMAScript Number::toString, as RFC 8785 §3.2.2.1 requires."""
    if isinstance(value, bool):
        raise TypeError("bool is not a number")
    if isinstance(value, int):
        return str(value)
    if math.isnan(value) or math.isinf(value):
        raise ValueError("NaN and Infinity are not representable in JSON")
    if value == 0:
        return "0"  # RFC 8785 normalizes -0 to 0

    sign = "-" if value < 0 else ""
    digits_tuple = Decimal(repr(abs(value))).as_tuple()
    digits = "".join(map(str, digits_tuple.digits))
    exponent = digits_tuple.exponent

    stripped = digits.rstrip("0") or "0"
    exponent += len(digits) - len(stripped)
    digits, k = stripped, len(stripped)
    n = exponent + k  # value == 0.digits * 10**n

    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * -n + digits
    exp = n - 1
    mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
    return f"{sign}{mantissa}e{'+' if exp >= 0 else '-'}{abs(exp)}"


def _string(value: str) -> str:
    out = ['"']
    for ch in value:
        cp = ord(ch)
        if cp in _ESCAPES:
            out.append(_ESCAPES[cp])
        elif cp < 0x20:
            out.append(f"\\u{cp:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _sort_key(key: str) -> tuple[int, ...]:
    """Sort by UTF-16 code unit, not by code point.

    The two orders disagree above the BMP: a supplementary character sorts
    before U+E000 as surrogate pairs but after it as code points.
    """
    return tuple(key.encode("utf-16-be"))


def _write(value, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, (int, float)):
        out.append(_number(value))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _write(item, out)
        out.append("]")
    elif isinstance(value, dict):
        out.append("{")
        for i, key in enumerate(sorted(value, key=_sort_key)):
            if not isinstance(key, str):
                raise TypeError(f"object keys MUST be strings, got {type(key).__name__}")
            if i:
                out.append(",")
            out.append(_string(key))
            out.append(":")
            _write(value[key], out)
        out.append("}")
    else:
        raise TypeError(f"{type(value).__name__} is not JSON-serializable")


def serialize(value) -> str:
    """Return the RFC 8785 canonical JSON text for `value`."""
    out: list[str] = []
    _write(value, out)
    return "".join(out)


def canonicalize(value) -> bytes:
    """Return the RFC 8785 canonical JSON bytes for `value`."""
    return serialize(value).encode("utf-8")


def loads(text: str | bytes):
    """Parse JSON, rejecting duplicate object keys.

    A duplicate key is accepted by most parsers and silently resolved
    last-wins, which lets a signed object and its verified form differ.
    """
    def _no_duplicates(pairs):
        seen = {}
        for key, val in pairs:
            if key in seen:
                raise ValueError(f"duplicate object key {key!r}")
            seen[key] = val
        return seen

    return json.loads(text, object_pairs_hook=_no_duplicates)
