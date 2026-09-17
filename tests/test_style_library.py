from doc_converter.style_library import StyleLibrary, create_style_pack


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
