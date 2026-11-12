"""Cria os workspaces (clientes da Bernhoeft) e os tipos de documento na primeira execução.

O foco é a nota fiscal de serviço: os outros tipos existem para que o lote misturado seja separado
e para que contratos e aditivos sirvam de referência na conciliação.
"""
import json

from . import db

TIPOS = {
    "Nota fiscal de serviço": (["nota fiscal de servicos", "nota fiscal de servico", "nfs-e", "danfse",
                                "documento auxiliar da nfs-e", "nota fiscal eletronica de servico"],
                               ["prestador", "tomador", "data emissao", "valor do servico", "competencia",
                                "contrato referenciado", "iss", "codigo de tributacao"]),
    "Nota fiscal de produto (NF-e)": (["danfe", "documento auxiliar da nota fiscal eletronica", "nf-e"],
                                      ["chave de acesso", "natureza da operacao", "protocolo de autorizacao", "icms",
                                       "ncm", "cfop", "destinatario", "valor total da nota", "emitente"]),
    "Contrato de prestação de serviços": (["contrato de prestacao de servicos", "contrato de prestacao de servico"],
                                          ["contratada", "contratante", "objeto", "valor mensal", "instrumento",
                                           "clausula", "vigencia"]),
    "Aditivo contratual": (["termo aditivo", "aditivo contratual"],
                           ["aditivo", "acrescimo mensal", "vigencia do aditivo"]),
    "Medição de serviços": (["boletim de medicao", "relatorio de medicao"],
                            ["medicao", "periodo medido", "quantidade"]),
    "Comprovante de pagamento": (["comprovante de pagamento", "comprovante de transferencia", "comprovante pix"],
                                 ["favorecido", "autenticacao", "pagador", "pix"]),
}
# Tipo do gabarito sintético -> nome do tipo aqui.
MAPA_GABARITO = {
    "contrato": "Contrato de prestação de serviços",
    "nota_fiscal_servico": "Nota fiscal de serviço",
    "aditivo_contratual": "Aditivo contratual",
    "medicao_ou_relatorio_servico": "Medição de serviços",
    "comprovante_pagamento": "Comprovante de pagamento",
}
# Clientes fictícios da Bernhoeft (cada um é um workspace separado).
WORKSPACES = [
    ("atlantica", "Atlântica Facilities", "Serviços terceirizados", "#2F6BFF", "AF"),
    ("horizonte", "Grupo Horizonte", "Indústria", "#1D47B8", "GH"),
    ("marazul", "Rede Mar Azul", "Supermercados", "#0F1E3D", "MA"),
    ("santaclara", "Hospital Santa Clara", "Saúde", "#F5B700", "SC"),
]


CORES = ["#2F6BFF", "#1D47B8", "#0F1E3D", "#F5B700", "#4B5E8C"]


def criar_cliente(nome: str, setor: str = "", cnpj: str | None = None) -> str:
    """Cadastra um cliente novo da Bernhoeft (um workspace) com os tipos de documento padrão."""
    import re
    import unicodedata

    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    wid = re.sub(r"[^a-z0-9]+", "", base)[:20] or "cliente"
    sufixo, final = 1, wid
    while db.q("SELECT 1 FROM workspaces WHERE id=?", (final,)):
        sufixo += 1
        final = f"{wid}{sufixo}"
    palavras = [p for p in re.findall(r"[A-Za-zÀ-ü]+", nome) if len(p) > 2] or [nome]
    sigla = "".join(p[0] for p in palavras[:2]).upper() or "CL"
    ordem = (db.q("SELECT COALESCE(MAX(ordem), 0) m FROM workspaces", um=True)["m"] or 0) + 1
    db.x("INSERT INTO workspaces(id, nome, setor, cor, sigla, ordem, cnpj) VALUES(?,?,?,?,?,?,?)",
         (final, nome, setor or "Cliente", CORES[ordem % len(CORES)], sigla, ordem, cnpj))
    for nome_t, (tit, pal) in TIPOS.items():
        db.x("INSERT INTO tipos(ws, nome, titulos, palavras, exigido) VALUES(?,?,?,?,?)",
             (final, nome_t, json.dumps(tit), json.dumps(pal), 0))
    return final


def semear():
    """Cria os clientes que ainda não existem e acrescenta tipos novos aos clientes já criados."""
    for w in db.q("SELECT id FROM workspaces"):
        for nome_t, (tit, pal) in TIPOS.items():
            if not db.q("SELECT 1 FROM tipos WHERE ws=? AND nome=?", (w["id"], nome_t)):
                db.x("INSERT INTO tipos(ws, nome, titulos, palavras, exigido) VALUES(?,?,?,?,?)",
                     (w["id"], nome_t, json.dumps(tit), json.dumps(pal), 0))
    for i, (wid, nome, setor, cor, sigla) in enumerate(WORKSPACES):
        if db.q("SELECT 1 FROM workspaces WHERE id=?", (wid,)):
            continue
        db.x("INSERT INTO workspaces(id, nome, setor, cor, sigla, ordem) VALUES(?,?,?,?,?,?)", (wid, nome, setor, cor, sigla, i))
        for nome_t, (tit, pal) in TIPOS.items():
            db.x("INSERT INTO tipos(ws, nome, titulos, palavras, exigido) VALUES(?,?,?,?,?)",
                 (wid, nome_t, json.dumps(tit), json.dumps(pal), 0))
