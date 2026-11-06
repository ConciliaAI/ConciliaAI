from io import BytesIO
import fitz
import pytest
from PIL import Image
from app.document_processing import count_pages, extract_page


def test_pdf_text_count_and_extract():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 60), "Contrato demonstrativo de prestacao de servicos - " * 2)
    raw = doc.tobytes()
    doc.close()
    assert count_pages(raw, ".pdf") == 1
    result = extract_page(raw, ".pdf", 1)
    assert "Contrato demonstrativo" in result.text
    assert result.method == "pdf_text"
    assert result.confidence == 1.0
    assert result.boxes


def test_tiff_multipage_count():
    first = Image.new("RGB", (50, 50), "white")
    second = Image.new("RGB", (50, 50), "black")
    buffer = BytesIO()
    first.save(buffer, format="TIFF", save_all=True, append_images=[second])
    assert count_pages(buffer.getvalue(), ".tiff") == 2


def test_invalid_extension():
    with pytest.raises(ValueError):
        count_pages(b"bad", ".exe")
