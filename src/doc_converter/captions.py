"""Shared explicit figure/table captions and creator-line vocabulary."""

import re

_CAPTION = re.compile(
    r"^(图|表|Figure|Fig\.?|Table)(?:\s*[一二三四五六七八九十百\d]+|\s*[:：]\s*\S|[ \u3000]{2,}\S)",
    re.I,
)
_CREDIT = re.compile(r"^制\s*(图|表)\s*人\s*[:：][^\r\n]{0,100}$")


def caption_role(text: str) -> str | None:
    """Recognize short, standalone labels without requiring a nearby object."""
    text = text.strip()
    credit = _CREDIT.fullmatch(text)
    if credit:
        return "figure-credit" if credit.group(1) == "图" else "table-credit"
    caption = _CAPTION.match(text)
    if (caption and len(text) <= 80 and "\n" not in text and "\r" not in text
            and not text.endswith(tuple("。；？！!?;"))):
        return "figure-caption" if caption.group(1).lower() in {"图", "figure", "fig", "fig."} else "table-caption"
    return None
