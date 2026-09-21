from io import BytesIO
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient

import doc_converter.api as api_module
from doc_converter.api import _suggest_semantic_roles, create_app


def test_local_api_creates_editable_job_saves_draft_and_renders_named_job(tmp_path) -> None:
    client = TestClient(create_app(data_root=tmp_path))

    created_pack = client.post(
        "/api/style-packs",
        json={"name": "测试正式报告", "format_id": "docx"},
    )
    assert created_pack.status_code == 201
    pack = created_pack.json()

    created_job = client.post(
        "/api/jobs",
        data={"style_pack_id": pack["id"], "style_pack_version": str(pack["version"])},
        files={"source": ("实施方案.md", "# 实施方案\n\n# 一、建设背景\n\n正文。", "text/markdown")},
    )
    assert created_job.status_code == 201
    job = created_job.json()
    assert job["status"] == "ready"
    assert job["suggestions"] == [
        {"line": 1, "role": "document-title", "score": 0.9, "reason": "首个无编号 H1"}
    ]

    draft = client.put(
        f"/api/jobs/{job['id']}/draft",
        json={"source_markdown": "---\ntitle: 实施方案\n---\n\n# 一、建设背景\n\n正文。"},
    )
    assert draft.status_code == 200
    assert draft.json()["draft_updated_at"] is not None

    completed_job = client.post(
        f"/api/jobs/{job['id']}/normalize-and-render",
        json={"source_markdown": "---\ntitle: 实施方案\n---\n\n# 一、建设背景\n\n正文。", "confirmed_roles": {}},
    )
    assert completed_job.status_code == 200
    assert completed_job.json()["status"] == "completed"
    assert completed_job.json()["output_name"] == "实施方案.docx"
    assert "实施方案.docx" in completed_job.json()["artifacts"]

    docx = client.get(f"/api/jobs/{job['id']}/artifacts/实施方案.docx")
    assert docx.status_code == 200
    assert docx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_structure_suggestions_cover_all_title_area_roles() -> None:
    source = """---
title: 项目方案
---

项目实施说明

摘要：这里是摘要内容。

关键词：项目；实施；质量

# 华软钢

重庆市公共资源交易中心

采购管理部

2026年9月18日

# 一、建设背景

正文内容。
"""

    suggestions = _suggest_semantic_roles(source)

    assert {item["role"] for item in suggestions} == {
        "document-subtitle",
        "abstract",
        "keywords",
        "author",
        "organization",
        "department",
        "date",
    }
    assert {item["line"] for item in suggestions} == {5, 7, 9, 11, 13, 15, 17}


def test_api_renders_generated_comprehensive_fixture_without_subtitle_confirmation(tmp_path) -> None:
    client = TestClient(create_app(data_root=tmp_path))
    pack = client.post("/api/style-packs", json={"name": "综合测试", "format_id": "docx"}).json()
    source = (Path(__file__).parent / "fixtures" / "comprehensive.md").read_text(encoding="utf-8")

    created = client.post(
        "/api/jobs",
        data={"style_pack_id": pack["id"], "style_pack_version": str(pack["version"])},
        files={"source": ("综合测试.md", source, "text/markdown")},
    )
    assert created.status_code == 201
    job = created.json()

    completed = client.post(
        f"/api/jobs/{job['id']}/normalize-and-render",
        json={"source_markdown": source, "confirmed_roles": {}},
    )

    assert completed.status_code == 200
    payload = completed.json()
    assert payload["output_name"] == "人工智能+公共资源交易创新实践.docx"
    assert payload["status"] == "completed"

    response = client.get(f"/api/jobs/{job['id']}/artifacts/{payload['output_name']}")
    document = Document(BytesIO(response.content))
    paragraph_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "基于14个省级创新样本的实践总结" in paragraph_text
    assert "摘要：本文从治理、安全、技术和生态四个方面总结公共资源交易数智化实践，并给出可执行的推进路径。" in paragraph_text
    assert "关键词：人工智能；大模型；公共资源交易；数智化" in paragraph_text


def test_render_uses_current_style_pack_and_advances_render_revision(tmp_path) -> None:
    client = TestClient(create_app(data_root=tmp_path))
    original = client.post("/api/style-packs", json={"name": "项目报告", "format_id": "docx"}).json()
    job = client.post(
        "/api/jobs",
        data={"style_pack_id": original["id"], "style_pack_version": str(original["version"])},
        files={"source": ("方案.md", "# 方案\n\n# 一、范围\n\n正文。", "text/markdown")},
    ).json()
    revised = client.put(
        f"/api/style-packs/{original['id']}",
        json={
            "base_version": original["version"],
            "name": original["name"],
            "format_id": original["format_id"],
            "roles": original["roles"],
        },
    ).json()
    render_request = {
        "source_markdown": "# 方案\n\n# 一、范围\n\n正文。",
        "confirmed_roles": {},
        "style_pack_id": revised["id"],
        "style_pack_version": revised["version"],
    }

    first = client.post(f"/api/jobs/{job['id']}/normalize-and-render", json=render_request)
    second = client.post(f"/api/jobs/{job['id']}/normalize-and-render", json=render_request)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["style_pack_version"] == revised["version"]
    assert first.json()["render_revision"] == 1
    assert second.json()["render_revision"] == 2
    snapshot = (
        tmp_path / "jobs" / job["id"] / "style-pack.snapshot.json"
    ).read_text(encoding="utf-8")
    assert f'"version": {revised["version"]}' in snapshot


def test_render_precomputes_inline_pdf_preview_before_marking_job_completed(tmp_path, monkeypatch) -> None:
    client = TestClient(create_app(data_root=tmp_path))
    pack = client.post("/api/style-packs", json={"name": "项目报告", "format_id": "docx"}).json()
    source = "# 方案\n\n# 一、范围\n\n正文。"
    job = client.post(
        "/api/jobs",
        data={"style_pack_id": pack["id"], "style_pack_version": str(pack["version"])},
        files={"source": ("方案.md", source, "text/markdown")},
    ).json()

    calls: list[tuple[Path, Path]] = []

    def fake_convert(source_path: Path, output_path: Path) -> bool:
        calls.append((source_path, output_path))
        assert source_path.exists()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4 preloaded preview")
        return True

    monkeypatch.setattr(api_module, "_convert_docx_to_pdf", fake_convert)
    rendered = client.post(
        f"/api/jobs/{job['id']}/normalize-and-render",
        json={"source_markdown": source, "confirmed_roles": {}},
    )
    assert rendered.status_code == 200
    payload = rendered.json()
    assert len(calls) == 1
    assert payload["preview_ready"] is True
    assert payload["status"] == "completed"

    preview = client.get(f"/api/jobs/{job['id']}/preview?revision=1")

    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("application/pdf")
    assert preview.headers["content-disposition"].startswith("inline")
    assert preview.content == b"%PDF-1.4 preloaded preview"
    assert len(calls) == 1


def test_preview_endpoint_retains_lazy_conversion_fallback(tmp_path, monkeypatch) -> None:
    client = TestClient(create_app(data_root=tmp_path))
    pack = client.post("/api/style-packs", json={"name": "项目报告", "format_id": "docx"}).json()
    source = "# 方案\n\n# 一、范围\n\n正文。"
    job = client.post(
        "/api/jobs",
        data={"style_pack_id": pack["id"], "style_pack_version": str(pack["version"])},
        files={"source": ("方案.md", source, "text/markdown")},
    ).json()

    monkeypatch.setattr(api_module, "_convert_docx_to_pdf", lambda _source_path, _output_path: False)
    rendered = client.post(
        f"/api/jobs/{job['id']}/normalize-and-render",
        json={"source_markdown": source, "confirmed_roles": {}},
    )
    assert rendered.status_code == 200
    assert rendered.json()["preview_ready"] is False

    calls: list[tuple[Path, Path]] = []

    def fake_convert(source_path: Path, output_path: Path) -> bool:
        calls.append((source_path, output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4 local preview")
        return True

    monkeypatch.setattr(api_module, "_convert_docx_to_pdf", fake_convert)
    preview = client.get(f"/api/jobs/{job['id']}/preview?revision=1")

    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("application/pdf")
    assert preview.content == b"%PDF-1.4 local preview"
    assert calls and calls[0][0].suffix == ".docx"


def test_application_serves_bundled_frontend_without_a_second_service(tmp_path) -> None:
    frontend_dist = tmp_path / "frontend-dist"
    frontend_dist.mkdir()
    (frontend_dist / "index.html").write_text("<title>Doc Converter</title>", encoding="utf-8")

    client = TestClient(create_app(data_root=tmp_path / "data", frontend_dist=frontend_dist))

    response = client.get("/")

    assert response.status_code == 200
    assert "Doc Converter" in response.text


def test_style_pack_edit_creates_a_new_immutable_api_revision(tmp_path) -> None:
    client = TestClient(create_app(data_root=tmp_path))
    original = client.post(
        "/api/style-packs",
        json={"name": "项目报告", "format_id": "docx", "roles": {"body": {"font_size_pt": 12}}},
    ).json()

    revised = client.put(
        f"/api/style-packs/{original['id']}",
        json={
            "base_version": original["version"],
            "name": "项目报告",
            "format_id": "docx",
            "roles": {"body": {"font_size_pt": 14}},
        },
    )

    assert revised.status_code == 201
    assert revised.json()["version"] == 2
    listed = client.get("/api/style-packs").json()
    assert next(pack for pack in listed if pack["id"] == original["id"])["version"] == 2


def test_draft_endpoint_rejects_missing_source_markdown(tmp_path) -> None:
    client = TestClient(create_app(data_root=tmp_path))
    pack = client.post("/api/style-packs", json={"name": "项目报告", "format_id": "docx"}).json()
    job = client.post(
        "/api/jobs",
        data={"style_pack_id": pack["id"], "style_pack_version": str(pack["version"])},
        files={"source": ("方案.md", "# 方案\n", "text/markdown")},
    ).json()

    response = client.put(f"/api/jobs/{job['id']}/draft", json={})

    assert response.status_code == 422


def test_data_root_environment_override_is_used_for_container_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DOC_CONVERTER_DATA_ROOT", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/style-packs")

    assert response.status_code == 200
    assert (tmp_path / "style-packs").exists()
