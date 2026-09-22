"""Direct DOCX-to-DOCX normalization primitives."""

from doc_converter.docx_direct.analyzer import analyze_docx
from doc_converter.docx_direct.audit import (
    build_normalization_records,
    sha256_file,
    write_audit_bundle,
)
from doc_converter.docx_direct.classifier import action_for_confidence, classify_document
from doc_converter.docx_direct.formatting import clean_uniform_direct_formatting
from doc_converter.docx_direct.model import (
    DirectNormalizeResult,
    DocumentAnalysis,
    ElementAnalysis,
    NormalizationRecord,
)
from doc_converter.docx_direct.normalizer import normalize_docx_direct
from doc_converter.docx_direct.ooxml_patch import (
    parse_xml_payload,
    read_zip_member,
    serialize_xml_payload,
    write_zip_copy,
)
from doc_converter.docx_direct.style_injector import inject_styles_into_docx
from doc_converter.docx_direct.style_mapper import patch_document_xml

__all__ = [
    "DirectNormalizeResult",
    "DocumentAnalysis",
    "ElementAnalysis",
    "NormalizationRecord",
    "action_for_confidence",
    "analyze_docx",
    "build_normalization_records",
    "classify_document",
    "clean_uniform_direct_formatting",
    "inject_styles_into_docx",
    "parse_xml_payload",
    "patch_document_xml",
    "read_zip_member",
    "normalize_docx_direct",
    "serialize_xml_payload",
    "sha256_file",
    "write_audit_bundle",
    "write_zip_copy",
]
