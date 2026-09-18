"""Versioned, local DOCX style-pack storage."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from doc_converter.style_schema import migrate_roles


class StylePack(BaseModel):
    """A portable versioned style configuration for one output format."""

    id: str
    name: str
    format_id: str
    version: int = 0
    created_at: datetime
    roles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    schema_version: str = "docx-style/v3"

    @classmethod
    def model_validate(cls, obj: Any, *args: Any, **kwargs: Any) -> "StylePack":
        if isinstance(obj, dict):
            obj = dict(obj)
            # The loader always returns the current normalized schema.  Older
            # JSON files are upgraded by ``migrate_roles`` without rewriting
            # the original revision on disk.
            obj["schema_version"] = "docx-style/v3"
            obj["roles"] = migrate_roles(obj.get("roles"))
        return super().model_validate(obj, *args, **kwargs)

    @classmethod
    def model_validate_json(cls, json_data: str | bytes | bytearray, *args: Any, **kwargs: Any) -> "StylePack":
        import json

        return cls.model_validate(json.loads(json_data), *args, **kwargs)


def create_style_pack(*, name: str, format_id: str) -> StylePack:
    """Create an unsaved style pack with the common DOCX semantic roles."""

    return StylePack(
        id=str(uuid4()),
        name=name,
        format_id=format_id,
        created_at=datetime.now(timezone.utc),
        roles=migrate_roles({}),
    )


class StyleLibrary:
    """Stores immutable style-pack revisions in an application-owned folder."""

    def __init__(self, data_root: Path) -> None:
        self._root = data_root / "style-packs"

    def save(self, pack: StylePack) -> StylePack:
        """Persist a new revision without changing older revisions."""

        pack_directory = self._root / pack.id
        existing_versions = [int(path.stem) for path in pack_directory.glob("*.json") if path.stem.isdigit()]
        next_version = max(existing_versions, default=0) + 1
        saved = pack.model_copy(update={"version": next_version})
        pack_directory.mkdir(parents=True, exist_ok=True)
        (pack_directory / f"{next_version}.json").write_text(
            saved.model_dump_json(indent=2), encoding="utf-8"
        )
        return saved

    def get(self, pack_id: str, version: int) -> StylePack:
        """Load one exact immutable style-pack revision."""

        path = self._root / pack_id / f"{version}.json"
        return StylePack.model_validate_json(path.read_text(encoding="utf-8"))

    def list_packs(self) -> list[StylePack]:
        """List the newest revision of each available style pack."""

        if not self._root.exists():
            return []

        packs: list[StylePack] = []
        for directory in self._root.iterdir():
            if not directory.is_dir():
                continue
            versions = sorted((int(path.stem) for path in directory.glob("*.json") if path.stem.isdigit()))
            if versions:
                packs.append(self.get(directory.name, versions[-1]))
        return sorted(packs, key=lambda pack: (pack.name, pack.id))
