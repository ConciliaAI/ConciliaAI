"""Extração por página. Não faz fronteiras nem classificação (fases 4 e 5)."""
from dataclasses import dataclass
from io import BytesIO

import fitz
import pytesseract
from PIL import Image, ImageOps
from pytesseract import Output

ALLOWED_TYPES = {
    ".pdf": "application/pdf", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".tif": "image/tiff", ".tiff": "image/tiff",
}


@dataclass
class OCRResult:
    text: str
    confidence: float
    method: str
    boxes: list[dict]


def count_pages(raw: bytes, ext: str) -> int:
    if ext == ".pdf":
        with fitz.open(stream=raw, filetype="pdf") as doc:
            if doc.needs_pass:
                raise ValueError("PDF protegido por senha")
            return doc.page_count
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        with Image.open(BytesIO(raw)) as im:
            return getattr(im, "n_frames", 1)
    raise ValueError("Tipo de arquivo não suportado")


def _image_ocr(img: Image.Image) -> OCRResult:
    img = ImageOps.exif_transpose(img).convert("RGB")
    data = pytesseract.image_to_data(img, lang="por+eng", output_type=Output.DICT)
    rows = []
    words = []
    confidences = []
    for i, word in enumerate(data["text"]):
        clean = word.strip()
        if not clean:
            continue
        confidence = float(data["conf"][i])
        box = {"text": clean, "x": int(data["left"][i]), "y": int(data["top"][i]),
               "w": int(data["width"][i]), "h": int(data["height"][i]),
               "confidence": max(0, confidence) / 100}
        words.append(box)
        rows.append((int(data["block_num"][i]), int(data["par_num"][i]),
                     int(data["line_num"][i]), clean))
        if confidence >= 0:
            confidences.append(confidence)
    lines: list[str] = []
    last = None
    for b, p, ln, word in rows:
        key = (b, p, ln)
        if key != last:
            lines.append(word)
            last = key
        else:
            lines[-1] += " " + word
    return OCRResult("\n".join(lines), round(sum(confidences) / len(confidences) / 100, 4)
                     if confidences else 0.0, "tesseract", words)


def extract_page(raw: bytes, ext: str, page_number: int) -> OCRResult:
    idx = page_number - 1
    if ext == ".pdf":
        with fitz.open(stream=raw, filetype="pdf") as doc:
            page = doc[idx]
            words = page.get_text("words", sort=True)
            text = page.get_text("text", sort=True).strip()
            # Texto já incorporado evita OCR desnecessário; confiança de origem digital
            # é uma estimativa técnica, não uma probabilidade calibrada.
            if len(text) >= 30:
                boxes = [{"text": str(w[4]), "x": round(w[0], 1), "y": round(w[1], 1),
                          "w": round(w[2]-w[0], 1), "h": round(w[3]-w[1], 1),
                          "confidence": 1.0} for w in words]
                return OCRResult(text, 1.0, "pdf_text", boxes)
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
            with Image.open(BytesIO(pix.tobytes("png"))) as img:
                return _image_ocr(img)
    with Image.open(BytesIO(raw)) as im:
        im.seek(idx)
        return _image_ocr(im.copy())
