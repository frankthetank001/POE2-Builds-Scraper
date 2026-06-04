"""Schema-less Protocol Buffers wire-format decoder.

poe.ninja's PoE2 builds `/search` endpoint returns `application/x-protobuf` with no
published `.proto`. We don't need one: the payload is a columnar result table and we
only want two string columns (`name` = character, `account` = "Name-1234"). This module
walks the raw wire format generically and reconstructs the nested structure enough to
pull those columns.

Verified against a real captured payload (tests/fixtures/search_runesofaldur.pb):
100 builds, `name` and `account` columns align 1:1.
"""

from __future__ import annotations

from typing import Any


def read_varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = 0
    result = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, i
        shift += 7
    raise ValueError("varint overran buffer")


def _looks_like_message(buf: bytes) -> bool:
    """True if `buf` cleanly parses as a protobuf message (consumes exactly)."""
    i, n = 0, len(buf)
    if n == 0:
        return False
    try:
        while i < n:
            tag, i = read_varint(buf, i)
            wt = tag & 7
            if wt == 0:
                _, i = read_varint(buf, i)
            elif wt == 1:
                i += 8
            elif wt == 5:
                i += 4
            elif wt == 2:
                ln, i = read_varint(buf, i)
                i += ln
            else:
                return False
        return i == n
    except Exception:
        return False


def _is_clean_text(s: str) -> bool:
    return bool(s) and all(31 < ord(c) < 0xFFFF for c in s)


def parse(buf: bytes, depth: int = 0, max_depth: int = 8) -> list[tuple[int, Any]]:
    """Decode a protobuf message into a list of (field_number, value).

    value is: a nested `list` (sub-message), a `str` (length-delimited text),
    `bytes` (length-delimited binary), or `int` (varint). Repeated fields appear
    as multiple entries with the same field_number, in wire order.

    A length-delimited chunk is treated as text first (preferred) so that short
    account names that happen to parse as valid protobuf are not mis-recursed.
    """
    out: list[tuple[int, Any]] = []
    i, n = 0, len(buf)
    while i < n:
        try:
            tag, i = read_varint(buf, i)
        except Exception:
            break
        field_no = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                v, i = read_varint(buf, i)
            except Exception:
                break
            out.append((field_no, v))
        elif wt == 1:
            i += 8
            out.append((field_no, "<f64>"))
        elif wt == 5:
            i += 4
            out.append((field_no, "<f32>"))
        elif wt == 2:
            try:
                ln, i = read_varint(buf, i)
            except Exception:
                break
            chunk = buf[i : i + ln]
            i += ln
            text: str | None = None
            try:
                cand = chunk.decode("utf-8")
                if _is_clean_text(cand):
                    text = cand
            except Exception:
                text = None
            if text is not None:
                out.append((field_no, text))
            elif depth < max_depth and ln > 1 and _looks_like_message(chunk):
                out.append((field_no, parse(chunk, depth + 1, max_depth)))
            else:
                out.append((field_no, chunk))
        else:
            break
    return out


def fields(node: list[tuple[int, Any]], field_no: int) -> list[Any]:
    """All values for a field number within a parsed message node."""
    return [v for (f, v) in node if f == field_no]
