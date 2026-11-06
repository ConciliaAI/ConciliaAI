"""Mede o acerto da IA comparando um envio com o gabarito (ground_truth.json) do gerador sintético.

O gerador é o de scripts/generate_synthetic_batch.py (criado na versão Docker do projeto). Ele monta um
PDF com documentos embaralhados e guarda, para cada página, a qual documento e tipo ela pertence.
"""
import importlib.util
import json
from datetime import datetime
from pathlib import Path

from . import db, seed
from .config import BASE, DADOS


def _gerador():
    caminho = BASE / "scripts" / "generate_synthetic_batch.py"
    spec = importlib.util.spec_from_file_location("gerador_sintetico", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gerar_lote(fornecedores: int = 4, notas: int = 3, digitalizar: bool = True, semente: int | None = None) -> Path:
    """Gera um lote sintético novo e devolve a pasta (com lotes/lote_misturado.pdf e ground_truth.json)."""
    pasta = DADOS / "sintetico" / datetime.now().strftime("lote-%Y%m%d-%H%M%S")
    pasta.parent.mkdir(parents=True, exist_ok=True)
    semente = semente if semente is not None else int(datetime.now().timestamp()) % 100000
    _gerador().generate(pasta, fornecedores, notas, semente, digitalizar)
    return pasta


def digitalizar(pdf: Path, destino: Path, semente: int = 7) -> Path:
    """Transforma o lote em PDF num TIFF multipágina só de imagem (como sai de um scanner).
    Algumas folhas saem tortas, borradas ou apagadas, para testar o OCR e a fila de revisão."""
    import random

    import pymupdf as fitz
    from PIL import Image, ImageEnhance, ImageFilter

    rng = random.Random(semente)
    paginas = []
    with fitz.open(pdf) as d:
        for pg in d:
            pix = pg.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), colorspace=fitz.csGRAY)
            im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            sorte = rng.random()
            if sorte < 0.06:  # folha ruim (xerox apagado, torto e fora de foco): deve ir para revisão humana
                im = im.rotate(rng.choice([-5, 4.5]), fillcolor=255, expand=False)
                im = im.filter(ImageFilter.GaussianBlur(3.2))
                im = ImageEnhance.Brightness(ImageEnhance.Contrast(im).enhance(0.22)).enhance(1.25)
            elif sorte < 0.45:  # leve inclinação e ruído de scanner
                im = im.rotate(rng.choice([-0.8, 0.6, 1.1]), fillcolor=255, expand=False)
                im = im.filter(ImageFilter.GaussianBlur(0.4))
            paginas.append(im)
    paginas[0].save(destino, save_all=True, append_images=paginas[1:], compression="tiff_deflate", dpi=(115, 115))
    return destino


def medir(gabarito: dict, docs: list[dict], paginas: list[dict]) -> dict:
    """Compara documentos previstos (pag_ini, pag_fim, tipo, status) com o gabarito."""
    inicios_v = set(gabarito["boundary_start_pages"])
    inicios_p = {d["pag_ini"] for d in docs}
    acertos_i = len(inicios_v & inicios_p)
    precisao = acertos_i / len(inicios_p) if inicios_p else 0.0
    cobertura = acertos_i / len(inicios_v) if inicios_v else 0.0
    f1 = 2 * precisao * cobertura / (precisao + cobertura) if precisao + cobertura else 0.0

    por_inicio = {d["pag_ini"]: d for d in docs}
    exatos, tipo_ok, detalhes = 0, 0, []
    for g in gabarito["documents"]:
        esperado = seed.MAPA_GABARITO.get(g["type"], g["type"])
        p = por_inicio.get(g["batch_start_page"])
        exato = bool(p and p["pag_fim"] == g["batch_end_page"])
        certo = bool(exato and p["tipo"] == esperado)
        exatos += exato
        tipo_ok += certo
        if not certo:
            detalhes.append({
                "documento": g["document_id"], "paginas": f"{g['batch_start_page']}–{g['batch_end_page']}",
                "esperado": esperado,
                "previsto": (f"{p['tipo']} (págs. {p['pag_ini']}–{p['pag_fim']})" if p else "início não detectado"),
            })

    tipo_pagina = {}
    for d in docs:
        for n in range(d["pag_ini"], d["pag_fim"] + 1):
            tipo_pagina[n] = d["tipo"]
    pags_ok = sum(1 for m in gabarito["page_map"]
                  if tipo_pagina.get(m["batch_page"]) == seed.MAPA_GABARITO.get(m["type"], m["type"]))

    auto = [d for d in docs if d["status"] == "confirmado" and not d.get("decisao")]
    revisao = [d for d in docs if d["status"] == "revisao"]
    certos_auto = 0
    for d in auto:
        g = next((x for x in gabarito["documents"] if x["batch_start_page"] == d["pag_ini"]), None)
        if g and g["batch_end_page"] == d["pag_fim"] and seed.MAPA_GABARITO.get(g["type"]) == d["tipo"]:
            certos_auto += 1
    n_doc = len(gabarito["documents"])
    pct = lambda a, b: round(100 * a / b, 1) if b else 0.0
    return {
        "paginas": gabarito["batch_total_pages"], "documentos_gabarito": n_doc, "documentos_previstos": len(docs),
        "fronteira_precisao": pct(precisao, 1), "fronteira_cobertura": pct(cobertura, 1), "fronteira_f1": pct(f1, 1),
        "segmentacao_exata": pct(exatos, n_doc), "tipo_correto": pct(tipo_ok, n_doc),
        "paginas_tipo_correto": pct(pags_ok, gabarito["batch_total_pages"]),
        "enviados_revisao": len(revisao), "pct_revisao": pct(len(revisao), len(docs)),
        "acerto_automaticos": pct(certos_auto, len(auto)), "automaticos": len(auto),
        "erros": detalhes[:15], "total_erros": len(detalhes),
    }


def medir_envio(eid: int) -> dict | None:
    e = db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)
    if not e or not e.get("gabarito") or e["status"] != "concluido":
        return None
    gabarito = json.loads(Path(e["gabarito"]).read_text(encoding="utf-8"))
    docs = db.q("SELECT * FROM docs WHERE envio_id=? ORDER BY pag_ini", (eid,))
    pags = db.q("SELECT n, tipo FROM paginas WHERE envio_id=?", (eid,))
    r = medir(gabarito, docs, pags)
    from . import conciliacao  # evita import circular (conciliacao -> analise)
    r["conciliacao"] = conciliacao.medir(e["ws"], gabarito)
    return r
