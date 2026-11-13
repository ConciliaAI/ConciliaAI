"""Testes da autenticação e administração de credenciais ERP."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import db
from app.integrations.auth import autenticar_integracao, exigir_escopo
from app.integrations.erp import exigir_integracao
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



def test_middleware_libera_apenas_prefixo_erp_v1(cliente):
    cliente.cookies.clear()

    # O prefixo ERP passa pelo middleware humano; como a rota ainda não existe,
    # o resultado esperado é 404, e não 401 por falta de cookie.
    assert cliente.get("/api/erp/v1/rota-ainda-nao-implementada").status_code == 404

    # Prefixos parecidos e demais rotas continuam exigindo sessão humana.
    assert cliente.get("/api/erp/v10/rota-inexistente").status_code == 401
    assert cliente.get("/api/integracoes").status_code == 401


def test_dependencia_erp_exige_bearer_e_escopo(cliente):
    criado = criar_integracao(cliente, permissoes=["results:read"])
    dependencia = exigir_integracao("results:read")

    integracao = dependencia(request_com_token(criado["token"]))
    assert integracao["id"] == criado["integracao"]["id"]
    assert integracao["ws"] == "horizonte"

    with pytest.raises(HTTPException) as erro:
        exigir_integracao("documents:write")(request_com_token(criado["token"]))
    assert erro.value.status_code == 403

    request_sem_token = Request({
        "type": "http", "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": "/api/erp/v1/documentos",
        "raw_path": b"/api/erp/v1/documentos", "query_string": b"",
        "headers": [], "server": ("testserver", 80),
        "client": ("testclient", 123),
    })
    with pytest.raises(HTTPException) as erro:
        dependencia(request_sem_token)
    assert erro.value.status_code == 401



def test_auditoria_identifica_admin_em_criacao_rotacao_e_revogacao(cliente):
    criado = criar_integracao(cliente)
    integracao_id = criado["integracao"]["id"]

    entrar(cliente, "admin")
    rotacao = cliente.post(f"/api/integracoes/{integracao_id}/rotacionar", json={})
    assert rotacao.status_code == 200
    revogacao = cliente.post(f"/api/integracoes/{integracao_id}/revogar")
    assert revogacao.status_code == 200

    eventos = cliente.get(f"/api/integracoes/{integracao_id}").json()["eventos"]
    por_acao = {evento["acao"]: evento for evento in eventos}
    for acao in ("criacao", "rotacao", "revogacao"):
        assert por_acao[acao]["ator_usuario"] == "admin"
        assert por_acao[acao]["ator_nome"] == "Administrador"
        assert por_acao[acao]["ator_perfil"] == "admin"


def test_falha_na_auditoria_reverte_criacao(cliente, monkeypatch):
    from app.integrations import admin
    entrar(cliente, "admin")
    antes = db.q("SELECT COUNT(*) AS total FROM integracoes", um=True)["total"]
    def falhar(*args, **kwargs):
        raise RuntimeError("falha simulada na auditoria")
    monkeypatch.setattr(admin, "_evento", falhar)
    with pytest.raises(RuntimeError):
        cliente.post("/api/integracoes", json={"nome": "ERP rollback", "ws": "horizonte"})
    depois = db.q("SELECT COUNT(*) AS total FROM integracoes", um=True)["total"]
    assert depois == antes


def test_falha_na_auditoria_reverte_rotacao_e_revogacao(cliente, monkeypatch):
    from app.integrations import admin
    criado = criar_integracao(cliente)
    integracao_id = criado["integracao"]["id"]
    hash_antes = db.q("SELECT token_hash FROM integracoes WHERE id=?", (integracao_id,), um=True)["token_hash"]
    entrar(cliente, "admin")
    def falhar(*args, **kwargs):
        raise RuntimeError("falha simulada na auditoria")
    monkeypatch.setattr(admin, "_evento", falhar)
    with pytest.raises(RuntimeError):
        cliente.post(f"/api/integracoes/{integracao_id}/rotacionar", json={})
    atual = db.q("SELECT token_hash, ativa FROM integracoes WHERE id=?", (integracao_id,), um=True)
    assert atual["token_hash"] == hash_antes and atual["ativa"] == 1
    with pytest.raises(RuntimeError):
        cliente.post(f"/api/integracoes/{integracao_id}/revogar")
    atual = db.q("SELECT token_hash, ativa FROM integracoes WHERE id=?", (integracao_id,), um=True)
    assert atual["token_hash"] == hash_antes and atual["ativa"] == 1


def test_historico_de_auditoria_nao_pode_ser_alterado_ou_excluido(cliente):
    criado = criar_integracao(cliente)
    integracao_id = criado["integracao"]["id"]
    evento = db.q("SELECT id FROM integracao_eventos WHERE integracao_id=? LIMIT 1", (integracao_id,), um=True)
    with pytest.raises(Exception):
        db.x("UPDATE integracao_eventos SET acao=? WHERE id=?", ("alterado", evento["id"]))
    with pytest.raises(Exception):
        db.x("DELETE FROM integracao_eventos WHERE id=?", (evento["id"],))
    preservado = db.q("SELECT acao FROM integracao_eventos WHERE id=?", (evento["id"],), um=True)
    assert preservado["acao"] == "criacao"
