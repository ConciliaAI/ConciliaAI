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
# Conta de demonstração: a empresa dona dos clientes fictícios e dos usuários admin, revisor e operador.
# Bancos criados antes das contas existirem passam inteiros para ela.
CONTA_DEMO = "demo"
NOME_CONTA_DEMO = "Bernhoeft (demonstração)"

# Clientes fictícios da conta de demonstração (cada um é um workspace separado).
WORKSPACES = [
    ("atlantica", "Atlântica Facilities", "Serviços terceirizados", "#2F6BFF", "AF"),
    ("horizonte", "Grupo Horizonte", "Indústria", "#1D47B8", "GH"),
    ("marazul", "Rede Mar Azul", "Supermercados", "#0F1E3D", "MA"),
    ("santaclara", "Hospital Santa Clara", "Saúde", "#F5B700", "SC"),
]


CORES = ["#2F6BFF", "#1D47B8", "#0F1E3D", "#F5B700", "#4B5E8C"]


def criar_conta(nome: str) -> str:
    """Cria a conta de uma empresa (sem workspaces: ela cria os dos seus clientes depois)."""
    import secrets
    cid = "c" + secrets.token_hex(6)
    db.x("INSERT INTO contas(id, nome, criado_em) VALUES(?,?,?)", (cid, nome, db.agora()))
    return cid


def criar_cliente(nome: str, setor: str = "", cnpj: str | None = None, conta_id: str = CONTA_DEMO) -> str:
    """Cadastra um workspace novo (um cliente da conta) com os tipos de documento padrão."""
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
    ordem = (db.q("SELECT COALESCE(MAX(ordem), 0) m FROM workspaces WHERE conta_id=?", (conta_id,), um=True)["m"] or 0) + 1
    db.x("INSERT INTO workspaces(id, nome, setor, cor, sigla, ordem, cnpj, conta_id) VALUES(?,?,?,?,?,?,?,?)",
         (final, nome, setor or "Cliente", CORES[ordem % len(CORES)], sigla, ordem, cnpj, conta_id))
    for nome_t, (tit, pal) in TIPOS.items():
        db.x("INSERT INTO tipos(ws, nome, titulos, palavras, exigido) VALUES(?,?,?,?,?)",
             (final, nome_t, json.dumps(tit), json.dumps(pal), 0))
    return final


def semear():
    """Cria a conta de demonstração e seus clientes e acrescenta tipos novos aos clientes já criados."""
    if not db.q("SELECT 1 FROM contas WHERE id=?", (CONTA_DEMO,)):
        db.x("INSERT INTO contas(id, nome, criado_em) VALUES(?,?,?)", (CONTA_DEMO, NOME_CONTA_DEMO, db.agora()))
    # Workspaces e usuários de antes das contas ficam na conta de demonstração.
    db.x("UPDATE workspaces SET conta_id=? WHERE conta_id IS NULL", (CONTA_DEMO,))
    db.x("UPDATE usuarios SET conta_id=? WHERE conta_id IS NULL", (CONTA_DEMO,))
    for w in db.q("SELECT id FROM workspaces"):
        for nome_t, (tit, pal) in TIPOS.items():
            if not db.q("SELECT 1 FROM tipos WHERE ws=? AND nome=?", (w["id"], nome_t)):
                db.x("INSERT INTO tipos(ws, nome, titulos, palavras, exigido) VALUES(?,?,?,?,?)",
                     (w["id"], nome_t, json.dumps(tit), json.dumps(pal), 0))
    for i, (wid, nome, setor, cor, sigla) in enumerate(WORKSPACES):
        if db.q("SELECT 1 FROM workspaces WHERE id=?", (wid,)):
            continue
        db.x("INSERT INTO workspaces(id, nome, setor, cor, sigla, ordem, conta_id) VALUES(?,?,?,?,?,?,?)",
             (wid, nome, setor, cor, sigla, i, CONTA_DEMO))
        for nome_t, (tit, pal) in TIPOS.items():
            db.x("INSERT INTO tipos(ws, nome, titulos, palavras, exigido) VALUES(?,?,?,?,?)",
                 (wid, nome_t, json.dumps(tit), json.dumps(pal), 0))
