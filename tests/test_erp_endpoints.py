"""Testes dos endpoints de transferência ERP."""
from fastapi.testclient import TestClient

from app.main import app


import pytest


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _login(client, usuario="admin"):
    client.cookies.clear()
    response = client.post(
        "/api/login",
        json={"usuario": usuario, "senha": f"{usuario}123"},
    )
    assert response.status_code == 200, response.text


def _integracao(client, workspace="horizonte", permissoes=None):
    _login(client)
    corpo = {"nome": "ERP endpoints", "ws": workspace}
    if permissoes is not None:
        corpo["permissoes"] = permissoes
    response = client.post("/api/integracoes", json=corpo)
    assert response.status_code == 200, response.text
    return response.json()["token"]


def test_endpoints_erp_exigem_credencial_e_escopo(client):
    assert client.get("/api/erp/v1/documents").status_code == 401
    token = _integracao(client, permissoes=["documents:write"])
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/erp/v1/documents", headers=headers).status_code == 403
    assert client.post(
            "/api/erp/v1/documents",
        headers=headers,
        files={"arquivos": ("teste.pdf", b"conteudo", "application/pdf")},
        ).status_code == 202


def test_recebimento_e_consulta_de_envio(client):
        token = _integracao(client)
        headers = {"Authorization": f"Bearer {token}"}
    recebido = client.post(
            "/api/erp/v1/documents",
            headers=headers,
            files={"arquivos": ("teste.pdf", b"nao e um pdf valido", "application/pdf")},
        )
        assert recebido.status_code == 202, recebido.text
    envio_id = recebido.json()["envio_id"]

    lista = client.get("/api/erp/v1/documents", headers=headers)
        assert lista.status_code == 200
    assert any(item["id"] == envio_id for item in lista.json()["items"])

    detalhe = client.get(f"/api/erp/v1/documents/{envio_id}", headers=headers)
        assert detalhe.status_code == 200
        assert detalhe.json()["id"] == envio_id

    resultados = client.get(
        f"/api/erp/v1/documents/{envio_id}/results",
            headers=headers,
        )
        assert resultados.status_code == 200
        assert resultados.json()["envio_id"] == envio_id


def test_integracao_nao_acessa_envio_de_outro_workspace(client):
    token_horizonte = _integracao(client, workspace="horizonte")
    headers_horizonte = {"Authorization": f"Bearer {token_horizonte}"}
        recebido = client.post(
            "/api/erp/v1/documents",
            headers=headers_horizonte,
            files={"arquivos": ("teste.pdf", b"conteudo", "application/pdf")},
        )
        assert recebido.status_code == 202, recebido.text
        envio_id = recebido.json()["envio_id"]

    token_marazul = _integracao(client, workspace="marazul")
    headers_marazul = {"Authorization": f"Bearer {token_marazul}"}
        assert client.get(
            f"/api/erp/v1/documents/{envio_id}",
            headers=headers_marazul,
        ).status_code == 404


def test_recebimento_rejeita_extensao_nao_permitida(client):
        token = _integracao(client)
    response = client.post(
            "/api/erp/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
            files={"arquivos": ("script.exe", b"conteudo", "application/octet-stream")},
        )
        assert response.status_code == 415
