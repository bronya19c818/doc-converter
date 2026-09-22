"""Direct DOCX-to-DOCX normalization primitives."""

from doc_converter.docx_direct.analyzer import analyze_docx
from doc_converter.docx_direct.classifier import action_for_confidence, classify_document
from doc_converter.docx_direct.model import (
    DirectNormalizeResult,
    DocumentAnalysis,
    ElementAnalysis,
    NormalizationRecord,
)
from doc_converter.docx_direct.ooxml_patch import read_zip_member, write_zip_copy
from doc_converter.docx_direct.style_injector import inject_styles_into_docx

__all__ = [
    "DirectNormalizeResult",
    "DocumentAnalysis",
    "ElementAnalysis",
    "NormalizationRecord",
    "action_for_confidence",
    "analyze_docx",
    "classify_document",
    "inject_styles_into_docx",
    "read_zip_member",
    "write_zip_copy",
]
