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
    assert pack.schema_version == "docx-style/v3"
    assert pack.roles["body-paragraph"]["font"]["chinese_font"] == "仿宋"
    assert pack.roles["body-paragraph"]["font"]["western_font"] == "Times New Roman"
    assert pack.roles["body-paragraph"]["paragraph"]["line_spacing_pt"] == 29
    assert pack.roles["body-paragraph"]["paragraph"]["first_line_indent_unit"] == "character"
    assert pack.roles["body-paragraph"]["paragraph"]["line_spacing_rule"] == "exact"
    assert pack.roles["abstract-content"]["font"]["chinese_font"] == "楷体"
    assert pack.roles["keywords-label"]["paragraph"]["left_indent_unit"] == "character"
    assert pack.roles["abstract-label"]["role_type"] == "paragraph"
    assert pack.roles["keywords-label"]["role_type"] == "paragraph"
    assert pack.roles["abstract-content"]["role_type"] == "character"
    assert pack.roles["keywords-content"]["role_type"] == "character"
    assert {f"heading-{level}" for level in range(1, 7)} <= set(pack.roles)
    assert pack.roles["page"]["page"]["page_width_cm"] == 21.0
    assert pack.roles["page"]["page"]["page_height_cm"] == 29.7


def test_default_roles_include_independent_table_headers_and_image_layout() -> None:
    roles = default_roles()

    assert roles["table-row-header"]["role_type"] == "paragraph"
    assert roles["table-column-header"]["role_type"] == "paragraph"
    assert roles["table-row-header"]["font"]["bold"] is True
    assert roles["table-column-header"]["font"]["bold"] is True
    assert roles["table-row-header"]["paragraph"]["alignment"] == "left"
    assert roles["table-column-header"]["paragraph"]["alignment"] == "center"
    assert roles["image"]["role_type"] == "image"
    assert roles["image"]["image"]["alignment"] == "center"
    assert roles["image"]["image"].get("max_width_cm") is None
    assert roles["image"]["image"]["space_before_pt"] == 0
    assert roles["image"]["image"]["space_after_pt"] == 0


def test_style_pack_migrates_custom_image_and_table_header_roles() -> None:
    migrated = StylePack.model_validate(
        {
            "id": "new-roles",
            "name": "图片与表格标题",
            "format_id": "docx",
            "created_at": "2026-09-18T00:00:00Z",
            "roles": {
                "image": {
                    "role_type": "image",
                    "image": {
                        "alignment": "right",
                        "max_width_cm": 8.5,
                        "space_before_pt": 2.5,
                        "space_after_pt": 4,
                    },
                },
                "table-row-header": {
                    "role_type": "paragraph",
                    "font": {"chinese_font": "黑体", "size_pt": 12, "bold": True},
                    "paragraph": {"alignment": "right"},
                },
            },
        }
    )

    assert migrated.roles["image"]["image"] == {
        "alignment": "right",
        "max_width_cm": 8.5,
        "space_before_pt": 2.5,
        "space_after_pt": 4.0,
    }
    assert migrated.roles["table-row-header"]["font"]["chinese_font"] == "黑体"
    assert migrated.roles["table-row-header"]["paragraph"]["alignment"] == "right"
    assert migrated.roles["table-column-header"] == default_roles()["table-column-header"]


def test_v3_metadata_paragraph_settings_move_to_label_roles() -> None:
    pack = StylePack.model_validate(
        {
            "id": "metadata-v3",
            "name": "旧摘要角色",
            "format_id": "docx",
            "version": 3,
            "created_at": "2026-09-18T00:00:00Z",
            "schema_version": "docx-style/v3",
            "roles": {
                "abstract-label": {
                    "role_type": "character",
                    "font": {
                        "chinese_font": "黑体",
                        "western_font": "Arial",
                        "size_pt": 9,
                        "bold": True,
                    },
                },
                "abstract-content": {
                    "role_type": "paragraph",
                    "font": {
                        "chinese_font": "楷体",
                        "western_font": "Times New Roman",
                        "size_pt": 10,
                    },
                    "paragraph": {
                        "alignment": "justify",
                        "first_line_indent_pt": 20,
                        "first_line_indent_unit": "character",
                        "line_spacing_pt": 16,
                    },
                },
                "keywords-label": {
                    "role_type": "character",
                    "font": {
                        "chinese_font": "黑体",
                        "western_font": "Arial",
                        "size_pt": 9,
                        "bold": True,
                    },
                },
                "keywords-content": {
                    "role_type": "paragraph",
                    "font": {
                        "chinese_font": "宋体",
                        "western_font": "Times New Roman",
                        "size_pt": 11,
                    },
                    "paragraph": {
                        "alignment": "left",
                        "space_after_pt": 6,
                    },
                },
            },
        }
    )

    abstract_label = pack.roles["abstract-label"]
    abstract_content = pack.roles["abstract-content"]
    assert abstract_label["role_type"] == "paragraph"
    assert abstract_label["font"]["chinese_font"] == "黑体"
    assert abstract_label["paragraph"]["first_line_indent_pt"] == 20
    assert abstract_label["paragraph"]["first_line_indent_unit"] == "character"
    assert abstract_content["role_type"] == "character"
    assert abstract_content["font"]["chinese_font"] == "楷体"
    assert "paragraph" not in abstract_content

    keywords_label = pack.roles["keywords-label"]
    keywords_content = pack.roles["keywords-content"]
    assert keywords_label["role_type"] == "paragraph"
    assert keywords_label["paragraph"]["space_after_pt"] == 6
    assert keywords_content["role_type"] == "character"
    assert keywords_content["font"]["chinese_font"] == "宋体"
    assert "paragraph" not in keywords_content


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
    assert migrated.roles["abstract-label"] == default_roles()["abstract-label"]
    assert migrated.roles["keywords-label"] == default_roles()["keywords-label"]
    assert migrated.roles["abstract-content"] == default_roles()["abstract-content"]
    assert migrated.roles["keywords-content"] == default_roles()["keywords-content"]
    assert "abstract" not in migrated.roles
    assert "keywords" not in migrated.roles


def test_v2_abstract_and_keyword_roles_migrate_to_label_paragraph_roles() -> None:
    migrated = StylePack.model_validate(
        {
            "id": "v2",
            "name": "旧摘要角色",
            "format_id": "docx",
            "created_at": "2026-09-18T00:00:00Z",
            "roles": {
                "abstract": {"font_name": "仿宋", "font_size_pt": 12, "first_line_indent_pt": 24},
                "abstract-content": {"font_name": "楷体", "font_size_pt": 11},
                "keywords": {"font_name": "宋体", "font_size_pt": 10},
            },
        }
    )

    assert migrated.roles["abstract-label"]["role_type"] == "paragraph"
    assert migrated.roles["abstract-content"]["role_type"] == "character"
    assert migrated.roles["abstract-content"]["font"]["chinese_font"] == "楷体"
    assert migrated.roles["abstract-content"]["font"]["size_pt"] == 11
    assert migrated.roles["abstract-label"]["paragraph"]["first_line_indent_pt"] == 24
    assert migrated.roles["abstract-label"]["paragraph"]["first_line_indent_unit"] == "pt"
    assert migrated.roles["keywords-label"]["role_type"] == "paragraph"
    assert migrated.roles["keywords-content"]["role_type"] == "character"
    assert migrated.roles["keywords-content"]["font"]["chinese_font"] == "宋体"
    assert migrated.roles["keywords-content"]["font"]["size_pt"] == 10


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
