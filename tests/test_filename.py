from doc_converter.filename import safe_docx_filename


def test_filename_uses_title_and_removes_windows_path_characters() -> None:
    assert safe_docx_filename('项目:方案/2026?', 'source.md') == '项目_方案_2026_.docx'


def test_filename_falls_back_to_source_stem() -> None:
    assert safe_docx_filename(None, '原始方案.markdown') == '原始方案.docx'
