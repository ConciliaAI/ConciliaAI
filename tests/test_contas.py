"""Contas (empresas) com vários workspaces: cada empresa só enxerga os workspaces, documentos e envios dela."""
import secrets

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app


def _pdf() -> bytes:
    d = fitz.open()
    d.new_page().insert_text((60, 80), "CONTRATO DE PRESTACAO DE SERVICOS", fontsize=16)
    return d.tobytes()


def _nova_conta(cliente: TestClient, empresa: str) -> dict:
    usuario = f"u{secrets.token_hex(4)}"
    r = cliente.post("/api/contas", json={"empresa": empresa, "nome": "Pessoa Teste", "usuario": usuario,
                                          "senha": "senha-forte-1"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def demo():
    with TestClient(app) as c:
        assert c.post("/api/login", json={"usuario": "admin", "senha": "admin123"}).status_code == 200
        yield c


def test_criar_conta_entra_logado_e_sem_workspaces():
    with TestClient(app) as c:
        conta = _nova_conta(c, "Escritório Contábil Alfa")
        assert conta["perfil"] == "admin"
        estado = c.get("/api/estado").json()
        assert estado["conta"]["nome"] == "Escritório Contábil Alfa"
        assert estado["conta"]["limite_documentos"] == config.LIMITE_DOCUMENTOS
        assert estado["clientes"] == []  # a empresa cria os workspaces dos seus clientes depois


def test_conta_cria_varios_workspaces_e_so_ve_os_seus(demo):
    with TestClient(app) as c:
        _nova_conta(c, "BPO Beta")
        for nome in ("Padaria Pão Quente", "Construtora Norte"):
            assert c.post("/api/clientes", json={"nome": nome}).status_code == 200
        meus = {w["nome"] for w in c.get("/api/estado").json()["clientes"]}
        assert meus == {"Padaria Pão Quente", "Construtora Norte"}

    # A conta de demonstração não vê os workspaces da BPO Beta, e vice-versa.
    do_demo = {w["nome"] for w in demo.get("/api/estado").json()["clientes"]}
    assert "Padaria Pão Quente" not in do_demo and "Atlântica Facilities" in do_demo


def test_workspace_de_outra_conta_responde_404(demo):
    with TestClient(app) as c:
        _nova_conta(c, "BPO Gama")
        ws = c.post("/api/clientes", json={"nome": "Cliente da Gama"}).json()["id"]
        envio = c.post(f"/api/ws/{ws}/envios", files=[("arquivos", ("lote.pdf", _pdf(), "application/pdf"))]).json()

        # Quem é da conta de demonstração não alcança nada da Gama, nem pelo workspace nem pelo id do envio.
        for caminho in (f"/api/ws/{ws}/documentos", f"/api/ws/{ws}/resumo", f"/api/ws/{ws}/relatorio.csv",
                        f"/api/envios/{envio['id']}"):
            assert demo.get(caminho).status_code == 404, caminho
        assert demo.post(f"/api/envios/{envio['id']}/cancelar").status_code == 404

        # E a Gama não alcança os workspaces da demonstração.
        assert c.get("/api/ws/atlantica/documentos").status_code == 404
        assert c.get(f"/api/envios/{envio['id']}").status_code == 200


def test_documentos_e_paginas_de_outra_conta_respondem_404(demo):
    # Pega um documento e uma página que existam na demonstração (cria um envio se o banco estiver vazio).
    if not db.q("SELECT 1 FROM docs WHERE ws='atlantica' LIMIT 1"):
        demo.post("/api/ws/atlantica/envios", files=[("arquivos", ("lote.pdf", _pdf(), "application/pdf"))])
    pagina = db.q("SELECT p.id FROM paginas p JOIN envios e ON e.id=p.envio_id WHERE e.ws='atlantica' LIMIT 1", um=True)
    with TestClient(app) as c:
        _nova_conta(c, "BPO Delta")
        if pagina:
            assert c.get(f"/api/paginas/{pagina['id']}/imagem").status_code == 404
        doc = db.q("SELECT id FROM docs WHERE ws='atlantica' LIMIT 1", um=True)
        if doc:
            assert c.get(f"/api/docs/{doc['id']}").status_code == 404
            assert c.delete(f"/api/docs/{doc['id']}").status_code == 404


def test_cnpj_do_workspace_e_unico_so_dentro_da_conta():
    cnpj = "11.222.333/0001-81"
    with TestClient(app) as a, TestClient(app) as b:
        _nova_conta(a, "BPO Épsilon")
        _nova_conta(b, "BPO Zeta")
        assert a.post("/api/clientes", json={"nome": "Mercado X", "cnpj": cnpj}).status_code == 200
        assert a.post("/api/clientes", json={"nome": "Mercado X de novo", "cnpj": cnpj}).status_code == 400
        # Duas empresas podem atender o mesmo cliente.
        assert b.post("/api/clientes", json={"nome": "Mercado X", "cnpj": cnpj}).status_code == 200


def test_admin_cadastra_usuario_na_propria_conta():
    with TestClient(app) as c:
        _nova_conta(c, "BPO Eta")
        login = f"op{secrets.token_hex(3)}"
        r = c.post("/api/usuarios", json={"nome": "Operadora", "usuario": login, "senha": "outra-senha-1",
                                          "perfil": "operador"})
        assert r.status_code == 200, r.text
        assert login in {u["usuario"] for u in c.get("/api/usuarios").json()}
        with TestClient(app) as nova:
            assert nova.post("/api/login", json={"usuario": login, "senha": "outra-senha-1"}).status_code == 200
            assert nova.get("/api/estado").json()["conta"]["nome"] == "BPO Eta"
            assert nova.post("/api/clientes", json={"nome": "Sem permissão"}).status_code == 403


def test_cadastro_recusa_usuario_repetido_e_senha_curta():
    with TestClient(app) as c:
        conta = _nova_conta(c, "BPO Teta")
        repetido = c.post("/api/contas", json={"empresa": "Outra", "nome": "X", "usuario": conta["usuario"],
                                               "senha": "senha-forte-2"})
        assert repetido.status_code == 400
        curta = c.post("/api/contas", json={"empresa": "Outra", "nome": "X", "usuario": "nova.pessoa", "senha": "123"})
        assert curta.status_code == 400
    # A conta "Outra" não pode ter ficado pela metade.
    assert not db.q("SELECT 1 FROM contas WHERE nome='Outra'")


def test_limite_de_documentos_por_conta(monkeypatch):
    with TestClient(app) as c:
        _nova_conta(c, "BPO Iota")
        ws = c.post("/api/clientes", json={"nome": "Cliente cheio"}).json()["id"]
        monkeypatch.setattr(config, "LIMITE_DOCUMENTOS", 0)
        r = c.post(f"/api/ws/{ws}/envios", files=[("arquivos", ("lote.pdf", _pdf(), "application/pdf"))])
        assert r.status_code == 403 and "limite" in r.json()["detail"]
