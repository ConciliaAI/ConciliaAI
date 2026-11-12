"""Testes da autenticação e administração de credenciais ERP."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import db
from app.integrations.auth import autenticar_integracao, exigir_escopo
from app.main import app


@pytest.fixture(scope="module")
def cliente():
    with TestClient(app) as client:
        yield client


def entrar(client, usuario):
    client.cookies.clear()
    response = client.post(
        "/api/login",
        json={"usuario": usuario, "senha": f"{usuario}123"},
    )
    assert response.status_code == 200, response.text


def criar_integracao(client, ws="horizonte", permissoes=None, expira_em=None):
    entrar(client, "admin")
    corpo = {"nome": "ERP de teste", "ws": ws}
    if permissoes is not None:
        corpo["permissoes"] = permissoes
    if expira_em is not None:
        corpo["expira_em"] = expira_em
    response = client.post("/api/integracoes", json=corpo)
    assert response.status_code == 200, response.text
    return response.json()


def request_com_token(token, query=b""):
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/erp/teste",
        "raw_path": b"/api/erp/teste",
        "query_string": query,
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "server": ("testserver", 80),
        "client": ("testclient", 123),
    })


def test_rotas_administrativas_exigem_login(cliente):
    cliente.cookies.clear()
    assert cliente.get("/api/integracoes").status_code == 401


def test_somente_admin_pode_criar_integracao(cliente):
    entrar(cliente, "operador")
    response = cliente.post(
        "/api/integracoes",
        json={"nome": "ERP operador", "ws": "horizonte"},
    )
    assert response.status_code == 403


def test_workspace_inexistente_e_rejeitado(cliente):
    entrar(cliente, "admin")
    response = cliente.post(
        "/api/integracoes",
        json={"nome": "ERP inválido", "ws": "workspace-que-nao-existe"},
    )
    assert response.status_code == 404


def test_criacao_nao_persiste_token_puro_nem_revela_hash(cliente):
    criado = criar_integracao(cliente)
    token = criado["token"]
    integracao = criado["integracao"]

    assert token.startswith("cai_")
    assert integracao["workspace"] == "horizonte"
    assert "token_hash" not in integracao
    assert "token" not in integracao

    guardado = db.q("SELECT token_hash FROM integracoes WHERE id=?", (integracao["id"],), um=True)
    assert guardado["token_hash"] != token
    assert len(guardado["token_hash"]) == 64

    lista = cliente.get("/api/integracoes")
    assert lista.status_code == 200
    registro = next(item for item in lista.json() if item["id"] == integracao["id"])
    assert "token_hash" not in registro and "token" not in registro


def test_token_valido_retorna_workspace_vinculado(cliente):
    criado = criar_integracao(cliente)
    integracao = autenticar_integracao(request_com_token(criado["token"]))
    assert integracao["ws"] == "horizonte"
    assert "results:read" in integracao["permissoes"]
    exigir_escopo(integracao, "results:read")


def test_token_incorreto_e_rejeitado(cliente):
    with pytest.raises(HTTPException) as erro:
        autenticar_integracao(request_com_token("cai_token_incorreto"))
    assert erro.value.status_code == 401


def test_token_expirado_e_rejeitado(cliente):
    criado = criar_integracao(cliente)
    db.x(
        "UPDATE integracoes SET expira_em=? WHERE id=?",
        ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
         criado["integracao"]["id"]),
    )
    with pytest.raises(HTTPException) as erro:
        autenticar_integracao(request_com_token(criado["token"]))
    assert erro.value.status_code == 401


def test_token_revogado_e_rejeitado(cliente):
    criado = criar_integracao(cliente)
    entrar(cliente, "admin")
    response = cliente.post(f"/api/integracoes/{criado['integracao']['id']}/revogar")
    assert response.status_code == 200
    with pytest.raises(HTTPException) as erro:
        autenticar_integracao(request_com_token(criado["token"]))
    assert erro.value.status_code == 401


def test_escopo_insuficiente_retorna_403(cliente):
    criado = criar_integracao(cliente, permissoes=["documents:write"])
    integracao = autenticar_integracao(request_com_token(criado["token"]))
    with pytest.raises(HTTPException) as erro:
        exigir_escopo(integracao, "results:read")
    assert erro.value.status_code == 403


def test_rotacao_invalida_token_anterior(cliente):
    criado = criar_integracao(cliente)
    antigo = criado["token"]
    entrar(cliente, "admin")
    response = cliente.post(f"/api/integracoes/{criado['integracao']['id']}/rotacionar", json={})
    assert response.status_code == 200
    novo = response.json()["token"]
    assert novo != antigo

    with pytest.raises(HTTPException) as erro:
        autenticar_integracao(request_com_token(antigo))
    assert erro.value.status_code == 401
    assert autenticar_integracao(request_com_token(novo))["ws"] == "horizonte"


def test_token_nao_consegue_escolher_outro_workspace(cliente):
    criado = criar_integracao(cliente, ws="horizonte")
    # Um parâmetro de workspace na requisição não altera o workspace da credencial.
    integracao = autenticar_integracao(
        request_com_token(criado["token"], query=b"workspace=marazul")
    )
    assert integracao["ws"] == "horizonte"


def test_eventos_administrativos_sao_auditados(cliente):
    criado = criar_integracao(cliente)
    entrar(cliente, "admin")
    response = cliente.get(f"/api/integracoes/{criado['integracao']['id']}")
    assert response.status_code == 200
    acoes = [evento["acao"] for evento in response.json()["eventos"]]
    assert "criacao" in acoes
