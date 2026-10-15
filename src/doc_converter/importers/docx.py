"""DOCX input adapter using Pandoc to create canonical Markdown."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import yaml
from docx import Document

from doc_converter.importers.base import ImporterError, ImportResult
from doc_converter.renderer import RendererError, resolve_pandoc

_TAB_TOKEN = "DOC_CONVERTER_TAB_TOKEN"
_PAGE_BREAK_TOKEN = "DOC_CONVERTER_PAGE_BREAK_TOKEN"
_ENDNOTE_LABEL = "doc-converter-endnote"
_PREFACE_LABEL_PATTERN = re.compile(
    r"^\s*(?:摘要|关键词|作者(?:单位)?|单位|机构|组织|部门|所属部门|日期|时间|发布时间|用途(?:说明)?|原则(?:说明)?)\s*(?:[:：]|$)"
)
_PLAIN_AUTHOR_PATTERN = re.compile(r"^[\u4e00-\u9fff]{2,4}(?:[、，,]\s*[\u4e00-\u9fff]{2,4})*$")
_DATE_ONLY_PATTERN = re.compile(r"^\d{4}\s*[年./-]\s*\d{1,2}(?:\s*[月./-]\s*\d{1,2}\s*日?)?$")
_ORG_MARKERS = ("公司", "集团", "中心", "大学", "学院", "研究院", "事务所", "医院", "学校", "协会", "委员会")
_DEPARTMENT_MARKERS = ("部门", "部", "处", "科", "室", "局", "办", "厅", "所", "组", "队")
_COMMON_SURNAMES = frozenset("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳")


def import_docx(source_path: Path, *, job_directory: Path) -> ImportResult:
    """Convert a DOCX source to GFM while extracting media into its job."""

    try:
        pandoc_path = resolve_pandoc()
    except RendererError as error:
        raise ImporterError("当前环境未找到 Pandoc，无法导入 DOCX 文件。") from error

    try:
        reader_source = _prepare_docx_for_reader(source_path, job_directory)
    except (BadZipFile, KeyError, UnicodeDecodeError, OSError, ValueError) as error:
        raise ImporterError("DOCX 文件不是有效的 Office Open XML 压缩包，无法导入。") from error
    relative_source = _relative_to_job(reader_source, job_directory)
    assets_argument = "source/assets"
    command = [
        str(pandoc_path),
        relative_source,
        "--from=docx",
        "--to=gfm",
        "--wrap=none",
        "--track-changes=accept",
        f"--extract-media={assets_argument}",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=job_directory,
            timeout=120,
        )
    except FileNotFoundError as error:
        raise ImporterError("当前环境未找到 Pandoc，无法导入 DOCX 文件。") from error
    except subprocess.TimeoutExpired as error:
        raise ImporterError("DOCX 导入超时，请检查文件是否损坏或过大。") from error
    except OSError as error:
        raise ImporterError(f"无法启动 Pandoc 导入 DOCX：{error}") from error

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "Pandoc 未能读取该 DOCX 文件。"
        raise ImporterError(f"DOCX 导入失败：{detail}")

    markdown = _restore_internal_reader_tokens(completed.stdout)
    markdown = _promote_docx_title_area(markdown, source_path)
    markdown = _mark_endnotes(markdown, source_path)

    assets_path = job_directory / assets_argument
    assets_dir: Path | None = assets_path
    if not assets_path.is_dir() or not any(assets_path.iterdir()):
        if assets_path.is_dir():
            assets_path.rmdir()
        assets_dir = None

    warnings = [
        line.strip()
        for line in completed.stderr.splitlines()
        if "warning" in line.lower()
    ]
    return ImportResult(
        source_format="docx",
        markdown=markdown,
        original_path=source_path,
        assets_dir=assets_dir,
        warnings=warnings,
    )


def _prepare_docx_for_reader(source_path: Path, job_directory: Path) -> Path:
    """Copy a DOCX and mark unsupported Word constructs before Pandoc reads it."""

    work_directory = job_directory / "work"
    work_directory.mkdir(parents=True, exist_ok=True)
    prepared_path = work_directory / "docx-reader.docx"
    with ZipFile(source_path) as source, ZipFile(prepared_path, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "word/document.xml":
                xml = payload.decode("utf-8")
                xml = re.sub(
                    r"<w:tab\s*/>",
                    f'<w:t xml:space="preserve">{_TAB_TOKEN}</w:t>',
                    xml,
                )
                xml = re.sub(
                    r'<w:br\b(?=[^>]*\bw:type=["\']page["\'])[^>]*/>',
                    f'<w:t xml:space="preserve">{_PAGE_BREAK_TOKEN}</w:t>',
                    xml,
                )
                payload = xml.encode("utf-8")
            target.writestr(info, payload)
    return prepared_path


def _restore_internal_reader_tokens(markdown: str) -> str:
    """Map reader-only markers to native Pandoc Markdown where possible."""

    return markdown.replace(_TAB_TOKEN, "&#9;").replace(
        _PAGE_BREAK_TOKEN,
        "<!-- doc-converter:page-break -->",
    )


def _promote_docx_title_area(markdown: str, source_path: Path) -> str:
    """Use high-confidence centered font-size evidence for DOCX title metadata."""

    try:
        document = Document(str(source_path))
    except (BadZipFile, OSError, ValueError, TypeError):
        return markdown

    candidates: list[tuple[int, int, str, float]] = []
    native_titles: set[str] = set()
    for index, paragraph in enumerate(document.paragraphs):
        style_name = paragraph.style.name if paragraph.style is not None else ""
        if style_name.lower().startswith("heading"):
            break
        # start/end are valid OOXML logical alignments not supported by the enum.
        native_title = style_name.casefold() in {"title", "标题"}
        if native_title and paragraph.text.strip():
            native_titles.add(paragraph.text.strip())
        if not native_title and style_name.casefold() not in {"subtitle", "副标题"} and not paragraph._p.xpath('./w:pPr/w:jc[@w:val="center"]'):
            continue
        size = max(
            (
                run.font.size.pt
                for run in paragraph.runs
                if run.font.size is not None and run.font.size.pt is not None
            ),
            default=0.0,
        )
        style_font = paragraph.style.font if paragraph.style is not None else None
        if size <= 0 and style_font is not None and style_font.size is not None:
            size = style_font.size.pt or 0.0
        for part_index, part in enumerate(re.split(r"[\r\n\v]+", paragraph.text)):
            text = part.strip()
            if text:
                candidates.append((index, part_index, text, size))
    if not candidates:
        return markdown

    title_candidates = [item for item in candidates if item[2] in native_titles]
    if not title_candidates:
        title_candidates = [item for item in candidates if not _is_title_preface_text(item[2])]
    if not title_candidates:
        return markdown
    largest_size = max(item[3] for item in title_candidates)
    title_index, title_part_index, title, _ = next(
        item for item in title_candidates if item[3] == largest_size
    )
    subtitle = next(
        (
            text
            for index, part_index, text, size in candidates
            if (index, part_index) > (title_index, title_part_index)
            and size < largest_size
            and not _is_preface_text(text)
        ),
        None,
    )

    lines = markdown.splitlines()
    for value in (title, subtitle):
        if value is not None:
            _remove_markdown_title_line(lines, value)
    while lines and not lines[0].strip():
        lines.pop(0)
    metadata = {"title": title}
    if subtitle is not None:
        metadata["subtitle"] = subtitle
    serialized = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{serialized}\n---\n\n" + "\n".join(lines).lstrip("\n")


def _remove_markdown_title_line(lines: list[str], value: str) -> None:
    """Remove only the first Markdown line fragment emitted for a title-area run."""

    for index, line in enumerate(lines):
        if _markdown_line_text(line) == value:
            lines[index] = ""
            return
    for index, line in enumerate(lines):
        if value not in line:
            continue
        remainder = line.replace(value, "", 1).strip()
        lines[index] = remainder
        return


def _is_preface_text(value: str) -> bool:
    if _is_title_preface_text(value):
        return True
    return (
        len(value) <= 20
        and not re.search(r"[。！？；，,:：.!?]", value)
        and any(value.rstrip().endswith(marker) for marker in (*_ORG_MARKERS, *_DEPARTMENT_MARKERS))
    )


def _is_title_preface_text(value: str) -> bool:
    return bool(
        _PREFACE_LABEL_PATTERN.match(value)
        or _DATE_ONLY_PATTERN.fullmatch(value)
        or _is_plain_author_text(value)
        or _is_org_or_department_preface(value)
    )


def _is_org_or_department_preface(value: str) -> bool:
    """Recognize short unlabeled organization lines without excluding report titles."""

    compact = re.sub(r"\s+", "", value)
    return bool(
        1 < len(compact) <= 20
        and not re.search(r"[。！？；，,:：.!?]", compact)
        and any(compact.endswith(marker) for marker in (*_ORG_MARKERS, *_DEPARTMENT_MARKERS))
    )


def _is_plain_author_text(value: str) -> bool:
    author_text = value.replace("、", "").replace("，", "").replace(",", "")
    return bool(
        _PLAIN_AUTHOR_PATTERN.fullmatch(value)
        and len(author_text) <= 8
        and value[:1] in _COMMON_SURNAMES
    )


def _markdown_line_text(line: str) -> str:
    candidate = line.strip()
    candidate = re.sub(r"^(?:\*\*|__)(.*?)(?:\*\*|__)$", r"\1", candidate)
    candidate = re.sub(r"^(?:\*|_)(.*?)(?:\*|_)$", r"\1", candidate)
    return candidate.strip()


def _mark_endnotes(markdown: str, source_path: Path) -> str:
    """Give endnotes an explicit internal label; Pandoc Markdown has no endnote type."""

    note_kinds = _document_note_kinds(source_path)
    endnote_number = 0
    for number, kind in enumerate(note_kinds, start=1):
        if kind != "endnote":
            continue
        endnote_number += 1
        label = f"[^{_ENDNOTE_LABEL}-{endnote_number}]"
        markdown = re.sub(rf"\[\^{number}\]", label, markdown)
    return markdown


def _document_note_kinds(source_path: Path) -> list[str]:
    try:
        with ZipFile(source_path) as archive:
            xml = archive.read("word/document.xml")
    except (OSError, KeyError, ValueError):
        return []
    kinds: list[str] = []
    for match in re.finditer(
        rb"<(?:w:)?(footnoteReference|endnoteReference)\b[^>]*\b(?:w:)?id=[\"'](\d+)[\"']",
        xml,
    ):
        if int(match.group(2)) <= 0:
            continue
        kinds.append("endnote" if match.group(1) == b"endnoteReference" else "footnote")
    return kinds


def _relative_to_job(source_path: Path, job_directory: Path) -> str:
    try:
        return source_path.relative_to(job_directory).as_posix()
    except ValueError:
        return str(source_path.resolve())

