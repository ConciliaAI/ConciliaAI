"""Cria os workspaces (clientes da Bernhoeft) e os tipos de documento na primeira execução."""
import json

from . import db

BASE_TIPOS = {
    "Ficha de registro": (["ficha de registro", "registro de empregado"],
                          ["admissao", "cargo", "ctps", "jornada", "salario contratual"]),
    "ASO": (["atestado de saude ocupacional", "a.s.o"],
            ["apto", "inapto", "exame admissional", "exame periodico", "medico do trabalho", "pcmso", "riscos ocupacionais"]),
    "Exame complementar": (["resultado de exame", "laudo laboratorial", "exame complementar"],
                           ["hemograma", "laboratorio", "material", "valores de referencia", "audiometria"]),
    "Holerite": (["recibo de pagamento", "demonstrativo de pagamento", "holerite", "contracheque"],
                 ["salario base", "vencimentos", "descontos", "liquido a receber", "inss", "competencia"]),
    "Guia FGTS": (["fgts digital", "guia do fgts", "guia de recolhimento do fgts"],
                  ["fgts", "recolhimento", "vencimento", "valor total"]),
    "Cartão de ponto": (["cartao de ponto", "folha de ponto", "espelho de ponto"],
                        ["entrada", "saida", "horas extras", "intervalo"]),
    "Documento de identidade": (["carteira de identidade", "registro geral"],
                                ["filiacao", "naturalidade", "data de nascimento", "orgao expedidor"]),
    "CND Federal": (["certidao negativa", "certidao de debitos"],
                    ["receita federal", "divida ativa", "valida ate", "cnpj"]),
    "Comprovante de pagamento": (["comprovante de pagamento", "comprovante de transferencia", "comprovante pix"],
                                 ["favorecido", "autenticacao", "pagador", "pix"]),
    "Contrato social": (["contrato social", "alteracao contratual"],
                        ["socios", "capital social", "clausula", "junta comercial"]),
}
EXTRA = {
    "valealto": {
        "Certificado NR-35": (["nr-35", "nr 35", "trabalho em altura"], ["certificado", "carga horaria", "treinamento"]),
        "Ordem de serviço de segurança": (["ordem de servico"], ["epi", "seguranca do trabalho", "riscos", "capacete"]),
    },
    "santaclara": {
        "Cartão de vacina": (["cartao de vacina", "caderneta de vacinacao", "carteira de vacinacao"],
                             ["dose", "hepatite b", "antitetanica", "lote"]),
    },
}
# Conciliação contratual: tipos do gerador sintético (scripts/generate_synthetic_batch.py).
TIPOS_CONCILIACAO = {
    "Contrato de prestação de serviços": (["contrato de prestacao de servicos"],
                                          ["contratada", "contratante", "objeto", "valor mensal", "instrumento"]),
    "Nota fiscal de serviço": (["nota fiscal de servicos", "nota fiscal de servico", "nfs-e"],
                               ["prestador", "tomador", "data emissao", "valor do servico", "contrato referenciado"]),
    "Aditivo contratual": (["termo aditivo", "aditivo contratual"],
                           ["aditivo", "acrescimo mensal", "vigencia do aditivo"]),
    "Medição de serviços": (["boletim de medicao", "relatorio de medicao"], ["medicao", "periodo medido", "quantidade"]),
    "Comprovante de pagamento": BASE_TIPOS["Comprovante de pagamento"],
}
# Tipo do gabarito sintético -> nome do tipo aqui.
MAPA_GABARITO = {
    "contrato": "Contrato de prestação de serviços",
    "nota_fiscal_servico": "Nota fiscal de serviço",
    "aditivo_contratual": "Aditivo contratual",
    "medicao_ou_relatorio_servico": "Medição de serviços",
    "comprovante_pagamento": "Comprovante de pagamento",
}
WORKSPACES = [
    ("horizonte", "Grupo Horizonte", "Indústria", "#2F6BFF", "GH", ["ASO", "Ficha de registro", "Holerite", "Cartão de ponto"]),
    ("marazul", "Rede Mar Azul", "Supermercados", "#1D47B8", "MA", ["ASO", "Ficha de registro", "Holerite", "Cartão de ponto"]),
    ("valealto", "Construtora Vale Alto", "Construção civil", "#0F1E3D", "VA", ["ASO", "Ficha de registro", "Certificado NR-35", "Ordem de serviço de segurança"]),
    ("santaclara", "Hospital Santa Clara", "Saúde", "#F5B700", "SC", ["ASO", "Ficha de registro", "Holerite", "Cartão de vacina"]),
    ("atlantica", "Atlântica Facilities", "Contratos e notas de fornecedores", "#4B5E8C", "AF", []),
]


def semear():
    """Cria os clientes que ainda não existem (também em bancos de versões anteriores)."""
    for i, (wid, nome, setor, cor, sigla, exigidos) in enumerate(WORKSPACES):
        if db.q("SELECT 1 FROM workspaces WHERE id=?", (wid,)):
            continue
        db.x("INSERT INTO workspaces VALUES(?,?,?,?,?,?)", (wid, nome, setor, cor, sigla, i))
        if wid == "atlantica":
            tipos = dict(TIPOS_CONCILIACAO)
        else:
            tipos = dict(BASE_TIPOS)
            tipos.update(EXTRA.get(wid, {}))
        for nome_t, (tit, pal) in tipos.items():
            db.x("INSERT INTO tipos(ws, nome, titulos, palavras, exigido) VALUES(?,?,?,?,?)",
                 (wid, nome_t, json.dumps(tit), json.dumps(pal), 1 if nome_t in exigidos else 0))
