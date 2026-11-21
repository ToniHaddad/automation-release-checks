"""Helpers to find line numbers in source text."""
from __future__ import annotations

import yaml


def find_line(text: str, needle: str, after_line: int = 0) -> int | None:
    """1-based line of the first line after `after_line` containing needle."""
    for i, line in enumerate(text.splitlines(), start=1):
        if i > after_line and needle in line:
            return i
    return None


def yaml_key_lines(text: str) -> dict[tuple, int]:
    """Map key paths (tuples of str) to 1-based lines for a YAML mapping."""
    out: dict[tuple, int] = {}

    def walk(node, path):
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                if isinstance(k, yaml.ScalarNode):
                    p = path + (str(k.value),)
                    out[p] = k.start_mark.line + 1
                    walk(v, p)

    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return out
    if root is not None:
        walk(root, ())
    return out
