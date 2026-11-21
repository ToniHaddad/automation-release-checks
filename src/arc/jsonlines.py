"""A small JSON parser that also records the line of every key and list item.

The standard library parser gives errors with a line but values without one.
Findings need the line of a node type or a token, so this parser returns both.
"""
from __future__ import annotations

import bisect
import json
import re

_WS = " \t\r\n"
_NUM = re.compile(r"-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?")
MAX_DEPTH = 200


class JSONLineError(ValueError):
    def __init__(self, msg: str, line: int):
        super().__init__(msg)
        self.msg = msg
        self.line = line


def parse(text: str) -> tuple[object, dict[tuple, int]]:
    """Return (value, lines). lines maps a path tuple (keys and list indexes) to a 1-based line."""
    starts = [0] + [i + 1 for i, c in enumerate(text) if c == "\n"]
    n = len(text)
    lines: dict[tuple, int] = {}
    pos = 0

    def line_of(p: int) -> int:
        return bisect.bisect_right(starts, max(0, min(p, n - 1) if n else 0))

    def fail(msg: str, p: int):
        raise JSONLineError(msg, line_of(p))

    def skip():
        nonlocal pos
        while pos < n and text[pos] in _WS:
            pos += 1

    def string() -> str:
        nonlocal pos
        start = pos
        pos += 1
        while pos < n:
            c = text[pos]
            if c == "\\":
                pos += 2
                continue
            if c == '"':
                pos += 1
                try:
                    return json.loads(text[start:pos])
                except ValueError:
                    fail("invalid string", start)
            if c == "\n":
                fail("unterminated string", start)
            pos += 1
        fail("unterminated string", start)

    def value(path: tuple, depth: int):
        nonlocal pos
        if depth > MAX_DEPTH:
            fail("nested too deeply", pos)
        skip()
        if pos >= n:
            fail("unexpected end of file", n - 1)
        lines.setdefault(path, line_of(pos))
        c = text[pos]
        if c == "{":
            pos += 1
            obj = {}
            skip()
            if pos < n and text[pos] == "}":
                pos += 1
                return obj
            while True:
                skip()
                if pos >= n:
                    fail("unexpected end of file inside an object", n - 1)
                if text[pos] != '"':
                    fail("expected a quoted key", pos)
                kpos = pos
                key = string()
                lines[path + (key,)] = line_of(kpos)
                skip()
                if pos >= n or text[pos] != ":":
                    fail("expected ':' after key", pos)
                pos += 1
                obj[key] = value(path + (key,), depth + 1)
                skip()
                if pos >= n:
                    fail("unexpected end of file inside an object", n - 1)
                if text[pos] == ",":
                    pos += 1
                    continue
                if text[pos] == "}":
                    pos += 1
                    return obj
                fail("expected ',' or '}'", pos)
        if c == "[":
            pos += 1
            arr = []
            skip()
            if pos < n and text[pos] == "]":
                pos += 1
                return arr
            while True:
                arr.append(value(path + (len(arr),), depth + 1))
                skip()
                if pos >= n:
                    fail("unexpected end of file inside a list", n - 1)
                if text[pos] == ",":
                    pos += 1
                    continue
                if text[pos] == "]":
                    pos += 1
                    return arr
                fail("expected ',' or ']'", pos)
        if c == '"':
            return string()
        for lit, val in (("true", True), ("false", False), ("null", None)):
            if text.startswith(lit, pos):
                pos += len(lit)
                return val
        m = _NUM.match(text, pos)
        if m:
            pos = m.end()
            return json.loads(m.group(0))
        fail(f"unexpected character {c!r}", pos)

    try:
        result = value((), 0)
        skip()
        if pos < n:
            fail("extra data after the JSON value", pos)
    except RecursionError:
        raise JSONLineError("nested too deeply", 1) from None
    return result, lines
