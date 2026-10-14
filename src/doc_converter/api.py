"""Local-only HTTP API for document conversion jobs and style packs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from doc_converter.docx_direct import analyze_docx, normalize_docx_direct
from doc_converter.docx_direct.audit import AUDIT_FILENAMES
from doc_converter.docx_direct.model import DecisionMode
from doc_converter.filename import safe_docx_filename
from doc_converter.importers import ImporterError, ImportResult, import_document
from doc_converter.importers.libreoffice import resolve_libreoffice
from doc_converter.normalizer import normalize_markdown
from doc_converter.renderer import RendererError, render_docx
from doc_converter.style_library import StyleLibrary, StylePack, create_style_pack
from doc_converter.style_schema import migrate_roles


class StylePackRequest(BaseModel):
    """The editable fields accepted by the local style-pack API."""

    name: str = Field(min_length=1, max_length=80)
    format_id: str = Field(default="docx", min_length=1, max_length=30)
    roles: dict[str, dict[str, Any]] | None = None


class StylePackRevisionRequest(StylePackRequest):
    """A revision request that protects the current style-pack version."""

    base_version: int = Field(ge=1)


class DraftResponse(BaseModel):
    """The imported or edited Markdown working copy for one job."""

    source_format: str
    source_markdown: str
    warnings: list[str] = Field(default_factory=list)


class RenderRequest(BaseModel):
    """Render immutable imported source with the selected style version."""

    model_config = ConfigDict(extra="forbid")
    style_pack_id: str | None = None
    style_pack_version: int | None = Field(default=None, ge=1)


class DirectRenderRequest(BaseModel):
    """The style-pack version used for a direct DOCX normalization."""

    style_pack_id: str | None = None
    style_pack_version: int | None = Field(default=None, ge=1)
    decision_mode: DecisionMode = "hybrid"


class JobRecord(BaseModel):
    """Persistent state for one local conversion job."""

    id: str
    status: str
    source_name: str
    source_format: str = "markdown"
    conversion_mode: Literal["round-trip", "docx-direct"] = "round-trip"
    source_original_name: str = ""
    import_warnings: list[str] = Field(default_factory=list)
    processing_warnings: list[str] = Field(default_factory=list)
    style_pack_id: str
    style_pack_version: int
    suggestions: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    output_name: str | None = None
    draft_updated_at: datetime | None = None
    source_hash: str = ""
    render_revision: int = 0
    preview_ready: bool = False


class JobStore:
    """Stores jobs beneath the application data root, outside source folders."""

    def __init__(self, data_root: Path) -> None:
        self._jobs_root = data_root / "jobs"

    def stage_upload(self, *, source_name: str, source_bytes: bytes) -> tuple[str, Path]:
        """Create a job workspace and preserve the uploaded bytes in their own file."""

        job_id = str(uuid4())
        job_directory = self.path_for(job_id)
        source_directory = job_directory / "source"
        source_directory.mkdir(parents=True, exist_ok=False)
        (job_directory / "work").mkdir()
        original_path = source_directory / f"original{Path(source_name).suffix.lower()}"
        original_path.write_bytes(source_bytes)
        return job_id, original_path

    def discard_staged_upload(self, job_id: str) -> None:
        """Remove an unregistered workspace after its import has failed."""

        job_directory = self.path_for(job_id).resolve()
        if job_directory.parent != self._jobs_root.resolve():
            raise ValueError("Invalid job directory.")
        if job_directory.exists():
            shutil.rmtree(job_directory)

    def create(
        self,
        *,
        job_id: str,
        source_name: str,
        source_original_name: str,
        import_result: ImportResult,
        style_pack_id: str,
        style_pack_version: int,
    ) -> JobRecord:
        created_at = datetime.now(timezone.utc)
        job = JobRecord(
            id=job_id,
            status="ready",
            source_name=source_name,
            source_format=import_result.source_format,
            source_original_name=source_original_name,
            import_warnings=import_result.warnings,
            style_pack_id=style_pack_id,
            style_pack_version=style_pack_version,
            created_at=created_at,
            source_hash=_source_hash(import_result.markdown),
        )
        job_directory = self.path_for(job.id)
        (job_directory / "source" / "imported.md").write_text(
            import_result.markdown, encoding="utf-8"
        )
        import_report = {
            "source_format": import_result.source_format,
            "source_original_name": source_original_name,
            "assets_dir": _relative_job_path(import_result.assets_dir, job_directory),
            "intermediate_files": [
                _relative_job_path(path, job_directory) for path in import_result.intermediate_files
            ],
            "warnings": import_result.warnings,
        }
        (job_directory / "import-report.json").write_text(
            json.dumps(import_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.save(job)
        return job

    def create_direct(
        self, *, job_id: str, source_name: str, style_pack_id: str, style_pack_version: int
    ) -> JobRecord:
        """Register a DOCX job that uses its original upload without importing Markdown."""
        job = JobRecord(
            id=job_id,
            status="ready",
            source_name=source_name,
            source_format="docx",
            conversion_mode="docx-direct",
            source_original_name=source_name,
            style_pack_id=style_pack_id,
            style_pack_version=style_pack_version,
            created_at=datetime.now(timezone.utc),
        )
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

    def read_source(self, job: JobRecord) -> str:
        """Read first import; recover old jobs only from their original upload."""
        path = self.path_for(job.id) / "source" / "imported.md"
        if not path.is_file():
            original = self.path_for(job.id) / "source" / f"original{Path(job.source_name).suffix.lower()}"
            if not original.is_file():
                raise ValueError("未找到原始上传文件，请重新选择源文件转换。")
            imported = import_document(original, job_directory=self.path_for(job.id))
            path.write_text(imported.markdown, encoding="utf-8")
        return path.read_text(encoding="utf-8")

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
        conversion_mode: Literal["round-trip", "docx-direct"] | None = Form(None),
    ) -> JobRecord:
        source_name = _safe_upload_name(source.filename)
        source_suffix = Path(source_name).suffix.lower()
        if source_suffix not in {".md", ".markdown", ".docx", ".doc"}:
            raise HTTPException(
                status_code=422,
                detail="当前支持 .md、.markdown、.docx 和 .doc 文件。",
            )
        effective_mode = conversion_mode or ("docx-direct" if source_suffix == ".docx" else "round-trip")
        if effective_mode == "docx-direct" and source_suffix != ".docx":
            raise HTTPException(status_code=422, detail="DOCX 直接规范化仅支持 .docx 文件。")
        try:
            style_library.get(style_pack_id, style_pack_version)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="未找到所选样式包版本。") from error

        job_id, original_path = job_store.stage_upload(
            source_name=source_name,
            source_bytes=source.file.read(),
        )
        if effective_mode == "docx-direct":
            try:
                analyze_docx(original_path)
            except ValueError as error:
                job_store.discard_staged_upload(job_id)
                raise HTTPException(status_code=422, detail=str(error)) from error
            return job_store.create_direct(
                job_id=job_id,
                source_name=source_name,
                style_pack_id=style_pack_id,
                style_pack_version=style_pack_version,
            )
        try:
            imported = import_document(original_path, job_directory=job_store.path_for(job_id))
        except ImporterError as error:
            job_store.discard_staged_upload(job_id)
            raise HTTPException(status_code=422, detail=str(error)) from error

        return job_store.create(
            job_id=job_id,
            source_name=source_name,
            source_original_name=source_name,
            import_result=imported,
            style_pack_id=style_pack_id,
            style_pack_version=style_pack_version,
        )

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> JobRecord:
        return _get_job_or_404(job_store, job_id)

    @app.get("/api/jobs/{job_id}/draft", deprecated=True)
    def get_draft(job_id: str) -> DraftResponse:
        job = _get_job_or_404(job_store, job_id)
        if job.conversion_mode == "docx-direct":
            raise HTTPException(status_code=404, detail="直接规范化任务没有 Markdown 工作副本。")
        try:
            markdown = job_store.read_source(job)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="未找到该任务的 Markdown 工作副本。") from error
        return DraftResponse(
            source_format=job.source_format,
            source_markdown=markdown,
            warnings=job.import_warnings,
        )

    @app.put("/api/jobs/{job_id}/draft", deprecated=True)
    def save_draft(job_id: str) -> None:
        _get_job_or_404(job_store, job_id)
        raise HTTPException(status_code=410, detail="工作副本编辑接口已移除，请在源文件或输出 DOCX 中修改后重新转换。")

    @app.post("/api/jobs/{job_id}/normalize-and-render")
    def normalize_and_render(job_id: str, request: RenderRequest) -> JobRecord:
        job = _get_job_or_404(job_store, job_id)
        if job.conversion_mode == "docx-direct":
            raise HTTPException(status_code=409, detail="请使用 DOCX 直接规范化接口。")
        job_directory = job_store.path_for(job.id)
        try:
            source_markdown = job_store.read_source(job)
            normalized = normalize_markdown(source_markdown, filename=job.source_name)
            if not normalized.report["integrity"]["passed"]:
                raise ValueError("内容完整性校验失败，已阻止 DOCX 生成。")

            normalized_path = job_directory / "document.normalized.md"
            normalized_path.write_text(normalized.markdown, encoding="utf-8")
            processing_warnings: list[str] = []
            report_artifacts: list[str] = []
            try:
                (job_directory / "normalization-report.json").write_text(
                    json.dumps(normalized.report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                report_artifacts.append("normalization-report.json")
            except OSError:
                processing_warnings.append("DOCX 仍可生成，处理报告未能保存。")
            style_pack_id = request.style_pack_id or job.style_pack_id
            style_pack_version = request.style_pack_version or job.style_pack_version
            try:
                style_pack = style_library.get(style_pack_id, style_pack_version)
            except FileNotFoundError as error:
                raise HTTPException(status_code=404, detail="未找到当前样式组合版本。") from error
            job = job.model_copy(
                update={
                    "style_pack_id": style_pack_id,
                    "style_pack_version": style_pack_version,
                }
            )
            (job_directory / "style-pack.snapshot.json").write_text(
                style_pack.model_dump_json(indent=2), encoding="utf-8"
            )
            output_name = safe_docx_filename(normalized.metadata.get("title"), job.source_name)
            staged_output = job_directory / "work" / "render-candidate.docx"
            rendered = render_docx(
                markdown=normalized.markdown,
                role_decisions=normalized.report["decisions"],
                style_pack=style_pack,
                output_path=staged_output,
                work_dir=job_directory / "work",
            )
            try:
                (job_directory / "output-verification.json").write_text(
                    json.dumps(rendered.verification, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                report_artifacts.append("output-verification.json")
            except OSError:
                processing_warnings.append("输出格式校验报告未能保存。")
            if not rendered.verification["passed"]:
                processing_warnings.append(f"输出格式复核发现 {rendered.verification['failed_checks']} 项差异，详见输出校验报告。")
            staged_output.replace(job_directory / output_name)
            render_revision = job.render_revision + 1
            preview_path = job_directory / "preview" / f"document-{render_revision}.pdf"
            preview_ready = _convert_docx_to_pdf(job_directory / output_name, preview_path)
            preview_ready = preview_ready and preview_path.is_file()
            completed = job.model_copy(
                update={
                    "status": "completed",
                    "artifacts": [
                        output_name,
                        "document.normalized.md",
                        *report_artifacts,
                        "style-pack.snapshot.json",
                    ],
                    "error": None,
                    "processing_warnings": processing_warnings,
                    "output_name": output_name,
                    "render_revision": render_revision,
                    "preview_ready": preview_ready,
                }
            )
            job_store.save(completed)
            return completed
        except (RendererError, ImporterError, OSError, ValueError) as error:
            failed = job.model_copy(update={"status": "failed", "error": str(error)})
            job_store.save(failed)
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/jobs/{job_id}/normalize-docx-direct")
    def normalize_docx_direct_job(job_id: str, request: DirectRenderRequest) -> JobRecord:
        job = _get_job_or_404(job_store, job_id)
        if job.conversion_mode != "docx-direct":
            raise HTTPException(status_code=409, detail="该任务未选择 DOCX 直接规范化。")
        style_pack_id = request.style_pack_id or job.style_pack_id
        style_pack_version = request.style_pack_version or job.style_pack_version
        try:
            style_pack = style_library.get(style_pack_id, style_pack_version)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="未找到当前样式组合版本。") from error

        job_directory = job_store.path_for(job.id)
        output_name = safe_docx_filename(f"{Path(job.source_name).stem}_规范化", job.source_name)
        output_path = job_directory / output_name
        try:
            normalize_docx_direct(
                job_directory / "source" / "original.docx",
                style_pack,
                output_path,
                audit_dir=job_directory,
                decision_mode=request.decision_mode,
            )
            render_revision = job.render_revision + 1
            preview_path = job_directory / "preview" / f"document-{render_revision}.pdf"
            preview_ready = _convert_docx_to_pdf(output_path, preview_path) and preview_path.is_file()
            completed = job.model_copy(
                update={
                    "status": "completed",
                    "artifacts": [output_name, *AUDIT_FILENAMES],
                    "error": None,
                    "output_name": output_name,
                    "style_pack_id": style_pack_id,
                    "style_pack_version": style_pack_version,
                    "render_revision": render_revision,
                    "preview_ready": preview_ready,
                }
            )
            job_store.save(completed)
            return completed
        except (OSError, ValueError) as error:
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

    @app.get("/api/jobs/{job_id}/preview")
    def get_preview(job_id: str, revision: int | None = Query(default=None, ge=1)) -> FileResponse:
        job = _get_job_or_404(job_store, job_id)
        if job.status != "completed" or not job.output_name:
            raise HTTPException(status_code=404, detail="任务尚未生成可预览的 DOCX。")
        job_directory = job_store.path_for(job.id)
        docx_path = job_directory / job.output_name
        if not docx_path.exists():
            raise HTTPException(status_code=404, detail="任务 DOCX 产物已不存在。")
        preview_revision = revision or job.render_revision
        preview_path = job_directory / "preview" / f"document-{preview_revision}.pdf"
        if not preview_path.exists() and not _convert_docx_to_pdf(docx_path, preview_path):
            raise HTTPException(status_code=404, detail="当前环境没有可用的本地 PDF 预览引擎。")
        return FileResponse(
            preview_path,
            media_type="application/pdf",
            filename="document-preview.pdf",
            content_disposition_type="inline",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    resolved_frontend_dist = frontend_dist or _default_frontend_dist()
    index_path = resolved_frontend_dist / "index.html"
    if index_path.exists():
        assets_path = resolved_frontend_dist / "assets"
        if assets_path.exists():
            app.mount("/assets", StaticFiles(directory=assets_path), name="frontend-assets")

        @app.get("/")
        def frontend() -> FileResponse:
            return FileResponse(index_path, headers={"Cache-Control": "no-cache"})

    return app


def _source_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _safe_upload_name(filename: str | None) -> str:
    """Keep only the client filename while handling both Windows and POSIX paths."""

    candidate = (filename or "document.md").replace("\\", "/").rsplit("/", 1)[-1]
    return candidate or "document.md"


def _relative_job_path(path: Path | None, job_directory: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(job_directory.resolve()).as_posix()
    except ValueError:
        return None


def _convert_docx_to_pdf(source_path: Path, output_path: Path) -> bool:
    """Render the already-created DOCX with a local office engine for preview only."""

    executable = _find_soffice()
    if executable is None:
        return False

    from tempfile import NamedTemporaryFile, TemporaryDirectory

    # Keep native Office paths short and ASCII even when a job/output name is
    # deeply nested or Chinese; the original and published DOCX stay untouched.
    temporary = TemporaryDirectory(prefix="docx-pdf-")
    conversion_root = Path(temporary.name)
    profile_root = conversion_root / "profile"
    profile_root.mkdir()
    staged_pdf: Path | None = None
    try:
        from doc_converter.preview_fonts import prepare_pdf_font_aliases

        prepare_pdf_font_aliases(profile_root)
        staged_source = conversion_root / "document.docx"
        shutil.copyfile(source_path, staged_source)
        result = subprocess.run(
            [
                executable,
                "--headless",
                f"-env:UserInstallation={profile_root.as_uri()}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(conversion_root),
                str(staged_source),
            ],
            capture_output=True,
            check=False,
            timeout=60,
        )
        generated_path = conversion_root / "document.pdf"
        if result.returncode != 0 or not generated_path.exists():
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # The native temporary directory may be on another drive. Publish an
        # atomic copy beside the destination rather than a cross-drive rename.
        with NamedTemporaryFile(dir=output_path.parent, prefix=".pdf-", suffix=".tmp", delete=False) as staged:
            staged_pdf = Path(staged.name)
            with generated_path.open("rb") as generated:
                shutil.copyfileobj(generated, staged)
        staged_pdf.replace(output_path)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        if staged_pdf is not None:
            staged_pdf.unlink(missing_ok=True)
        temporary.cleanup()


def _find_soffice() -> str | None:
    try:
        return str(resolve_libreoffice())
    except ImporterError:
        return None


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
    configured_root = os.environ.get("DOC_CONVERTER_DATA_ROOT")
    if configured_root:
        return Path(configured_root)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "DocConverter"
    return Path.home() / ".doc-converter"


def _default_frontend_dist() -> Path:
    return Path(__file__).resolve().parent / "web"

