"""Testes dos endpoints de transferência ERP."""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _login(client):
    client.cookies.clear()
    response = client.post(
        "/api/login",
        json={"usuario": "admin", "senha": "admin123"},
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


def test_endpoints_erp_exigem_credencial_e_escopo(client, monkeypatch):
    assert client.get("/api/erp/v1/documents").status_code == 401
    token = _integracao(client, permissoes=["documents:write"])
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/erp/v1/documents", headers=headers).status_code == 403
    envio_id = db.x(
        """INSERT INTO envios(ws, nome, origem, criado_em, status)
           VALUES(?,?,?,?,?)""",
        ("horizonte", "teste.pdf", "ERP: ERP endpoints", db.agora(), "fila"),
    )
    monkeypatch.setattr(
        "app.integrations.erp.pipeline.criar_envio",
        lambda *args, **kwargs: {
            "envio_id": envio_id,
            "status": "fila",
            "documentos_aceitos": 1,
            "documentos_xml": 0,
            "arquivos_com_paginas": 1,
            "paginas_enfileiradas": 1,
            "arquivos_duplicados": 0,
            "somente_duplicados": False,
        },
    )
    recebido = client.post(
        "/api/erp/v1/documents",
        headers=headers,
        files={"arquivos": ("teste.pdf", b"conteudo", "application/pdf")},
    )
    assert recebido.status_code == 202, recebido.text


def test_recebimento_e_consulta_de_envio(client):
    token = _integracao(client)
    headers = {"Authorization": f"Bearer {token}"}
    recebido = client.post(
        "/api/erp/v1/documents",
        headers=headers,
        files={"arquivos": ("teste.pdf", b"nao e um pdf valido", "application/pdf")},
    )
    assert recebido.status_code == 422, recebido.text
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
    assert recebido.status_code == 422, recebido.text
    envio_id = recebido.json()["envio_id"]

    token_marazul = _integracao(client, workspace="marazul")
    headers_marazul = {"Authorization": f"Bearer {token_marazul}"}
    resposta = client.get(
        f"/api/erp/v1/documents/{envio_id}",
        headers=headers_marazul,
    )
    assert resposta.status_code == 404


def test_recebimento_rejeita_extensao_nao_permitida(client):
    token = _integracao(client)
    response = client.post(
        "/api/erp/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"arquivos": ("script.exe", b"conteudo", "application/octet-stream")},
    )
    assert response.status_code == 415


@pytest.mark.parametrize(
    ("status", "codigo_esperado"),
    [
        ("falhou", "PROCESSING_FAILED"),
        ("recusado", "DOCUMENTS_REJECTED"),
    ],
)
def test_listagem_e_detalhe_nao_expoem_erro_interno(client, status, codigo_esperado):
    token = _integracao(client)
    headers = {"Authorization": f"Bearer {token}"}
    recebido = client.post(
        "/api/erp/v1/documents",
        headers=headers,
        files={"arquivos": ("teste.pdf", f"conteudo de teste {status}".encode(), "application/pdf")},
    )
    assert recebido.status_code == 422, recebido.text
    envio_id = recebido.json()["envio_id"]

    detalhe_interno = (
        "FileNotFoundError: /srv/conciliaai/private/uploads/cliente/documento.pdf"
    )
    db.x(
        "UPDATE envios SET status=?, erro=? WHERE id=?",
        (status, detalhe_interno, envio_id),
    )

    lista = client.get("/api/erp/v1/documents", headers=headers)
    assert lista.status_code == 200
    item = next(item for item in lista.json()["items"] if item["id"] == envio_id)

    detalhe = client.get(
        f"/api/erp/v1/documents/{envio_id}",
        headers=headers,
    )
    assert detalhe.status_code == 200
    payloads = [item, detalhe.json()]

    for payload in payloads:
        assert "erro" not in payload
        assert payload["erro_codigo"] == codigo_esperado
        assert payload["erro_mensagem"]
        assert detalhe_interno not in str(payload)
        assert "/srv/conciliaai/private/" not in str(payload)


@pytest.mark.parametrize(
    ("resultado_pipeline", "status_http", "codigo_resultado"),
    [
        (
            {
                "status": "fila",
                "documentos_aceitos": 1,
                "documentos_xml": 0,
                "arquivos_com_paginas": 1,
                "paginas_enfileiradas": 2,
                "arquivos_duplicados": 0,
                "somente_duplicados": False,
            },
            202,
            "ACCEPTED_FOR_PROCESSING",
        ),
        (
            {
                "status": "concluido",
                "documentos_aceitos": 1,
                "documentos_xml": 1,
                "arquivos_com_paginas": 0,
                "paginas_enfileiradas": 0,
                "arquivos_duplicados": 0,
                "somente_duplicados": False,
            },
            200,
            "PROCESSED",
        ),
        (
            {
                "status": "recusado",
                "documentos_aceitos": 0,
                "documentos_xml": 0,
                "arquivos_com_paginas": 0,
                "paginas_enfileiradas": 0,
                "arquivos_duplicados": 1,
                "somente_duplicados": True,
            },
            409,
            "DUPLICATE_DOCUMENT",
        ),
        (
            {
                "status": "recusado",
                "documentos_aceitos": 0,
                "documentos_xml": 0,
                "arquivos_com_paginas": 0,
                "paginas_enfileiradas": 0,
                "arquivos_duplicados": 0,
                "somente_duplicados": False,
            },
            422,
            "NO_ACCEPTED_DOCUMENTS",
        ),
    ],
)
def test_recebimento_retorna_status_real_do_pipeline(
    client, monkeypatch, resultado_pipeline, status_http, codigo_resultado
):
    token = _integracao(client)
    headers = {"Authorization": f"Bearer {token}"}
    envio_id = db.x(
        """INSERT INTO envios(ws, nome, origem, criado_em, status)
           VALUES(?,?,?,?,?)""",
        ("horizonte", "teste.pdf", "ERP: ERP endpoints", db.agora(),
         resultado_pipeline["status"]),
    )

    resultado = {"envio_id": envio_id, **resultado_pipeline}

    def pipeline_simulado(*args, **kwargs):
        assert kwargs.get("retornar_detalhes") is True
        return resultado

    monkeypatch.setattr("app.integrations.erp.pipeline.criar_envio", pipeline_simulado)

    response = client.post(
        "/api/erp/v1/documents",
        headers=headers,
        files={"arquivos": ("teste.pdf", b"conteudo", "application/pdf")},
    )

    assert response.status_code == status_http, response.text
    assert response.json()["resultado"] == codigo_resultado
    assert response.json()["envio_id"] == envio_id
