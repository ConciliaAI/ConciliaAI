"""Encontra e esconde dados sensíveis no texto e na imagem das páginas."""
import re

from PIL import Image, ImageDraw

PADROES = {
    "cpf": [r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", r"\b\d{11}\b",
            r"(?i)\b(?:RG|R\.G\.)\s*(?:n[ºo°.]*)?\s*:?\s*[\dXx][\dXx.\-]{4,13}"],
    "banco": [r"(?i)\bAg(?:[êe]ncia|\.)\s*:?\s*\d{3,5}(?:-\d)?\s*[,;/]?\s*(?:Conta(?:\s+corrente)?|C/C|CC)\s*:?\s*[\d.\-]{4,15}"],
    "saude": [r"(?i)\bCID[\s\-:]*[A-Z]\d{2}(?:\.\d)?\b", r"(?i)\bdiagn[oó]stico\s*:\s*[^\n]{3,80}"],
    "endereco": [r"(?i)\b(?:Rua|Avenida|Av\.|Travessa|Alameda)\s+[^\n,]{3,60},?\s*(?:n[ºo°.]*\s*)?\d+"],
    "contato": [r"\(?\b\d{2}\)?\s?9?\d{4}-\d{4}\b", r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"],
}
ROTULO = {"cpf": "CPF/RG protegido", "banco": "conta protegida", "saude": "dado de saúde protegido",
          "endereco": "endereço protegido", "contato": "contato protegido"}


def ativos(cfg: dict) -> list[str]:
    return [k for k in PADROES if cfg.get(k) == "1"]


def achar(texto: str, cats: list[str], extras: list[dict] | None = None):
    """Devolve lista de (inicio, fim, categoria) sem sobreposição."""
    achados = []
    for c in cats:
        for p in PADROES[c]:
            for m in re.finditer(p, texto or ""):
                achados.append((m.start(), m.end(), c))
    for e in extras or []:
        c, trecho = e.get("categoria"), (e.get("trecho") or "").strip()
        if c in cats and len(trecho) >= 4:
            i = (texto or "").find(trecho)
            while i >= 0:
                achados.append((i, i + len(trecho), c))
                i = texto.find(trecho, i + 1)
    achados.sort()
    limpo = []
    for a in achados:
        if limpo and a[0] < limpo[-1][1]:
            if a[1] > limpo[-1][1]:
                limpo[-1] = (limpo[-1][0], a[1], limpo[-1][2])
            continue
        limpo.append(a)
    return limpo


def mascarar_texto(texto: str, cats: list[str], extras=None, html=False) -> str:
    if not texto:
        return ""
    out, pos = [], 0
    for i, f, c in achar(texto, cats, extras):
        out.append(texto[pos:i])
        out.append(f"⟦{ROTULO[c]}⟧")
        pos = f
    out.append(texto[pos:])
    return "".join(out)


def mascarar_imagem(caminho_png: str, linhas: list[dict], cats: list[str], extras=None) -> Image.Image:
    im = Image.open(caminho_png).convert("RGB")
    if not cats:
        return im
    d = ImageDraw.Draw(im)
    for ln in linhas or []:
        t = ln.get("text", "")
        if not t:
            continue
        x0, y0, x1, y1 = ln["box"]
        for i, f, _ in achar(t, cats, extras):
            a = x0 + (x1 - x0) * i / len(t)
            b = x0 + (x1 - x0) * f / len(t)
            d.rectangle([a - 3, y0 - 2, b + 3, y1 + 2], fill=(15, 30, 61))
    return im
