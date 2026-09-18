import json

from doc_converter.style_library import StyleLibrary, StylePack, create_style_pack
from doc_converter.style_schema import ROLE_KEYS, default_roles


def test_saved_style_pack_is_versioned_and_listed(tmp_path) -> None:
    library = StyleLibrary(tmp_path)
    pack = create_style_pack(name="正式报告", format_id="docx")

    saved = library.save(pack)

    assert saved.version == 1
    assert library.list_packs() == [saved]
    assert (tmp_path / "style-packs" / saved.id / "1.json").exists()


def test_saving_existing_pack_creates_a_new_immutable_version(tmp_path) -> None:
    library = StyleLibrary(tmp_path)
    first = library.save(create_style_pack(name="正式报告", format_id="docx"))

    second = library.save(first.model_copy(update={"name": "正式报告（调整）"}))

    assert first.version == 1
    assert second.version == 2
    assert library.get(first.id, 1).name == "正式报告"
    assert library.get(second.id, 2).name == "正式报告（调整）"


def test_new_style_pack_contains_all_roles_and_independent_font_slots() -> None:
    pack = create_style_pack(name="模板级报告", format_id="docx")

    assert set(pack.roles) == set(ROLE_KEYS)
    assert pack.schema_version == "docx-style/v2"
    assert pack.roles["body-paragraph"]["font"]["chinese_font"] == "仿宋"
    assert pack.roles["body-paragraph"]["font"]["western_font"] == "Times New Roman"
    assert pack.roles["body-paragraph"]["paragraph"]["line_spacing_pt"] == 29
    assert pack.roles["body-paragraph"]["paragraph"]["first_line_indent_unit"] == "character"
    assert pack.roles["body-paragraph"]["paragraph"]["line_spacing_rule"] == "exact"
    assert pack.roles["abstract"]["font"]["chinese_font"] == "仿宋"
    assert pack.roles["keywords"]["paragraph"]["first_line_indent_pt"] == 0
    assert pack.roles["abstract-label"]["role_type"] == "character"
    assert pack.roles["keywords-label"]["role_type"] == "character"
    assert pack.roles["abstract-content"]["role_type"] == "character"
    assert pack.roles["keywords-content"]["role_type"] == "character"
    assert pack.roles["page"]["page"]["page_width_cm"] == 21.0
    assert pack.roles["page"]["page"]["page_height_cm"] == 29.7


def test_legacy_style_pack_is_migrated_without_losing_custom_values(tmp_path) -> None:
    legacy = {
        "id": "legacy",
        "name": "旧版",
        "format_id": "docx",
        "version": 1,
        "created_at": "2026-09-18T00:00:00Z",
        "roles": {
            "document-title": {"font_name": "黑体", "font_size_pt": 24, "bold": True},
            "heading-1": {"font_name": "楷体", "font_size_pt": 16, "bold": True},
            "body": {"font_name": "仿宋", "font_size_pt": 14, "first_line_indent_pt": 28},
        },
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

    migrated = StylePack.model_validate_json(path.read_text(encoding="utf-8"))

    assert set(migrated.roles) == set(ROLE_KEYS)
    assert migrated.roles["document-title"]["font"]["chinese_font"] == "黑体"
    assert migrated.roles["document-title"]["font"]["size_pt"] == 24
    assert migrated.roles["body-paragraph"]["paragraph"]["first_line_indent_pt"] == 28
    assert migrated.roles["body-paragraph"]["paragraph"]["first_line_indent_unit"] == "pt"
    assert migrated.roles["body-table"] == default_roles()["body-table"]
    assert migrated.roles["abstract"] == default_roles()["abstract"]
    assert migrated.roles["keywords"] == default_roles()["keywords"]
    assert migrated.roles["abstract-label"] == default_roles()["abstract-label"]
    assert migrated.roles["keywords-label"] == default_roles()["keywords-label"]
    assert migrated.roles["abstract-content"] == default_roles()["abstract-content"]
    assert migrated.roles["keywords-content"] == default_roles()["keywords-content"]


def test_style_pack_migrates_indent_units_and_line_spacing_modes() -> None:
    migrated = StylePack.model_validate(
        {
            "id": "units",
            "name": "单位测试",
            "format_id": "docx",
            "version": 1,
            "created_at": "2026-09-18T00:00:00Z",
            "roles": {
                "body-paragraph": {
                    "first_line_indent_pt": 28,
                    "first_line_indent_unit": "cm",
                    "line_spacing_rule": "multiple",
                    "line_spacing_multiple": 1.5,
                }
            },
        }
    )

    paragraph = migrated.roles["body-paragraph"]["paragraph"]
    assert paragraph["first_line_indent_unit"] == "cm"
    assert paragraph["line_spacing_rule"] == "multiple"
    assert paragraph["line_spacing_multiple"] == 1.5


def test_multiple_line_spacing_without_a_value_uses_the_editor_default() -> None:
    migrated = StylePack.model_validate(
        {
            "id": "multiple",
            "name": "多倍行距",
            "format_id": "docx",
            "version": 1,
            "created_at": "2026-09-18T00:00:00Z",
            "roles": {
                "body-paragraph": {
                    "paragraph": {"line_spacing_rule": "multiple"},
                }
            },
        }
    )

    assert migrated.roles["body-paragraph"]["paragraph"]["line_spacing_multiple"] == 1.5
