"""Policy projections of character styles; original definitions stay intact."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from doc_converter.docx_direct.ooxml_patch import parse_xml_payload, serialize_xml_payload


def _signature(node: Any) -> tuple[Any, ...]:
    """Compare XML content independently of inherited namespace declarations."""
    return (
        node.tag,
        tuple(sorted(node.attrib.items())),
        node.text,
        tuple(_signature(child) for child in node),
    )


class CharacterStyleProjector:
    """Filter overridden visual properties through an entire basedOn chain."""

    def __init__(self, payload: bytes) -> None:
        self.original_payload = payload
        self.root = parse_xml_payload(payload)
        self.styles = {n.get(qn("w:styleId")): n for n in self.root.findall(qn("w:style"))}
        self.cache: dict[tuple[str, frozenset[str]], str] = {}
        self._removed_properties: dict[tuple[str, frozenset[str]], dict[str, int]] = {}
        self.inserted_ids: list[str] = []

    def project(self, style_id: str, removed: frozenset[str]) -> str | None:
        """Return a safe projected ID, or None for unresolved/cyclic inheritance."""

        key = (style_id, removed)
        if key in self.cache:
            return self.cache[key]
        chain: list[Any] = []
        visited: set[str] = set()
        current: str | None = style_id
        while current:
            source = self.styles.get(current)
            if source is None or source.get(qn("w:type")) != "character" or current in visited:
                return None
            if len(chain) >= 64:
                return None
            visited.add(current)
            chain.append(source)
            parent = source.find(qn("w:basedOn"))
            current = parent.get(qn("w:val")) if parent is not None else None
        parent_id: str | None = None
        removed_properties: Counter[str] = Counter()
        for source in reversed(chain):
            original_id = source.get(qn("w:styleId"))
            properties = source.find(qn("w:rPr"))
            if properties is not None:
                for child in properties:
                    tag = child.tag.rsplit("}", 1)[-1]
                    if tag in removed:
                        removed_properties[tag] += 1
            overrides = properties is not None and any(
                properties.find(qn("w:" + tag)) is not None for tag in removed
            )
            parent = source.find(qn("w:basedOn"))
            parent_changed = parent is not None and parent.get(qn("w:val")) != parent_id
            if not overrides and not parent_changed:
                parent_id = original_id
                continue
            projected = deepcopy(source)
            properties = projected.find(qn("w:rPr"))
            if properties is not None:
                for tag in removed:
                    for n in properties.findall(qn("w:" + tag)):
                        properties.remove(n)
            projected_parent = projected.find(qn("w:basedOn"))
            if projected_parent is not None and parent_id:
                projected_parent.set(qn("w:val"), parent_id)
            # Content-derived IDs avoid collisions with unrelated DC or source styles.
            digest = sha256(repr(_signature(projected)).encode("utf-8")).hexdigest()[:20]
            projected_id = "DC_PolicyChar_" + digest
            projected.set(qn("w:styleId"), projected_id)
            name = projected.find(qn("w:name"))
            if name is not None:
                name.set(qn("w:val"), projected_id)
            existing = self.styles.get(projected_id)
            if existing is not None and _signature(existing) != _signature(projected):
                return None
            if existing is None:
                self.root.append(projected)
                self.styles[projected_id] = projected
                self.inserted_ids.append(projected_id)
            parent_id = projected_id
        if parent_id:
            self.cache[key] = parent_id
            self._removed_properties[key] = dict(removed_properties)
        return parent_id

    def removed_properties(self, style_id: str, removed: frozenset[str]) -> dict[str, int]:
        """Filtered inheritance-node counts for one run's successful projection."""
        return dict(self._removed_properties.get((style_id, removed), {}))

    def rebase(self, style_id: str | None, target: str, removed: frozenset[str]) -> str | None:
        """Retain semantic inheritance layers on an inline role, with stable IDs.

        Stop at the target base on repeat conversions: its new StylePack font
        must remain inherited rather than copied or projected away.
        """
        chain: list[Any] = []
        visited: set[str] = set()
        current = style_id
        while current and current != target:
            source = self.styles.get(current)
            if current in visited or len(chain) >= 64 or source is None:
                return None
            if source.get(qn("w:type")) != "character":
                return None
            visited.add(current)
            chain.append(source)
            parent = source.find(qn("w:basedOn"))
            current = parent.get(qn("w:val")) if parent is not None else None
        # A previously rebased chain already inherits the managed content role.
        # Its font follows A→B through that base; do not mint another chain.
        if current == target and all(
            not any(n.tag.rsplit("}", 1)[-1] in removed for n in source.find(qn("w:rPr")))
            for source in chain if source.find(qn("w:rPr")) is not None
        ):
            return style_id or target
        parent_id = target
        removed_properties: Counter[str] = Counter()
        for source in reversed(chain):
            style = deepcopy(source)
            props = style.find(qn("w:rPr"))
            if props is not None:
                for n in list(props):
                    if n.tag.rsplit("}", 1)[-1] in removed | {"rStyle"}:
                        removed_properties[n.tag.rsplit("}", 1)[-1]] += 1
                        props.remove(n)
            if props is None or not len(props):
                continue
            base = style.find(qn("w:basedOn"))
            if base is None:
                base = OxmlElement("w:basedOn")
                style.insert(0, base)
            base.set(qn("w:val"), parent_id)
            sid = "DC_PolicyChar_" + sha256(repr(_signature(style)).encode()).hexdigest()[:20]
            style.set(qn("w:styleId"), sid)
            name = style.find(qn("w:name"))
            if name is None:
                name = OxmlElement("w:name")
                style.insert(0, name)
            name.set(qn("w:val"), sid)
            existing = self.styles.get(sid)
            if existing is not None and _signature(existing) != _signature(style):
                return None
            if existing is None:
                self.root.append(style)
                self.styles[sid] = style
                self.inserted_ids.append(sid)
            parent_id = sid
        self._removed_properties[(style_id or "", removed)] = dict(removed_properties)
        return parent_id

    def payload(self) -> bytes:
        return serialize_xml_payload(self.root) if self.inserted_ids else self.original_payload
