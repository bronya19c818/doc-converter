"""Direct DOCX-to-DOCX normalization primitives."""

from doc_converter.docx_direct.analyzer import analyze_docx
from doc_converter.docx_direct.model import (
    DirectNormalizeResult,
    DocumentAnalysis,
    ElementAnalysis,
    NormalizationRecord,
)

__all__ = [
    "DirectNormalizeResult",
    "DocumentAnalysis",
    "ElementAnalysis",
    "NormalizationRecord",
    "analyze_docx",
]
