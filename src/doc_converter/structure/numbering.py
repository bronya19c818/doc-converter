"""Literal numbering facts; no role assignment or format evidence."""
from __future__ import annotations

import re
import unicodedata

NUMBERING_PATTERNS = (
    ("CHAPTER", re.compile(r"^第\s*[一二三四五六七八九十百\d]+\s*章")),
    ("SECTION", re.compile(r"^第\s*[一二三四五六七八九十百\d]+\s*节")),
    ("CN_ENUM", re.compile(r"^[一二三四五六七八九十百]+、")),
    ("CN_BRACKET", re.compile(r"^[（(][一二三四五六七八九十百]+[）)]")),
    ("DECIMAL", re.compile(r"^\d+(?:\.\d+)+(?=\s|[^\d.])")),
    ("ARABIC_ENUM", re.compile(r"^\d+[.、](?=\s|[^\d.])|^\d+\s+")),
    ("ARABIC_BRACKET", re.compile(r"^[（(]\d+[）)]")),
    ("CIRCLED", re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]")),
    ("ARABIC_ENUM", re.compile(r"^\d{1,2}(?=[\u4e00-\u9fff])")),
)


def ordinal(token: str | None) -> list[int]:
    if not token:
        return []
    digits = re.findall(r"\d+", token)
    if digits:
        return [int(n) for n in digits]
    if token[0] in "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳":
        return [int(unicodedata.numeric(token[0]))]
    value, current = 0, 0
    numbers = {c: i for i, c in enumerate("零一二三四五六七八九")}
    for c in token:
        if c in numbers:
            current = numbers[c]
        elif c in "十百":
            value += (current or 1) * (10 if c == "十" else 100)
            current = 0
    return [value + current] if value + current else []


def numbering(text: str) -> tuple[str | None, int | None, str | None]:
    for family, pattern in NUMBERING_PATTERNS:
        match = pattern.match(text)
        if match:
            token = match.group().strip()
            depth = token.count(".") + 1 if family == "DECIMAL" else None
            return family, depth, token
    return None, None, None

