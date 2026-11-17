"""Subtipos identificados por sinais verificáveis no texto de PDF, imagem ou OCR.

Classificação complementar: não substitui o tipo principal nem parser XML.
Pontuações são heurísticas e não representam acurácia/probabilidade de IA.
"""
from __future__ import annotations

import re
import unicodedata

SINAIS = {
    "nfse": (
        (r"\bNFS[\s.-]?E\b", 5, "Sigla NFS-e"),
        (r"\bNOTA\s+FISCAL\s+DE\s+SERVICOS\b", 5, "Nota fiscal de serviços"),
        (r"\bDANFSE\b", 7, "Documento auxiliar da NFS-e"),
        (r"\bPRESTADOR\s+DE\s+SERVICOS\b", 1, "Prestador de serviços"),
    ),
    "danfe": (
        (r"\bDANFE\b", 7, "Documento auxiliar da NF-e"),
        (r"\bDOCUMENTO\s+AUXILIAR\s+DA\s+NOTA\s+FISCAL\s+ELETRONICA\b", 6, "Título de DANFE"),
        (r"\bCHAVE\s+DE\s+ACESSO\b", 1, "Chave de acesso"),
    ),
    "nfce": (
        (r"\bNFC[\s.-]?E\b", 7, "Sigla NFC-e"),
        (r"\bDANFCE\b", 7, "Documento auxiliar da NFC-e"),
        (r"\bNOTA\s+FISCAL\s+DE\s+CONSUMIDOR\s+ELETRONICA\b", 7, "Nota fiscal de consumidor eletrônica"),
    ),
    "cte": (
        (r"\bCT[\s.-]?E\b", 5, "Sigla CT-e"),
        (r"\bDACTE\b", 7, "Documento auxiliar do CT-e"),
        (r"\bCONHECIMENTO\s+DE\s+TRANSPORTE\s+ELETRONICO\b", 7, "Conhecimento de transporte eletrônico"),
    ),
    "aditivo": (
        (r"\bTERMO\s+ADITIVO\b", 7, "Termo aditivo"),
        (r"\bADITIVO\s+(?:AO|DO)\s+CONTRATO\b", 6, "Aditivo ao contrato"),
        (r"\bADITIVO\s+CONTRATUAL\b", 6, "Aditivo contratual"),
    ),
    "distrato": (
        (r"\bTERMO\s+DE\s+DISTRATO\b", 7, "Termo de distrato"),
        (r"\bDISTRATO\s+CONTRATUAL\b", 7, "Distrato contratual"),
    ),
    "boleto": (
        (r"\bBOLETO\s+BANCARIO\b", 7, "Boleto bancário"),
        (r"\bLINHA\s+DIGITAVEL\b", 5, "Linha digitável"),
    ),
    "comprovante_pagamento": (
        (r"\bCOMPROVANTE\s+DE\s+PAGAMENTO\b", 7, "Comprovante de pagamento"),
        (r"\bCOMPROVANTE\s+(?:DE\s+)?PIX\b", 7, "Comprovante Pix"),
        (r"\bTRANSACAO\s+CONCLUIDA\b", 2, "Transação concluída"),
    ),
    "recibo": (
        (r"\bRECIBO\s+DE\s+PAGAMENTO\b", 7, "Recibo de pagamento"),
        (r"\bRECIBO\b", 3, "Título de recibo"),
        (r"\bRECEBI(?:MOS)?\s+DE\b", 2, "Declaração de recebimento"),
    ),
    "contrato": (
        (r"\bCONTRATO\s+DE\s+(?:PRESTACAO|FORNECIMENTO|LOCACAO)\b", 5, "Título contratual"),
        (r"\bINSTRUMENTO\s+PARTICULAR\s+DE\s+CONTRATO\b", 6, "Instrumento particular"),
        (r"\bCONTRATANTE\b", 1, "Parte contratante"),
        (r"\bCONTRATADA\b", 1, "Parte contratada"),
    ),
}
SUBTIPOS = tuple(SINAIS) + ("nao_identificado",)

ROTULOS_SUBTIPOS = {
    "nfse": "NFS-e (serviços)",
    "danfe": "DANFE / NF-e (mercadorias)",
    "nfce": "NFC-e (consumidor)",
    "cte": "CT-e / DACTE (transporte)",
    "aditivo": "Aditivo contratual",
    "distrato": "Distrato contratual",
    "boleto": "Boleto bancário",
    "comprovante_pagamento": "Comprovante de pagamento",
    "recibo": "Recibo",
    "contrato": "Contrato",
    "nao_identificado": "Não identificado",
}
TIPO_COMPATIVEL = {
    "nfse": "Nota fiscal de serviço",
    "danfe": "Nota fiscal de produto (NF-e)",
    "contrato": "Contrato de prestação de serviços",
    "aditivo": "Aditivo contratual",
    "comprovante_pagamento": "Comprovante de pagamento",
}

def normalizar(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in s if not unicodedata.combining(c)).upper()

def identificar_subtipo(texto: str) -> dict:
    conteudo = normalizar((texto or "")[:20000])
    encontrados = []
    for subtipo, sinais in SINAIS.items():
        evidencias = []
        for expressao, peso, descricao in sinais:
            encontrado = re.search(expressao, conteudo)
            if encontrado:
                # Títulos no início do documento têm mais força do que
                # referências incidentais no corpo (ex.: contrato cita aditivo).
                bonus_titulo = 4 if encontrado.start() < 180 and peso >= 5 else 0
                evidencias.append((peso + bonus_titulo, descricao))
        if evidencias:
            encontrados.append((sum(peso for peso, _ in evidencias),
                                subtipo, [descricao for _, descricao in evidencias]))
    if not encontrados:
        return {"subtipo": "nao_identificado", "pontuacao": 0, "evidencias": [],
                "alternativas": [], "revisao_necessaria": True}
    encontrados.sort(key=lambda r: (-r[0], r[1]))
    pontos, subtipo, evidencias = encontrados[0]
    segundo = encontrados[1][0] if len(encontrados) > 1 else 0
    alternativas = [x[1] for x in encontrados[1:3] if x[0] >= pontos - 3]
    return {"subtipo": subtipo, "pontuacao": pontos, "evidencias": evidencias,
            "alternativas": alternativas,
            "revisao_necessaria": bool(pontos < 5 or segundo > 0 and pontos - segundo < 3)}
