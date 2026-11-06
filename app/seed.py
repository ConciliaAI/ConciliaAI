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


def semear():
    """Cria os clientes que ainda não existem."""
    for i, (wid, nome, setor, cor, sigla) in enumerate(WORKSPACES):
        if db.q("SELECT 1 FROM workspaces WHERE id=?", (wid,)):
            continue
        db.x("INSERT INTO workspaces VALUES(?,?,?,?,?,?)", (wid, nome, setor, cor, sigla, i))
        for nome_t, (tit, pal) in TIPOS.items():
            db.x("INSERT INTO tipos(ws, nome, titulos, palavras, exigido) VALUES(?,?,?,?,?)",
                 (wid, nome_t, json.dumps(tit), json.dumps(pal), 0))
