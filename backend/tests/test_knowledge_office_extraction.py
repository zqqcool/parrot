from __future__ import annotations

import io
from typing import Any, cast

import pytest
from docx import Document
from docx.shared import Inches
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from PIL import Image

from app.core.errors import AppError
from app.modules.knowledge.extraction.docx import DocxDocumentExtractor
from app.modules.knowledge.extraction.xlsx import XlsxDocumentExtractor
from app.modules.knowledge.extractor import KnowledgeExtractionError
from app.modules.knowledge.ingestion_validation import validate_uploaded_file


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color=(0, 128, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def _docx_with_heading_table_and_image() -> bytes:
    document = Document()
    document.add_heading("3. Login", level=1)
    document.add_heading("3.1 SSO", level=2)
    document.add_paragraph("步骤 1 打开门户")
    document.add_paragraph("Click Sign in with SSO")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Field"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Provider"
    table.cell(1, 1).text = "Okta"
    table.cell(1, 0).paragraphs[0].add_run().add_picture(
        io.BytesIO(_png_bytes()), width=Inches(1.0)
    )
    document.add_paragraph("2) Confirm access")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _xlsx_with_region_and_image() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Orders"
    sheet["A1"] = "SKU"
    sheet["B1"] = "Qty"
    sheet["A2"] = "ABC-1"
    sheet["B2"] = 3
    sheet["A3"] = "ABC-2"
    sheet["B3"] = 5
    image = Image.new("RGB", (24, 24), color=(255, 0, 0))
    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    from openpyxl.drawing.image import Image as XLImage

    sheet.add_image(XLImage(io.BytesIO(image_buffer.getvalue())), "C2")
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _xlsx_with_chart() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Month", "Count"])
    sheet.append(["Jan", 3])
    sheet.append(["Feb", 5])
    chart = cast(Any, BarChart())
    chart.add_data(Reference(sheet, min_col=2, min_row=1, max_row=3), titles_from_data=True)
    cast(Any, sheet).add_chart(chart, "D2")
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_docx_validation_accepts_ooxml_word() -> None:
    content = _docx_with_heading_table_and_image()
    item = validate_uploaded_file(
        content,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "manual.docx",
        5_000_000,
    )
    assert item.extension == ".docx"


def test_docx_extractor_builds_sections_tables_and_embedded_images() -> None:
    extracted = DocxDocumentExtractor().extract(
        _docx_with_heading_table_and_image(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        max_chars=50_000,
        max_pdf_pages=10,
        max_slides=10,
        max_embedded_images=20,
    )
    assert extracted.format_profile == "docx"
    assert any(block.block_kind == "table" for block in extracted.blocks)
    assert any("Sign in with SSO" in block.index_text for block in extracted.blocks)
    assert extracted.media
    assert all(item.asset_kind == "embedded" for item in extracted.media)
    assert any(group.kind == "procedure_step" for group in extracted.groups)


def test_docx_extractor_rejects_silent_text_truncation() -> None:
    with pytest.raises(KnowledgeExtractionError, match="KNOWLEDGE_EXTRACTED_TEXT_TOO_LARGE"):
        DocxDocumentExtractor().extract(
            _docx_with_heading_table_and_image(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            max_chars=10,
            max_pdf_pages=10,
            max_slides=10,
        )


def test_xlsx_validation_and_region_extraction() -> None:
    content = _xlsx_with_region_and_image()
    item = validate_uploaded_file(
        content,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "orders.xlsx",
        5_000_000,
    )
    assert item.extension == ".xlsx"
    extracted = XlsxDocumentExtractor().extract(
        content,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        max_chars=50_000,
        max_pdf_pages=10,
        max_slides=10,
        max_sheets=10,
        max_rows_per_region=100,
        max_embedded_images=20,
    )
    assert extracted.format_profile == "xlsx"
    assert extracted.sheet_count == 1
    assert any(block.sheet_name == "Orders" for block in extracted.blocks)
    assert any("ABC-1" in block.index_text for block in extracted.blocks)
    assert extracted.groups
    assert extracted.groups[0].kind == "table_region"


def test_xlsx_extractor_reports_skipped_charts() -> None:
    extracted = XlsxDocumentExtractor().extract(
        _xlsx_with_chart(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        max_chars=50_000,
        max_pdf_pages=10,
        max_slides=10,
        max_sheets=10,
        max_rows_per_region=100,
    )

    assert extracted.skipped_media_count == 1
    assert extracted.warnings == ("charts_skipped",)


def test_xlsx_extractor_rejects_sheet_limit_instead_of_silently_dropping_sheets() -> None:
    workbook = Workbook()
    first = workbook.active
    assert first is not None
    first["A1"] = "first"
    workbook.create_sheet("Second")["A1"] = "second"
    buffer = io.BytesIO()
    workbook.save(buffer)

    with pytest.raises(KnowledgeExtractionError, match="KNOWLEDGE_XLSX_SHEET_LIMIT"):
        XlsxDocumentExtractor().extract(
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            max_chars=50_000,
            max_pdf_pages=10,
            max_slides=10,
            max_sheets=1,
        )


def test_ooxml_validation_rejects_cross_format_package() -> None:
    with pytest.raises(AppError) as error:
        validate_uploaded_file(
            _xlsx_with_region_and_image(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "manual.docx",
            5_000_000,
        )

    assert error.value.code == "KNOWLEDGE_FILE_CONTENT_INVALID"
