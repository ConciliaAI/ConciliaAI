"""Transforma cada página em imagem e lê o texto (camada de texto do PDF ou OCR local)."""
import pymupdf as fitz
from PIL import Image, ImageOps

# Scans em alta resolução (ex.: A3 a 600 dpi) passam do limite padrão do Pillow (~89 MP) e seriam recusados.
Image.MAX_IMAGE_PIXELS = 400_000_000
_motor = None


def _ocr():
    global _motor
    if _motor is None:
        from rapidocr_onnxruntime import RapidOCR
        # Detector de texto em até 960 px no lado maior: ~40% mais rápido numa página A4 e a leitura
        # continua igual (medido no lote de teste). det_model_path=None contorna um defeito da biblioteca.
        _motor = RapidOCR(det_limit_side_len=960, det_limit_type="max", det_model_path=None)
    return _motor


def aquecer():
    """Carrega o modelo de OCR antes do primeiro envio (economiza ~3 s na primeira página)."""
    import numpy as np
    from PIL import Image
    _ocr()(np.array(Image.new("RGB", (64, 64), "white")), use_cls=False)


def contar_paginas(caminho: str) -> list[tuple[int, str]]:
    """Lista (índice, tipo) das páginas de um arquivo: pdf ou imagem (TIFF pode ter várias)."""
    low = caminho.lower()
    if low.endswith(".pdf"):
        with fitz.open(caminho) as d:
            if d.needs_pass:
                raise ValueError("PDF protegido por senha")
            return [(i, "pdf") for i in range(d.page_count)]
    with Image.open(caminho) as im:
        n = getattr(im, "n_frames", 1)
    return [(i, "img") for i in range(n)]


def _linhas_pdf(pagina, zoom):
    grupos = {}
    for x0, y0, x1, y1, palavra, b, ln, _ in pagina.get_text("words"):
        g = grupos.setdefault((b, ln), {"t": [], "box": [x0, y0, x1, y1]})
        g["t"].append(palavra)
        bx = g["box"]
        g["box"] = [min(bx[0], x0), min(bx[1], y0), max(bx[2], x1), max(bx[3], y1)]
    out = []
    for g in grupos.values():
        out.append({"text": " ".join(g["t"]), "box": [round(v * zoom) for v in g["box"]]})
    out.sort(key=lambda l: (l["box"][1], l["box"][0]))
    return out


def renderizar(caminho: str, indice: int, origem: str, saida_png: str):
    """Salva a página como PNG e devolve (largura, altura, texto, linhas, fonte_do_texto)."""
    texto, linhas = "", []
    if origem == "pdf":
        zoom = 2.0
        with fitz.open(caminho) as d:
            pg = d[indice]
            pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            pix.save(saida_png)
            larg, alt = pix.width, pix.height
            texto = pg.get_text().strip()
            if len(texto) >= 25:
                linhas = _linhas_pdf(pg, zoom)
    else:
        with Image.open(caminho) as im:
            if indice:
                im.seek(indice)
            im = ImageOps.exif_transpose(im).convert("RGB")
            # 1800 px no lado maior (~150 dpi num A4) basta para o OCR e é mais rápido que 300 dpi.
            if max(im.size) > 1800:
                im.thumbnail((1800, 1800))
            im.save(saida_png)
            larg, alt = im.size
    if len(texto) >= 25 and linhas:
        return larg, alt, texto, linhas, "pdf"
    # Sem o classificador de giro do texto: as linhas de um documento escaneado já vêm na horizontal (mais rápido).
    resultado, _ = _ocr()(saida_png, use_cls=False)
    linhas = []
    for caixa, t, conf in resultado or []:
        xs = [p[0] for p in caixa]
        ys = [p[1] for p in caixa]
        linhas.append({"text": t, "box": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))], "score": float(conf)})
    linhas.sort(key=lambda l: (round(l["box"][1] / 12), l["box"][0]))
    texto = "\n".join(l["text"] for l in linhas)
    return larg, alt, texto, linhas, "ocr"
