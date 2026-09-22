"""Read-only resolution of effective Word paragraph and run formatting."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from docx.oxml import parse_xml
from docx.oxml.ns import qn

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
TEXT_TAGS = {qn('w:t'), qn('w:delText')}
_TRUE_VALUES = {'1', 'true', 'on', 'yes'}
_FALSE_VALUES = {'0', 'false', 'off', 'no'}
_VERTICAL_MARKS = {'superscript', 'subscript'}


@dataclass(frozen=True)
class _StyleDefinition:
    style_id: str
    style_type: str | None
    based_on: str | None
    name: str | None
    paragraph_properties: dict[str, Any]
    run_properties: dict[str, Any]


class EffectiveFormatResolver:
    """Resolve Word formatting inheritance without mutating XML nodes."""

    def __init__(self, styles_root: Any | None = None, *, max_depth: int = 32) -> None:
        self._styles_root = styles_root
        self._max_depth = max(1, max_depth)
        self._styles = self._read_styles(styles_root)
        self._default_paragraph_properties = self._read_default_properties(
            styles_root,
            'w:pPrDefault',
            'w:pPr',
        )
        self._default_run_properties = self._read_default_properties(
            styles_root,
            'w:rPrDefault',
            'w:rPr',
        )

    @classmethod
    def from_styles_xml(cls, payload: bytes, *, max_depth: int = 32) -> EffectiveFormatResolver:
        """Build a resolver from one read-only styles.xml payload."""

        return cls(parse_xml(payload), max_depth=max_depth)

    @classmethod
    def empty(cls) -> EffectiveFormatResolver:
        """Return a resolver that uses direct formatting only."""

        return cls()

    def resolve_paragraph(
        self,
        paragraph: Any,
        *,
        paragraph_style_id: str | None,
    ) -> dict[str, Any]:
        """Resolve paragraph and run evidence without changing the input node."""

        direct_ppr = paragraph.find(qn('w:pPr'))
        resolved_style_id = paragraph_style_id or _child_value(direct_ppr, 'w:pStyle')
        style_chain = self._style_chain(resolved_style_id)
        paragraph_properties = dict(self._default_paragraph_properties)
        run_properties = dict(self._default_run_properties)
        for style in style_chain:
            paragraph_properties.update(style.paragraph_properties)
            run_properties.update(style.run_properties)
        paragraph_properties.update(_property_map(direct_ppr))

        run_results: list[dict[str, Any]] = []
        for run in paragraph.iter(qn('w:r')):
            direct_rpr = run.find(qn('w:rPr'))
            character_style_id = _child_value(direct_rpr, 'w:rStyle')
            effective_run_properties = dict(run_properties)
            for style in self._style_chain(character_style_id):
                effective_run_properties.update(style.run_properties)
            effective_run_properties.update(_property_map(direct_rpr))
            values = _format_values(effective_run_properties)
            values['text_length'] = len(_text(run))
            values['style_chain'] = [style.style_id for style in self._style_chain(character_style_id)]
            run_results.append(values)

        base_values = _format_values(run_properties)
        summary = _summarize_runs(run_results, base_values)
        paragraph_values = _paragraph_values(paragraph_properties)
        effective_size = summary['dominant_font_size_pt']
        if effective_size is None:
            effective_size = base_values['font_size_pt']
        effective_bold = base_values['bold']
        if summary['dominant_bold'] is not None:
            effective_bold = summary['dominant_bold']

        return {
            **paragraph_values,
            'font_name': base_values['font_name'],
            'font_size_pt': effective_size,
            'bold': effective_bold,
            'italic': base_values['italic'],
            'color': base_values['color'],
            **summary,
            'style_chain': [style.style_id for style in style_chain],
            'based_on_heading': any(_is_heading_style(style) for style in style_chain),
        }

    def _style_chain(self, style_id: str | None) -> list[_StyleDefinition]:
        chain: list[_StyleDefinition] = []
        visited: set[str] = set()

        def visit(current_id: str | None, depth: int) -> None:
            if not current_id or depth >= self._max_depth or current_id in visited:
                return
            style = self._styles.get(current_id)
            if style is None:
                return
            visited.add(current_id)
            visit(style.based_on, depth + 1)
            chain.append(style)

        visit(style_id, 0)
        return chain

    @staticmethod
    def _read_default_properties(root: Any | None, parent_tag: str, child_tag: str) -> dict[str, Any]:
        if root is None:
            return {}
        defaults = root.find(qn('w:docDefaults'))
        if defaults is None:
            return {}
        parent = defaults.find(qn(parent_tag))
        child = parent.find(qn(child_tag)) if parent is not None else None
        return _property_map(child)

    @staticmethod
    def _read_styles(root: Any | None) -> dict[str, _StyleDefinition]:
        if root is None:
            return {}
        result: dict[str, _StyleDefinition] = {}
        for node in root.findall(qn('w:style')):
            style_id = node.get(qn('w:styleId'))
            if not style_id:
                continue
            based_on = _child_value(node, 'w:basedOn')
            name_node = node.find(qn('w:name'))
            name = name_node.get(qn('w:val')) if name_node is not None else None
            result[style_id] = _StyleDefinition(
                style_id=style_id,
                style_type=node.get(qn('w:type')),
                based_on=based_on,
                name=name,
                paragraph_properties=_property_map(node.find(qn('w:pPr'))),
                run_properties=_property_map(node.find(qn('w:rPr'))),
            )
        return result


def _property_map(node: Any | None) -> dict[str, Any]:
    if node is None:
        return {}
    return {child.tag: child for child in node if isinstance(child.tag, str)}


def _child_value(parent: Any | None, tag: str) -> str | None:
    if parent is None:
        return None
    node = parent.find(qn(tag))
    return node.get(qn('w:val')) if node is not None else None


def _attribute(node: Any | None, attribute: str = 'val') -> str | None:
    if node is None:
        return None
    return node.get(qn('w:' + attribute))


def _boolean(node: Any | None) -> bool | None:
    if node is None:
        return None
    value = _attribute(node)
    if value is None:
        return True
    normalized = value.lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return None


def _font_name(node: Any | None) -> str | None:
    if node is None:
        return None
    for attribute in ('eastAsia', 'hAnsi', 'ascii', 'cs'):
        value = node.get(qn('w:' + attribute))
        if value:
            return value
    return None


def _font_size(node: Any | None) -> float | None:
    value = _attribute(node)
    if value is None:
        return None
    try:
        return float(value) / 2
    except (TypeError, ValueError):
        return None


def _format_values(properties: dict[str, Any]) -> dict[str, Any]:
    size_node = properties.get(qn('w:sz'))
    if size_node is None:
        size_node = properties.get(qn('w:szCs'))
    fonts_node = properties.get(qn('w:rFonts'))
    vert_align = _attribute(properties.get(qn('w:vertAlign')))
    return {
        'font_name': _font_name(fonts_node),
        'font_size_pt': _font_size(size_node),
        'bold': _boolean(properties.get(qn('w:b'))),
        'italic': _boolean(properties.get(qn('w:i'))),
        'color': _attribute(properties.get(qn('w:color'))),
        'vert_align': vert_align,
    }


def _paragraph_values(properties: dict[str, Any]) -> dict[str, Any]:
    outline_value = _attribute(properties.get(qn('w:outlineLvl')))
    try:
        outline_level = int(outline_value) if outline_value is not None else None
    except ValueError:
        outline_level = None
    return {
        'alignment': _attribute(properties.get(qn('w:jc'))),
        'outline_level': outline_level,
        'keep_next': _boolean(properties.get(qn('w:keepNext'))),
        'page_break_before': _boolean(properties.get(qn('w:pageBreakBefore'))),
    }


def _text(node: Any) -> str:
    parts: list[str] = []
    for child in node.iter():
        if child.tag in TEXT_TAGS and child.text:
            parts.append(child.text)
        elif child.tag == qn('w:tab'):
            parts.append('\t')
        elif child.tag == qn('w:br'):
            parts.append('\n')
    return ''.join(parts)


def _summarize_runs(
    runs: list[dict[str, Any]],
    base_values: dict[str, Any],
) -> dict[str, Any]:
    weighted_sizes: defaultdict[float, int] = defaultdict(int)
    total_weight = 0
    all_sizes: list[float] = []
    bold_weight = 0
    for run in runs:
        length = int(run.get('text_length', 0))
        size = run.get('font_size_pt')
        if isinstance(size, (int, float)):
            all_sizes.append(float(size))
        if length <= 0 or run.get('vert_align') in _VERTICAL_MARKS:
            continue
        if not isinstance(size, (int, float)):
            continue
        weighted_sizes[float(size)] += length
        total_weight += length
        if run.get('bold') is True:
            bold_weight += length

    if not weighted_sizes:
        base_size = base_values.get('font_size_pt')
        dominant_size = float(base_size) if isinstance(base_size, (int, float)) else None
        dominant_ratio = None
    else:
        dominant_size, dominant_count = max(
            weighted_sizes.items(),
            key=lambda item: (item[1], -item[0]),
        )
        dominant_ratio = dominant_count / total_weight if total_weight else None

    if total_weight:
        dominant_bold: bool | None = bold_weight * 2 >= total_weight
    else:
        dominant_bold = base_values.get('bold')

    return {
        'dominant_font_size_pt': dominant_size,
        'dominant_font_size_ratio': dominant_ratio,
        'max_font_size_pt': max(all_sizes, default=None),
        'dominant_bold': dominant_bold,
        'run_statistics': {'runs': runs, 'weighted_characters': total_weight},
    }


def _is_heading_style(style: _StyleDefinition) -> bool:
    value = (style.style_id + ' ' + (style.name or '')).replace(' ', '').lower()
    return 'heading' in value
