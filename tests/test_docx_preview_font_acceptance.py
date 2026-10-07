"""Actual upload/normalize/PDF download: prevent Chinese-font alias fallback.

Failure modes: correct DOCX slots but wrong PDF font, wrong alias family,
mutating the DOCX/source, or configuring the user's normal LibreOffice profile.
The font assertion is local-only because CI does not ship Windows FangSong.
"""

import json
import os
import subprocess
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from doc_converter.api import create_app

_FONT_AUDITOR = os.environ.get("DOCX_FONT_AUDIT_PYTHON")
_FANGSONG = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/simfang.ttf"
_OFFICE = Path("C:/Program Files/LibreOffice/program/soffice.com")


@pytest.mark.skipif(os.name != "nt" or not _FONT_AUDITOR or not _FANGSONG.is_file() or not _OFFICE.is_file(),
                    reason="Requires local Windows FangSong, LibreOffice and DOCX_FONT_AUDIT_PYTHON with pypdf")
def test_real_pdf_uses_requested_chinese_font(tmp_path, monkeypatch):
    monkeypatch.setenv("DOC_CONVERTER_LIBREOFFICE", str(_OFFICE))
    doc = Document()
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "表格正文应使用仿宋字体。"
    buffer = BytesIO()
    doc.save(buffer)
    original = buffer.getvalue()
    (tmp_path / "source.docx").write_bytes(original)
    client = TestClient(create_app(data_root=tmp_path / "app"))
    pack = client.get("/api/style-packs").json()[0]
    response = client.post("/api/jobs", data={"style_pack_id": pack["id"], "style_pack_version": pack["version"], "conversion_mode": "docx-direct"},
                           files={"source": ("source.docx", original, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert response.status_code == 201
    job_id = response.json()["id"]
    rendered = client.post(f"/api/jobs/{job_id}/normalize-docx-direct", json={})
    assert rendered.status_code == 200 and rendered.json()["preview_ready"]
    job = rendered.json()
    pdf = client.get(f"/api/jobs/{job_id}/preview")
    assert pdf.status_code == 200
    path = tmp_path / "preview.pdf"
    path.write_bytes(pdf.content)
    exported = client.get(f"/api/jobs/{job_id}/artifacts/{job['output_name']}")
    assert exported.status_code == 200
    (tmp_path / "normalized.docx").write_bytes(exported.content)
    probe = "from pypdf import PdfReader; import sys,json; r=PdfReader(sys.argv[1]); print(json.dumps(sorted({str(f.get_object().get('/BaseFont')) for p in r.pages for f in p['/Resources'].get('/Font',{}).get_object().values()})))"
    fonts = subprocess.run([str(_FONT_AUDITOR), "-c", probe, str(path)], capture_output=True, text=True, check=True).stdout
    (tmp_path / "font-inventory.txt").write_text(fonts, encoding="utf-8")
    families = {name.split("+")[-1].lstrip("/") for name in json.loads(fonts) if name != "None"}
    assert families == {"FangSong"}, fonts
    assert (tmp_path / "app/jobs" / job_id / "source/original.docx").read_bytes() == original
    assert (tmp_path / "app/jobs" / job_id / job["output_name"]).read_bytes() == exported.content
    (tmp_path / "verification.json").write_text(json.dumps({"passed": True, "source_sha256": sha256(original).hexdigest(),
                                                            "font": "FangSong", "docx_unchanged_by_preview": True}, indent=2), encoding="utf-8")
