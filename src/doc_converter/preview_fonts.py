"""Resolve standard Chinese/English family aliases in isolated PDF profiles."""

from pathlib import Path
from xml.etree import ElementTree as ET

_REGISTRY = "http://openoffice.org/2001/registry"
_ALIASES = {"仿宋": "FangSong", "楷体": "KaiTi", "宋体": "SimSun", "黑体": "SimHei",
            "新宋体": "NSimSun", "微软雅黑": "Microsoft YaHei"}


def prepare_pdf_font_aliases(profile: Path) -> None:
    """Create only the new task profile; never change user profiles or DOCX fonts.

    LibreOffice can fail to resolve localized family names absent from a source
    font table. These are names of the same families, not substitute typefaces.
    """
    registry = profile / "user/registrymodifications.xcu"
    registry.parent.mkdir(parents=True, exist_ok=True)
    if registry.exists():
        raise ValueError("PDF font aliases require a fresh private LibreOffice profile")
    root = ET.Element("oor:items", {"xmlns:oor": _REGISTRY})
    path = "/org.openoffice.Office.Common/Font/Substitution"
    item = ET.SubElement(root, "item", {"oor:path": path})
    prop = ET.SubElement(item, "prop", {"oor:name": "Replacement", "oor:op": "fuse"})
    ET.SubElement(prop, "value").text = "true"
    pairs = ET.SubElement(root, "item", {"oor:path": path + "/FontPairs"})
    for index, (localized, family) in enumerate(_ALIASES.items()):
        node = ET.SubElement(pairs, "node", {"oor:name": f"_{index}", "oor:op": "replace"})
        for key, value in {"ReplaceFont": localized, "SubstituteFont": family,
                           "Always": "true", "OnScreenOnly": "false"}.items():
            prop = ET.SubElement(node, "prop", {"oor:name": key})
            ET.SubElement(prop, "value").text = value
    registry.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
