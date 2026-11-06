"""Fluxo completo pela API: login, perfis, envio, separação, busca, revisão e proteções."""
import time

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app


def lote_pdf() -> bytes:
    d = fitz.open()
    paginas = [
        ("FICHA DE REGISTRO DE EMPREGADO", ["Nome do colaborador: Marcos Silva", "CPF: 321.654.987-00", "Cargo: Porteiro", "Página 1 de 2"]),
        (None, ["Dependentes: não possui", "Assinatura do empregado", "Página 2 de 2"]),
        ("ATESTADO DE SAÚDE OCUPACIONAL - ASO", ["Nome do colaborador: Marcos Silva", "Exame admissional", "Resultado: APTO", "Observação: CID Z00.0"]),
        ("RECIBO DE PAGAMENTO DE SALÁRIO", ["Nome do colaborador: Ana Rocha", "Competência: 10/2026", "Salário base R$ 1.850,00", "Líquido a receber"]),
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
    r = cliente.post("/api/ws/horizonte/envios", files=[("arquivos", ("lote.pdf", lote, "application/pdf"))])
    assert r.status_code == 200, r.text
    e = esperar(cliente, r.json()["id"])
    docs = e["docs"]
    assert [(d["tipo"], d["pag_ini"], d["pag_fim"]) for d in docs] == [
        ("Ficha de registro", 1, 2), ("ASO", 3, 3), ("Holerite", 4, 4)]
    assert all("321.654.987-00" not in (d["cpf"] or "") for d in docs)

    busca = cliente.get("/api/ws/horizonte/busca", params={"q": "porteiro"}).json()
    assert busca and busca[0]["tipo"] == "Ficha de registro"

    aso = next(d for d in docs if d["tipo"] == "ASO")
    texto = cliente.get(f"/api/docs/{aso['id']}").json()["texto"]
    assert "Z00.0" not in texto

    # Arquivo repetido não é processado de novo.
    r2 = cliente.post("/api/ws/horizonte/envios", files=[("arquivos", ("copia.pdf", lote, "application/pdf"))])
    assert r2.json()["status"] == "recusado"

    # Operador não decide pendências; revisor decide.
    assert cliente.post(f"/api/docs/{aso['id']}/decisao", json={"acao": "confirmar"}).status_code == 403
    entrar(cliente, "revisor")
    assert cliente.post(f"/api/docs/{aso['id']}/decisao", json={"acao": "confirmar"}).status_code == 200
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
