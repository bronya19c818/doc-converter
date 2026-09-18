from fastapi.testclient import TestClient

from doc_converter.api import create_app


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
