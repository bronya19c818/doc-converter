"""Local-only HTTP API for document conversion jobs and style packs."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from doc_converter.filename import safe_docx_filename
from doc_converter.normalizer import normalize_markdown
from doc_converter.renderer import RendererError, render_docx
from doc_converter.style_library import StyleLibrary, StylePack, create_style_pack
from doc_converter.style_schema import migrate_roles

_NUMBERED_TITLE = re.compile(r"^(?:[一二三四五六七八九十]+、|（[^）]+）|\d+[.、])")


class StylePackRequest(BaseModel):
    """The editable fields accepted by the local style-pack API."""

    name: str = Field(min_length=1, max_length=80)
    format_id: str = Field(default="docx", min_length=1, max_length=30)
    roles: dict[str, dict[str, Any]] | None = None


class StylePackRevisionRequest(StylePackRequest):
    """A revision request that protects the current style-pack version."""

    base_version: int = Field(ge=1)


class ConfirmationRequest(BaseModel):
    """Explicit user confirmations for semantic-role suggestions."""

    confirmed_roles: dict[str, str] = Field(default_factory=dict)


class DraftRequest(BaseModel):
    """A complete editable Markdown work copy."""

    source_markdown: str


class RenderRequest(BaseModel):
    """The current work copy and optional structure actions for rendering."""

    source_markdown: str | None = None
    confirmed_roles: dict[str, str] = Field(default_factory=dict)


class JobRecord(BaseModel):
    """Persistent state for one local conversion job."""

    id: str
    status: str
    source_name: str
    style_pack_id: str
    style_pack_version: int
    suggestions: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    output_name: str | None = None
    draft_updated_at: datetime | None = None
    source_hash: str = ""


class JobStore:
    """Stores jobs beneath the application data root, outside source folders."""

    def __init__(self, data_root: Path) -> None:
        self._jobs_root = data_root / "jobs"

    def create(
        self,
        *,
        source_name: str,
        source: str,
        style_pack_id: str,
        style_pack_version: int,
        suggestions: list[dict[str, Any]],
    ) -> JobRecord:
        created_at = datetime.now(timezone.utc)
        job = JobRecord(
            id=str(uuid4()),
            status="ready",
            source_name=source_name,
            style_pack_id=style_pack_id,
            style_pack_version=style_pack_version,
            suggestions=suggestions,
            created_at=created_at,
            source_hash=_source_hash(source),
        )
        job_directory = self.path_for(job.id)
        job_directory.mkdir(parents=True, exist_ok=False)
        (job_directory / "source.md").write_text(source, encoding="utf-8")
        (job_directory / "source.original.md").write_text(source, encoding="utf-8")
        self.save(job)
        return job

    def get(self, job_id: str) -> JobRecord:
        path = self.path_for(job_id) / "job.json"
        if not path.exists():
            raise KeyError(job_id)
        return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, job: JobRecord) -> None:
        self.path_for(job.id).mkdir(parents=True, exist_ok=True)
        (self.path_for(job.id) / "job.json").write_text(
            job.model_dump_json(indent=2), encoding="utf-8"
        )

    def path_for(self, job_id: str) -> Path:
        return self._jobs_root / job_id


def create_app(*, data_root: Path | None = None, frontend_dist: Path | None = None) -> FastAPI:
    """Create an app bound to a local data root, with no remote integrations."""

    resolved_root = data_root or _default_data_root()
    style_library = StyleLibrary(resolved_root)
    _seed_builtin_packs(style_library)
    job_store = JobStore(resolved_root)

    app = FastAPI(title="Doc Converter", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "processing": "local-only"}

    @app.get("/api/style-packs")
    def list_style_packs() -> list[StylePack]:
        return style_library.list_packs()

    @app.post("/api/style-packs", status_code=status.HTTP_201_CREATED)
    def save_style_pack(request: StylePackRequest) -> StylePack:
        pack = create_style_pack(name=request.name.strip(), format_id=request.format_id)
        if request.roles is not None:
            pack = pack.model_copy(update={"roles": migrate_roles(request.roles)})
        return style_library.save(pack)

    @app.put("/api/style-packs/{pack_id}", status_code=status.HTTP_201_CREATED)
    def revise_style_pack(pack_id: str, request: StylePackRevisionRequest) -> StylePack:
        try:
            current = style_library.get(pack_id, request.base_version)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="未找到待编辑的样式包版本。") from error
        latest = next((pack for pack in style_library.list_packs() if pack.id == pack_id), None)
        if latest is None or latest.version != request.base_version:
            raise HTTPException(status_code=409, detail="样式包已有更新，请刷新后再保存。")
        if request.format_id != current.format_id:
            raise HTTPException(status_code=422, detail="不能修改既有样式包的目标格式。")
        return style_library.save(
            current.model_copy(
                update={
                    "name": request.name.strip(),
                    "roles": migrate_roles(request.roles) if request.roles is not None else current.roles,
                }
            )
        )

    @app.post("/api/jobs", status_code=status.HTTP_201_CREATED)
    def create_job(
        source: UploadFile = File(...),
        style_pack_id: str = Form(...),
        style_pack_version: int = Form(...),
    ) -> JobRecord:
        source_name = Path(source.filename or "document.md").name
        if Path(source_name).suffix.lower() not in {".md", ".markdown"}:
            raise HTTPException(status_code=422, detail="当前仅支持 Markdown 文件。")
        try:
            source_text = source.file.read().decode("utf-8")
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=422, detail="Markdown 必须使用 UTF-8 编码。") from error
        try:
            style_library.get(style_pack_id, style_pack_version)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="未找到所选样式包版本。") from error

        return job_store.create(
            source_name=source_name,
            source=source_text,
            style_pack_id=style_pack_id,
            style_pack_version=style_pack_version,
            suggestions=_suggest_semantic_roles(source_text),
        )

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> JobRecord:
        return _get_job_or_404(job_store, job_id)

    @app.put("/api/jobs/{job_id}/draft")
    def save_draft(job_id: str, request: DraftRequest) -> JobRecord:
        job = _get_job_or_404(job_store, job_id)
        updated = job.model_copy(
            update={
                "status": "ready",
                "suggestions": _suggest_semantic_roles(request.source_markdown),
                "error": None,
                "draft_updated_at": datetime.now(timezone.utc),
                "source_hash": _source_hash(request.source_markdown),
            }
        )
        job_store.path_for(job.id).mkdir(parents=True, exist_ok=True)
        (job_store.path_for(job.id) / "source.md").write_text(request.source_markdown, encoding="utf-8")
        job_store.save(updated)
        return updated

    @app.post("/api/jobs/{job_id}/normalize-and-render")
    def normalize_and_render(job_id: str, request: RenderRequest) -> JobRecord:
        job = _get_job_or_404(job_store, job_id)
        job_directory = job_store.path_for(job.id)
        confirmed_roles = {int(line): role for line, role in request.confirmed_roles.items()}
        try:
            source_markdown = request.source_markdown
            if source_markdown is not None:
                (job_directory / "source.md").write_text(source_markdown, encoding="utf-8")
                job = job.model_copy(
                    update={
                        "draft_updated_at": datetime.now(timezone.utc),
                        "source_hash": _source_hash(source_markdown),
                    }
                )
            normalized = normalize_markdown(
                (job_directory / "source.md").read_text(encoding="utf-8"),
                filename=job.source_name,
                confirmed_roles=confirmed_roles,
            )
            if not normalized.report["integrity"]["passed"]:
                raise ValueError("内容完整性校验失败，已阻止 DOCX 生成。")

            normalized_path = job_directory / "document.normalized.md"
            normalized_path.write_text(normalized.markdown, encoding="utf-8")
            (job_directory / "normalization-report.json").write_text(
                json.dumps(normalized.report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (job_directory / "confirmation.json").write_text(
                json.dumps(request.confirmed_roles, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            style_pack = style_library.get(job.style_pack_id, job.style_pack_version)
            (job_directory / "style-pack.snapshot.json").write_text(
                style_pack.model_dump_json(indent=2), encoding="utf-8"
            )
            output_name = safe_docx_filename(normalized.metadata.get("title"), job.source_name)
            render_docx(
                markdown=normalized.markdown,
                style_pack=style_pack,
                output_path=job_directory / output_name,
                work_dir=job_directory / "work",
            )
            completed = job.model_copy(
                update={
                    "status": "completed",
                    "artifacts": [
                        output_name,
                        "document.normalized.md",
                        "normalization-report.json",
                        "confirmation.json",
                        "style-pack.snapshot.json",
                    ],
                    "error": None,
                    "output_name": output_name,
                }
            )
            job_store.save(completed)
            return completed
        except (RendererError, ValueError) as error:
            failed = job.model_copy(update={"status": "failed", "error": str(error)})
            job_store.save(failed)
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/jobs/{job_id}/artifacts/{artifact_name}")
    def get_artifact(job_id: str, artifact_name: str) -> FileResponse:
        job = _get_job_or_404(job_store, job_id)
        if Path(artifact_name).name != artifact_name or artifact_name not in job.artifacts:
            raise HTTPException(status_code=404, detail="未找到任务产物。")
        artifact_path = job_store.path_for(job_id) / artifact_name
        if not artifact_path.exists():
            raise HTTPException(status_code=404, detail="任务产物已不存在。")
        return FileResponse(artifact_path, filename=artifact_name)

    resolved_frontend_dist = frontend_dist or _default_frontend_dist()
    index_path = resolved_frontend_dist / "index.html"
    if index_path.exists():
        assets_path = resolved_frontend_dist / "assets"
        if assets_path.exists():
            app.mount("/assets", StaticFiles(directory=assets_path), name="frontend-assets")

        @app.get("/")
        def frontend() -> FileResponse:
            return FileResponse(index_path)

    return app


def _suggest_semantic_roles(source: str) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    title_found = False
    for line_number, line in enumerate(source.splitlines(), start=1):
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            title = match.group(1)
            if not _NUMBERED_TITLE.match(title) and not title_found:
                suggestions.append(
                    {
                        "line": line_number,
                        "role": "document-title",
                        "score": 0.9,
                        "reason": "首个无编号 H1",
                    }
                )
                title_found = True
                continue
            if title_found and not _NUMBERED_TITLE.match(title):
                suggestions.append(
                    {
                        "line": line_number,
                        "role": "document-subtitle",
                        "score": 0.75,
                        "reason": "标题后的无编号 H1，可作为副标题",
                    }
                )
            if title_found:
                return suggestions
        if line.strip():
            if title_found:
                return suggestions
            break
    return suggestions


def _source_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _get_job_or_404(job_store: JobStore, job_id: str) -> JobRecord:
    try:
        return job_store.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="未找到任务。") from error


def _seed_builtin_packs(style_library: StyleLibrary) -> None:
    if style_library.list_packs():
        return
    for name in ("通用正式报告", "学术论文", "简洁商务报告"):
        style_library.save(create_style_pack(name=name, format_id="docx"))


def _default_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "DocConverter"
    return Path.home() / ".doc-converter"


def _default_frontend_dist() -> Path:
    return Path(__file__).resolve().parent / "web"
