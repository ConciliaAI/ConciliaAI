"""Testes dos endpoints de transferência ERP."""
import hashlib

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.integrations.security import hash_token


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


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": f"test-{token[:24]}",
    }


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
    headers = _headers(token)

    assert client.get("/api/erp/v1/documents", headers=headers).status_code == 403
    negada = db.q(
        """SELECT acao, status FROM integracao_eventos
           WHERE acao='escopo_negado' AND integracao_id=(
             SELECT id FROM integracoes WHERE token_hash=?
           ) ORDER BY id DESC LIMIT 1""",
        (hash_token(token),),
        um=True,
    )
    assert negada == {"acao": "escopo_negado", "status": 403}
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
    headers = _headers(token)
    recebido = client.post(
        "/api/erp/v1/documents",
        headers=headers,
        files={"arquivos": ("teste.pdf", b"nao e um pdf valido", "application/pdf")},
    )
    assert recebido.status_code == 422, recebido.text
    envio_id = recebido.json()["envio_id"]
    reserva = db.q(
        """SELECT envio_id, status FROM integracao_requisicoes
           WHERE integracao_id=(SELECT id FROM integracoes WHERE token_hash=?)
           AND chave=?""",
        (hash_token(token), headers["Idempotency-Key"]),
        um=True,
    )
    assert reserva == {"envio_id": envio_id, "status": "concluido"}

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
    headers_horizonte = _headers(token_horizonte)
    recebido = client.post(
        "/api/erp/v1/documents",
        headers=headers_horizonte,
        files={"arquivos": ("teste.pdf", b"conteudo", "application/pdf")},
    )
    assert recebido.status_code == 422, recebido.text
    envio_id = recebido.json()["envio_id"]

    token_marazul = _integracao(client, workspace="marazul")
    headers_marazul = _headers(token_marazul)
    resposta = client.get(
        f"/api/erp/v1/documents/{envio_id}",
        headers=headers_marazul,
    )
    assert resposta.status_code == 404


def test_recebimento_rejeita_extensao_nao_permitida(client):
    token = _integracao(client)
    response = client.post(
        "/api/erp/v1/documents",
        headers=_headers(token),
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
    headers = _headers(token)
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
    headers = _headers(token)
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



def test_idempotencia_reproduz_resposta_sem_chamar_pipeline_duas_vezes(client, monkeypatch):
    token = _integracao(client, permissoes=["documents:write"])
    headers = _headers(token)
    envio_id = db.x(
        """INSERT INTO envios(ws, nome, origem, criado_em, status)
           VALUES(?,?,?,?,?)""",
        ("horizonte", "idempotente.pdf", "ERP: ERP endpoints", db.agora(), "fila"),
    )
    chamadas = {"total": 0}

    def pipeline_simulado(*args, **kwargs):
        chamadas["total"] += 1
        return {
            "envio_id": envio_id,
            "status": "fila",
            "documentos_aceitos": 1,
            "documentos_xml": 0,
            "arquivos_com_paginas": 1,
            "paginas_enfileiradas": 1,
            "arquivos_duplicados": 0,
            "somente_duplicados": False,
        }

    monkeypatch.setattr("app.integrations.erp.pipeline.criar_envio", pipeline_simulado)
    arquivos = {"arquivos": ("idempotente.pdf", b"conteudo idempotente", "application/pdf")}
    primeira = client.post("/api/erp/v1/documents", headers=headers, files=arquivos)
    segunda = client.post("/api/erp/v1/documents", headers=headers, files=arquivos)

    assert primeira.status_code == 202
    assert segunda.status_code == primeira.status_code
    assert segunda.json() == primeira.json()
    assert segunda.headers.get("Idempotency-Replayed") == "true"
    assert chamadas["total"] == 1


def test_idempotency_key_nao_aceita_conteudo_diferente(client, monkeypatch):
    token = _integracao(client, permissoes=["documents:write"])
    headers = _headers(token)
    envio_id = db.x(
        """INSERT INTO envios(ws, nome, origem, criado_em, status)
           VALUES(?,?,?,?,?)""",
        ("horizonte", "idempotente.pdf", "ERP: ERP endpoints", db.agora(), "fila"),
    )
    monkeypatch.setattr(
        "app.integrations.erp.pipeline.criar_envio",
        lambda *args, **kwargs: {
            "envio_id": envio_id, "status": "fila", "documentos_aceitos": 1,
            "documentos_xml": 0, "arquivos_com_paginas": 1,
            "paginas_enfileiradas": 1, "arquivos_duplicados": 0,
            "somente_duplicados": False,
        },
    )
    primeira = client.post(
        "/api/erp/v1/documents", headers=headers,
        files={"arquivos": ("a.pdf", b"conteudo A", "application/pdf")},
    )
    segunda = client.post(
        "/api/erp/v1/documents", headers=headers,
        files={"arquivos": ("a.pdf", b"conteudo B", "application/pdf")},
    )
    assert primeira.status_code == 202
    assert segunda.status_code == 409


def test_chave_em_processamento_nao_dispara_novo_pipeline(client, monkeypatch):
    token = _integracao(client, permissoes=["documents:write"])
    headers = _headers(token)
    integracao = db.q(
        "SELECT id FROM integracoes WHERE token_hash=?",
        (hash_token(token),),
        um=True,
    )
    nome = "a.pdf"
    conteudo = b"conteudo"
    digest = hashlib.sha256()
    digest.update(len(nome.encode("utf-8")).to_bytes(8, "big"))
    digest.update(nome.encode("utf-8"))
    digest.update(len(conteudo).to_bytes(8, "big"))
    digest.update(conteudo)
    db.x(
        """INSERT INTO integracao_requisicoes
           (integracao_id, chave, fingerprint, status, criada_em, atualizada_em)
           VALUES(?,?,?,'processando',?,?)""",
        (integracao["id"], headers["Idempotency-Key"], digest.hexdigest(),
         db.agora(), db.agora()),
    )
    chamadas = {"total": 0}
    monkeypatch.setattr(
        "app.integrations.erp.pipeline.criar_envio",
        lambda *args, **kwargs: chamadas.update(total=chamadas["total"] + 1),
    )
    response = client.post(
        "/api/erp/v1/documents", headers=headers,
        files={"arquivos": ("a.pdf", b"conteudo", "application/pdf")},
    )
    assert response.status_code == 409
    assert chamadas["total"] == 0



def test_post_exige_idempotency_key(client):
    token = _integracao(client, permissoes=["documents:write"])
    response = client.post(
        "/api/erp/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"arquivos": ("a.pdf", b"conteudo", "application/pdf")},
    )
    assert response.status_code == 422


def test_schema_idempotente_e_aditivo(client):
    _integracao(client)
    integracoes_antes = db.q("SELECT COUNT(*) AS total FROM integracoes", um=True)["total"]
    with db._lock:
        db._con.executescript(db.SCHEMA)
        db._con.commit()
    tabelas = db.q(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='integracao_requisicoes'"
    )
    integracoes_depois = db.q("SELECT COUNT(*) AS total FROM integracoes", um=True)["total"]
    assert tabelas == [{"name": "integracao_requisicoes"}]
    assert integracoes_depois == integracoes_antes



def test_admin_pode_liberar_reserva_indeterminada_sem_envio(client):
    token = _integracao(client)
    integracao = db.q(
        "SELECT id FROM integracoes WHERE token_hash=?",
        (hash_token(token),),
        um=True,
    )
    chave = "recuperacao-segura-01"
    db.x(
        """INSERT INTO integracao_requisicoes
           (integracao_id, chave, fingerprint, status, criada_em, atualizada_em)
           VALUES(?,?,?,'indeterminado',?,?)""",
        (integracao["id"], chave, "fingerprint", db.agora(), db.agora()),
    )

    pendentes = client.get(f"/api/integracoes/{integracao['id']}/requisicoes")
    assert pendentes.status_code == 200
    assert any(item["chave"] == chave for item in pendentes.json())

    liberada = client.post(
        f"/api/integracoes/{integracao['id']}/requisicoes/{chave}/desbloquear"
    )
    assert liberada.status_code == 200, liberada.text
    assert db.q(
        "SELECT id FROM integracao_requisicoes WHERE integracao_id=? AND chave=?",
        (integracao["id"], chave),
        um=True,
    ) is None
    evento = db.q(
        """SELECT acao FROM integracao_eventos
           WHERE integracao_id=? ORDER BY id DESC LIMIT 1""",
        (integracao["id"],),
        um=True,
    )
    assert evento["acao"] == "idempotencia_desbloqueada_sem_envio"


def test_admin_nao_pode_liberar_reserva_com_envio_associado(client):
    token = _integracao(client)
    integracao = db.q(
        "SELECT id FROM integracoes WHERE token_hash=?",
        (hash_token(token),),
        um=True,
    )
    envio_id = db.x(
        """INSERT INTO envios(ws, nome, origem, criado_em, status)
           VALUES(?,?,?,?,?)""",
        ("horizonte", "recuperacao.pdf", "ERP: ERP endpoints", db.agora(), "fila"),
    )
    chave = "recuperacao-com-envio-02"
    db.x(
        """INSERT INTO integracao_requisicoes
           (integracao_id, chave, fingerprint, status, envio_id, criada_em, atualizada_em)
           VALUES(?,?,?,'indeterminado',?,?,?)""",
        (integracao["id"], chave, "fingerprint", envio_id, db.agora(), db.agora()),
    )
    response = client.post(
        f"/api/integracoes/{integracao['id']}/requisicoes/{chave}/desbloquear"
    )
    assert response.status_code == 409
    assert db.q(
        "SELECT envio_id FROM integracao_requisicoes WHERE integracao_id=? AND chave=?",
        (integracao["id"], chave),
        um=True,
    ) == {"envio_id": envio_id}



def test_admin_nao_libera_processando_mesmo_com_confirmacao(client):
    token = _integracao(client)
    integracao = db.q(
        "SELECT id FROM integracoes WHERE token_hash=?",
        (hash_token(token),),
        um=True,
    )
    chave = "recuperacao-processando-03"
    db.x(
        """INSERT INTO integracao_requisicoes
           (integracao_id, chave, fingerprint, status, criada_em, atualizada_em)
           VALUES(?,?,?,'processando',?,?)""",
        (integracao["id"], chave, "fingerprint", db.agora(), db.agora()),
    )

    sem_confirmacao = client.post(
        f"/api/integracoes/{integracao['id']}/requisicoes/{chave}/desbloquear"
    )
    assert sem_confirmacao.status_code == 409

    confirmada = client.post(
        f"/api/integracoes/{integracao['id']}/requisicoes/{chave}/desbloquear",
        json={"confirmar_processamento_encerrado": True},
    )
    assert confirmada.status_code == 409, confirmada.text
    assert db.q(
        "SELECT id FROM integracao_requisicoes WHERE integracao_id=? AND chave=?",
        (integracao["id"], chave),
        um=True,
    ) is not None



def test_falha_no_pipeline_bloqueia_reenvio_e_permite_reconciliacao(monkeypatch):
    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as c:
        token = _integracao(c, permissoes=["documents:write"])
        headers = _headers(token)

        def pipeline_com_falha(*args, **kwargs):
            raise RuntimeError("falha simulada depois da reserva")

        monkeypatch.setattr(
            "app.integrations.erp.pipeline.criar_envio",
            pipeline_com_falha,
        )
        primeira = c.post(
            "/api/erp/v1/documents",
            headers=headers,
            files={"arquivos": ("falha.pdf", b"conteudo", "application/pdf")},
        )
        assert primeira.status_code == 500

        reserva = db.q(
            """SELECT status, envio_id FROM integracao_requisicoes
               WHERE integracao_id=(SELECT id FROM integracoes WHERE token_hash=?)
               AND chave=?""",
            (hash_token(token), headers["Idempotency-Key"]),
            um=True,
        )
        assert reserva == {"status": "indeterminado", "envio_id": None}

        segunda = c.post(
            "/api/erp/v1/documents",
            headers=headers,
            files={"arquivos": ("falha.pdf", b"conteudo", "application/pdf")},
        )
        assert segunda.status_code == 409

        integracao = db.q(
            "SELECT id FROM integracoes WHERE token_hash=?",
            (hash_token(token),),
            um=True,
        )
        liberada = c.post(
            f"/api/integracoes/{integracao['id']}/requisicoes/{headers['Idempotency-Key']}/desbloquear"
        )
        assert liberada.status_code == 200, liberada.text


def test_erp_respostas_nao_expõem_metadados_de_texto_livre(client):
    """Nomes de arquivos, empresa e descrição podem conter CPF e não são retornados."""
    token = _integracao(client)
    headers = _headers(token)
    envio_id = db.x(
        """INSERT INTO envios(ws, nome, origem, criado_em, status)
           VALUES(?,?,?,?,?)""",
        ("horizonte", "CPF 123.456.789-09.pdf", "origem com 12345678909", db.agora(), "fila"),
    )
    lista = client.get("/api/erp/v1/documents", headers=headers)
    item = next(item for item in lista.json()["items"] if item["id"] == envio_id)
    detalhe = client.get(f"/api/erp/v1/documents/{envio_id}", headers=headers)
    resultados = client.get(f"/api/erp/v1/documents/{envio_id}/results", headers=headers)
    assert lista.status_code == detalhe.status_code == resultados.status_code == 200
    for resposta in (item, detalhe.json(), resultados.json()):
        assert "12345678909" not in str(resposta)
        assert "123.456.789-09" not in str(resposta)
    assert "nome" not in item and "origem" not in item
    assert "nome" not in detalhe.json() and "origem" not in detalhe.json()


def test_duas_requisicoes_simultaneas_mesma_chave_executam_uma_vez(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    token = _integracao(client, permissoes=["documents:write"])
    headers = _headers(token)
    iniciado, liberar = Event(), Event()
    chamadas = []
    envio_id = db.x(
        "INSERT INTO envios(ws, nome, origem, criado_em, status) VALUES(?,?,?,?,?)",
        ("horizonte", "paralelo.pdf", "ERP", db.agora(), "fila"),
    )

    def pipeline_lento(*args, **kwargs):
        chamadas.append(1)
        iniciado.set()
        assert liberar.wait(10), "pipeline bloqueado além do prazo do teste"
        return {
            "envio_id": envio_id, "status": "fila", "documentos_aceitos": 1,
            "documentos_xml": 0, "arquivos_com_paginas": 1,
            "paginas_enfileiradas": 1, "arquivos_duplicados": 0,
            "somente_duplicados": False,
        }

    monkeypatch.setattr("app.integrations.erp.pipeline.criar_envio", pipeline_lento)
    files = {"arquivos": ("paralelo.pdf", b"conteudo paralelo", "application/pdf")}
    with ThreadPoolExecutor(max_workers=2) as executor:
        primeira = executor.submit(
            client.post, "/api/erp/v1/documents", headers=headers, files=files
        )
        try:
            assert iniciado.wait(10), "primeira requisição não começou"
            segunda = executor.submit(
                client.post, "/api/erp/v1/documents", headers=headers, files=files
            ).result(timeout=10)
            assert segunda.status_code == 409, segunda.text
        finally:
            liberar.set()
        assert primeira.result(timeout=10).status_code == 202
    assert len(chamadas) == 1


def test_execucao_antiga_nao_vincula_envio_a_tentativa_nova(monkeypatch):
    """Fencing: callback anterior não pode vincular novo envio após liberação da chave."""
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False) as c:
        token = _integracao(c, permissoes=["documents:write"])
        headers = _headers(token)
        chaves_anteriores = []

        def pipeline_com_erro(*args, **kwargs):
            chaves_anteriores.append(kwargs["ao_criar_envio"])
            raise RuntimeError("falha antes da associação do envio")

        monkeypatch.setattr("app.integrations.erp.pipeline.criar_envio", pipeline_com_erro)
        arquivos = {"arquivos": ("tentativa.pdf", b"dados originais", "application/pdf")}
        primeira = c.post("/api/erp/v1/documents", headers=headers, files=arquivos)
        assert primeira.status_code == 500
        integracao_id = db.q(
            "SELECT id FROM integracoes WHERE token_hash=?", (hash_token(token),), um=True
        )["id"]
        anterior = db.q(
            "SELECT tentativa_id, status FROM integracao_requisicoes WHERE integracao_id=? AND chave=?",
            (integracao_id, headers["Idempotency-Key"]), um=True,
        )
        assert anterior["tentativa_id"] and anterior["status"] == "indeterminado"
        liberada = c.post(
            f"/api/integracoes/{integracao_id}/requisicoes/{headers['Idempotency-Key']}/desbloquear"
        )
        assert liberada.status_code == 200, liberada.text

        def pipeline_novo(*args, **kwargs):
            with pytest.raises(RuntimeError):
                db.transacao(lambda conn: chaves_anteriores[0](conn, 99999))
            def criar(conn):
                cur = conn.execute(
                    "INSERT INTO envios(ws, nome, origem, criado_em, status) VALUES(?,?,?,?,?)",
                    ("horizonte", "tentativa-nova.pdf", "ERP", db.agora(), "fila"),
                )
                kwargs["ao_criar_envio"](conn, cur.lastrowid)
                return cur.lastrowid
            novo_envio = db.transacao(criar)
            return {
                "envio_id": novo_envio, "status": "fila", "documentos_aceitos": 1,
                "documentos_xml": 0, "arquivos_com_paginas": 1,
                "paginas_enfileiradas": 1, "arquivos_duplicados": 0,
                "somente_duplicados": False,
            }

        monkeypatch.setattr("app.integrations.erp.pipeline.criar_envio", pipeline_novo)
        segunda = c.post("/api/erp/v1/documents", headers=headers, files=arquivos)
        assert segunda.status_code == 202, segunda.text
        atual = db.q(
            "SELECT tentativa_id, envio_id, status FROM integracao_requisicoes WHERE integracao_id=? AND chave=?",
            (integracao_id, headers["Idempotency-Key"]), um=True,
        )
        assert atual["tentativa_id"] != anterior["tentativa_id"]
        assert atual["envio_id"] == segunda.json()["envio_id"]
        assert atual["status"] == "concluido"


def test_falha_apos_vincular_envio_nao_permite_desbloqueio(monkeypatch):
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False) as c:
        token = _integracao(c, permissoes=["documents:write"])
        headers = _headers(token)
        def pipeline_falha_apos_envio(*args, **kwargs):
            def gravar(conn):
                cur = conn.execute(
                    "INSERT INTO envios(ws, nome, origem, criado_em, status) VALUES(?,?,?,?,?)",
                    ("horizonte", "vinculado.pdf", "ERP", db.agora(), "recebendo"),
                )
                kwargs["ao_criar_envio"](conn, cur.lastrowid)
                return cur.lastrowid
            db.transacao(gravar)
            raise RuntimeError("falha após vínculo")
        monkeypatch.setattr("app.integrations.erp.pipeline.criar_envio", pipeline_falha_apos_envio)
        arquivos = {"arquivos": ("vinculado.pdf", b"enviado", "application/pdf")}
        resposta = c.post("/api/erp/v1/documents", headers=headers, files=arquivos)
        assert resposta.status_code == 500
        integracao_id = db.q(
            "SELECT id FROM integracoes WHERE token_hash=?", (hash_token(token),), um=True
        )["id"]
        atual = db.q(
            "SELECT status, envio_id FROM integracao_requisicoes WHERE integracao_id=? AND chave=?",
            (integracao_id, headers["Idempotency-Key"]), um=True,
        )
        assert atual["status"] == "indeterminado" and atual["envio_id"]
        assert c.post(
            f"/api/integracoes/{integracao_id}/requisicoes/{headers['Idempotency-Key']}/desbloquear"
        ).status_code == 409
        assert c.post("/api/erp/v1/documents", headers=headers, files=arquivos).status_code == 409


def test_reserva_processando_permanece_bloqueada_em_nova_sessao(client):
    """Uma nova sessão do app não pode executar a mesma chave de reserva pendente."""
    token = _integracao(client, permissoes=["documents:write"])
    headers = _headers(token)
    integracao_id = db.q(
        "SELECT id FROM integracoes WHERE token_hash=?", (hash_token(token),), um=True
    )["id"]
    db.x(
        """INSERT INTO integracao_requisicoes
           (integracao_id, chave, fingerprint, tentativa_id, status, criada_em, atualizada_em)
           VALUES(?,?,?,'antiga-tentativa','processando',?,?)""",
        (integracao_id, headers["Idempotency-Key"], "fingerprint", db.agora(), db.agora()),
    )
    from fastapi.testclient import TestClient
    with TestClient(app) as nova_sessao:
        resposta = nova_sessao.post(
            "/api/erp/v1/documents", headers=headers,
            files={"arquivos": ("reinicio.pdf", b"conteudo", "application/pdf")},
        )
        assert resposta.status_code == 409
