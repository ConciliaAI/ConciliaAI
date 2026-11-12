"""Fluxo completo pela API: login, perfis, envio de PDF + XML, separação, conciliação, revisão e proteções."""
import time

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

from app import fiscal
from app.main import app

CNPJ = "87.000.001/1001-78"
TOMADOR = "87.000.999/1999-99"


def lote_pdf() -> bytes:
    d = fitz.open()
    paginas = [
        ("CONTRATO DE PRESTACAO DE SERVICOS", ["Instrumento: CTR-900", "Contratada: Limpeza Brilho ME",
                                               f"CNPJ contratada: {CNPJ}", f"CNPJ contratante: {TOMADOR}",
                                               "Objeto: Limpeza e conservacao predial", "Valor mensal: R$ 4.000,00",
                                               "Vigencia: 01/01/2026 a 31/12/2026", "Pagina 1 de 2"]),
        (None, ["Clausula 5: reajuste depende de termo aditivo", "Representante legal: CPF 321.654.987-00",
                "Assinaturas das partes", "Pagina 2 de 2"]),
        ("NOTA FISCAL DE SERVICOS ELETRONICA - NFS-e", ["Numero: 501", "Prestador: Limpeza Brilho ME",
                                                       f"CNPJ prestador: {CNPJ}", f"CNPJ tomador: {TOMADOR}",
                                                       "Data emissao: 05/09/2026", "Competencia: 09/2026",
                                                       "Descricao: Limpeza e conservacao predial",
                                                       "Valor do servico: R$ 4.000,00"]),
    ]
    for titulo, linhas in paginas:
        pg = d.new_page()
        y = 70
        if titulo:
            pg.insert_text((60, y), titulo, fontsize=16)
            y += 30
        for ln in linhas:
            pg.insert_text((60, y), ln, fontsize=11)
            y += 20
    return d.tobytes()


def nota_xml(numero, cnpj, valor, data="2026-10-05", descricao="Limpeza e conservacao predial"):
    inv = {"numero": numero, "data_emissao": data, "competencia": data[:7], "prestador_cnpj": cnpj,
           "tomador_cnpj": TOMADOR, "descricao_servico": descricao, "valor_servico": valor}
    return fiscal.nfse_nacional_xml(inv, "Limpeza Brilho ME")


@pytest.fixture(scope="module")
def cliente():
    with TestClient(app) as c:
        yield c


def entrar(c, usuario):
    c.cookies.clear()
    r = c.post("/api/login", json={"usuario": usuario, "senha": f"{usuario}123"})
    assert r.status_code == 200, r.text
    return r.json()


def esperar(c, eid, limite=120):
    for _ in range(limite * 4):
        e = c.get(f"/api/envios/{eid}").json()
        if e["envio"]["status"] in ("concluido", "recusado"):
            return e
        time.sleep(0.25)
    raise AssertionError("envio não terminou")


def test_sem_login_bloqueia(cliente):
    cliente.cookies.clear()
    assert cliente.get("/api/ws/horizonte/resumo").status_code == 401
    assert cliente.post("/api/login", json={"usuario": "admin", "senha": "errada"}).status_code == 401


def test_fluxo_completo(cliente):
    entrar(cliente, "operador")
    lote = lote_pdf()
    arquivos = [("arquivos", ("lote.pdf", lote, "application/pdf")),
                ("arquivos", ("nfse-502.xml", nota_xml("502", CNPJ, "5200.00"), "application/xml")),
                ("arquivos", ("nfse-777.xml", nota_xml("777", "87.000.700/1700-34", "900.00"), "application/xml"))]
    r = cliente.post("/api/ws/horizonte/envios", files=arquivos)
    assert r.status_code == 200, r.text
    assert r.json()["notas_xml"] == 2
    e = esperar(cliente, r.json()["id"])
    docs = e["docs"]
    assert [(d["tipo"], d["pag_ini"], d["pag_fim"]) for d in docs] == [
        ("Contrato de prestação de serviços", 1, 2), ("Nota fiscal de serviço", 3, 3)]
    contrato = next(d for d in docs if d["tipo"].startswith("Contrato"))
    assert contrato["dados"]["campos"]["valor_mensal"] == 4000.0

    # Conciliação: a nota do PDF bate; a do XML cobra a mais; a terceira não tem contrato.
    notas = {n["numero"]: n for n in cliente.get("/api/ws/horizonte/notas").json()}
    assert notas["501"]["status"] == "conciliada" and notas["501"]["origem"] == "pdf"
    assert notas["502"]["status"] == "divergente" and notas["502"]["contrato_numero"] == "CTR-900"
    assert notas["777"]["status"] == "divergente"
    divs = cliente.get("/api/ws/horizonte/divergencias").json()["divergencias"]
    assert sorted(d["regra"] for d in divs) == ["SEM_CONTRATO", "VALOR_DIVERGENTE"]

    # Dado pessoal escondido no texto do contrato.
    texto = cliente.get(f"/api/docs/{contrato['id']}").json()["texto"]
    assert "321.654.987-00" not in texto
    assert cliente.get("/api/ws/horizonte/busca", params={"q": "conservacao"}).json()

    # Arquivo repetido não é processado de novo.
    r2 = cliente.post("/api/ws/horizonte/envios", files=[("arquivos", ("copia.pdf", lote, "application/pdf"))])
    assert r2.json()["status"] == "recusado"

    # Operador não decide; revisor decide; rejeitar exige motivo.
    valor = next(d for d in divs if d["regra"] == "VALOR_DIVERGENTE")
    sem = next(d for d in divs if d["regra"] == "SEM_CONTRATO")
    assert cliente.post(f"/api/divergencias/{valor['id']}/decisao", json={"acao": "aprovar"}).status_code == 403
    entrar(cliente, "revisor")
    assert cliente.post(f"/api/divergencias/{valor['id']}/decisao", json={"acao": "rejeitar"}).status_code == 400
    r = cliente.post(f"/api/divergencias/{valor['id']}/decisao", json={"acao": "rejeitar", "comentario": "Cobrar devolução de R$ 1.200"})
    assert r.status_code == 200, r.text
    assert cliente.post(f"/api/divergencias/{sem['id']}/decisao", json={"acao": "aprovar", "comentario": "Contrato em assinatura"}).status_code == 200
    notas = {n["numero"]: n for n in cliente.get("/api/ws/horizonte/notas").json()}
    assert notas["502"]["status"] == "rejeitada" and notas["777"]["status"] == "aprovada"
    csv = cliente.get("/api/ws/horizonte/relatorio.csv", params={"tipo": "divergencias"}).text
    assert "Valor acima do contratado" in csv and "Cobrar devolução" in csv
    assert "rejeitou" in cliente.get("/api/ws/horizonte/relatorio.csv", params={"tipo": "trilha"}).text

    # A mesma nota enviada de novo não vira duplicada.
    entrar(cliente, "operador")
    r3 = cliente.post("/api/ws/horizonte/envios", files=[("arquivos", ("outra-copia.xml", nota_xml("502", CNPJ, "5200.00").replace(b"Garanhuns", b"Garanhuns "), "application/xml"))])
    assert r3.json()["status"] == "concluido"
    assert len([n for n in cliente.get("/api/ws/horizonte/notas").json() if n["numero"] == "502"]) == 1

    # Só admin muda configurações.
    assert cliente.post("/api/ws/horizonte/config", json={"limiar": 80}).status_code == 403
    entrar(cliente, "admin")
    assert cliente.post("/api/ws/horizonte/config", json={"limiar": 80}).status_code == 200


def test_pdf_com_senha_e_recusado(cliente):
    entrar(cliente, "operador")
    d = fitz.open()
    d.new_page().insert_text((60, 70), "Documento secreto")
    protegido = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="1234")
    r = cliente.post("/api/ws/marazul/envios", files=[("arquivos", ("secreto.pdf", protegido, "application/pdf"))])
    assert r.json()["status"] == "recusado"
    assert "senha" in r.json()["erro"]


def test_cadastro_de_cliente_e_fornecedor(cliente):
    entrar(cliente, "revisor")
    assert cliente.post("/api/clientes", json={"nome": "Construtora Boa Vista"}).status_code == 403
    entrar(cliente, "admin")
    assert cliente.post("/api/clientes", json={"nome": "X", "cnpj": "11.111.111/1111-11"}).status_code == 400
    novo = cliente.post("/api/clientes", json={"nome": "Construtora Boa Vista", "setor": "Construção civil"}).json()
    assert novo["id"] == "construtoraboavista"
    ws = novo["id"]
    assert cliente.post(f"/api/ws/{ws}/fornecedores", json={"cnpj": "12.345.678/0001-00", "nome": "Y"}).status_code == 400
    r = cliente.post(f"/api/ws/{ws}/fornecedores", json={"cnpj": CNPJ, "nome": "Limpeza Brilho ME",
                                                        "email": "contato@brilho.exemplo", "responsavel": "Carlos (contratos)"})
    assert r.status_code == 200, r.text
    f = cliente.get(f"/api/ws/{ws}/fornecedores").json()
    assert len(f) == 1 and f[0]["responsavel"] == "Carlos (contratos)" and f[0]["cadastro"] == "manual"
    # Outro cliente não vê esse fornecedor.
    assert all(x["cnpj"] != fiscal.so_digitos(CNPJ) or x["cadastro"] != "manual" for x in cliente.get("/api/ws/marazul/fornecedores").json())


def test_aviso_ao_fornecedor(cliente):
    entrar(cliente, "revisor")
    divs = cliente.get("/api/ws/horizonte/divergencias", params={"status": "todas"}).json()["divergencias"]
    d = next(x for x in divs if x["regra"] == "VALOR_DIVERGENTE")
    r = cliente.post(f"/api/divergencias/{d['id']}/aviso")
    assert r.status_code == 200, r.text
    a = r.json()
    assert "502" in a["assunto"] and "R$ 5.200,00" in a["corpo"] and "Cobrar devolução" in a["corpo"]
    assert "Avisos" not in a["corpo"] and a["para"] is None  # fornecedor sem e-mail cadastrado
    csv = cliente.get("/api/ws/horizonte/relatorio.csv", params={"tipo": "avisos"}).text
    assert a["assunto"] in csv
    d2 = next(x for x in cliente.get("/api/ws/horizonte/divergencias", params={"status": "todas"}).json()["divergencias"] if x["id"] == d["id"])
    assert d2["avisado_em"]


def test_excluir_documento(cliente):
    entrar(cliente, "operador")
    docs = cliente.get("/api/ws/horizonte/documentos").json()
    nota = next(d for d in docs if d["tipo"] == "Nota fiscal de serviço")
    assert cliente.delete(f"/api/docs/{nota['id']}").status_code == 403  # operador não exclui
    entrar(cliente, "revisor")
    r = cliente.delete(f"/api/docs/{nota['id']}")
    assert r.status_code == 200, r.text
    assert all(d["id"] != nota["id"] for d in cliente.get("/api/ws/horizonte/documentos").json())
    assert cliente.get(f"/api/docs/{nota['id']}").status_code == 404
    # A nota lida só desse PDF sai da conferência; a trilha registra quem excluiu.
    assert "501" not in [n["numero"] for n in cliente.get("/api/ws/horizonte/notas").json()]
    assert "excluiu o documento" in cliente.get("/api/ws/horizonte/relatorio.csv", params={"tipo": "trilha"}).text
    pags = cliente.get(f"/api/envios/{nota['envio_id']}").json()["paginas"]
    assert all(p["status"] == "excluida" for p in pags if nota["pag_ini"] <= p["n"] <= nota["pag_fim"])
