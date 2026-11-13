"""Ponto de entrada da API ERP e dependências de autenticação máquina a máquina.

As rotas deste módulo não usam cookies/sessões humanas. Cada endpoint declara
exigir_integracao(<escopo>) e obtém o workspace exclusivamente da credencial.
"""
import hashlib
import json
import re
from uuid import uuid4
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .. import config, db, pipeline
from .auth import autorizar_integracao


router = APIRouter(prefix="/api/erp/v1", tags=["Integração ERP"])

MAX_ARQUIVOS = 20
EXTENSOES_PERMITIDAS = {
    ".xml", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    ".bmp", ".webp", ".zip",
}


def exigir_integracao(escopo: str):
    """Cria dependência que valida Bearer Token e o escopo exigido pela rota."""
    def dependencia(request: Request) -> dict:
        return autorizar_integracao(request, escopo)

    return dependencia


def _sanitizar_envio(envio: dict) -> dict:
    """Remove detalhes internos de erro antes de expor um envio à integração ERP."""
    resposta = dict(envio)
    erro_interno = resposta.pop("erro", None)
    # Nomes de arquivos e origens são texto livre: podem conter CPF, dados pessoais ou caminhos.
    resposta.pop("nome", None)
    resposta.pop("origem", None)

    resposta["erro_codigo"] = None
    resposta["erro_mensagem"] = None

    if erro_interno:
        if "já foi enviado" in str(erro_interno).lower():
            resposta["erro_codigo"] = "DUPLICATE_DOCUMENT"
            resposta["erro_mensagem"] = (
                "O documento já havia sido recebido anteriormente e não foi importado novamente."
            )
        elif resposta.get("status") == "recusado":
            resposta["erro_codigo"] = "DOCUMENTS_REJECTED"
            resposta["erro_mensagem"] = (
                "O envio não contém documentos válidos para processamento."
            )
        elif resposta.get("status") == "falhou":
            resposta["erro_codigo"] = "PROCESSING_FAILED"
            resposta["erro_mensagem"] = (
                "Não foi possível concluir o processamento. Consulte o suporte."
            )
        else:
            resposta["erro_codigo"] = "PROCESSING_ERROR"
            resposta["erro_mensagem"] = (
                "Ocorreu um problema no processamento. Consulte o suporte."
            )

    return resposta


def _envio_do_workspace(envio_id: int, ws: str) -> dict:
    """Retorna 404 também quando o envio existe, mas pertence a outro workspace."""
    envio = db.q(
        "SELECT id, ws, nome, origem, criado_em, status, total, feitas, erro, "
        "retomadas, motor, terminado_em, notas_xml FROM envios WHERE id=? AND ws=?",
        (envio_id, ws),
        um=True,
    )
    if not envio:
        raise HTTPException(404, "Envio não encontrado.")
    return envio


def _auditar(integracao: dict, request: Request, acao: str, status: int) -> None:
    """Registra a operação sem armazenar token, conteúdo ou dados dos documentos."""
    db.x(
        """INSERT INTO integracao_eventos(integracao_id, ws, acao, endpoint, status, quando)
           VALUES(?,?,?,?,?,?)""",
        (integracao["id"], integracao["ws"], acao, request.url.path, status, db.agora()),
    )


@router.post("/documents")
async def receber_documentos(
    request: Request,
    arquivos: list[UploadFile] = File(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    integracao: dict = Depends(exigir_integracao("documents:write")),
):
    """Recebe arquivos; uma chave por operação impede reprocessamento em retries."""
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", idempotency_key):
        raise HTTPException(400, "Idempotency-Key deve conter de 8 a 128 caracteres seguros.")
    if not arquivos or len(arquivos) > MAX_ARQUIVOS:
        raise HTTPException(400, f"Envie de 1 a {MAX_ARQUIVOS} arquivos por requisição.")

    max_bytes = config.MAX_MB * 1024 * 1024
    total_bytes = 0
    recebidos = []

    for arquivo in arquivos:
        nome = Path(arquivo.filename or "").name
        extensao = Path(nome).suffix.lower()
        if not nome or extensao not in EXTENSOES_PERMITIDAS:
            raise HTTPException(415, f"Formato não permitido: {nome or 'arquivo sem nome'}.")
        conteudo = await arquivo.read(max_bytes + 1)
        if not conteudo:
            raise HTTPException(400, f"O arquivo {nome} está vazio.")
        if len(conteudo) > max_bytes:
            raise HTTPException(413, f"O arquivo {nome} excede o limite de {config.MAX_MB} MB.")
        total_bytes += len(conteudo)
        if total_bytes > max_bytes:
            raise HTTPException(413, f"O conjunto de arquivos excede o limite de {config.MAX_MB} MB por requisição.")
        recebidos.append((nome, conteudo))

    # Fingerprint determinístico: considera nomes, ordem e bytes de cada arquivo.
    digest = hashlib.sha256()
    for nome, conteudo in recebidos:
        nome_bytes = nome.encode("utf-8")
        digest.update(len(nome_bytes).to_bytes(8, "big"))
        digest.update(nome_bytes)
        digest.update(len(conteudo).to_bytes(8, "big"))
        digest.update(conteudo)
    fingerprint = digest.hexdigest()
    agora = db.agora()
    tentativa_id = uuid4().hex  # identidade imutável desta execução, mesmo após desbloqueio

    # BEGIN IMMEDIATE serializa reservas concorrentes antes de qualquer efeito no pipeline.
    def reservar(conn):
        existente = conn.execute(
            """SELECT fingerprint, status, envio_id, resposta_status, resposta_json
               FROM integracao_requisicoes WHERE integracao_id=? AND chave=?""",
            (integracao["id"], idempotency_key),
        ).fetchone()
        if existente:
            return dict(existente), False
        conn.execute(
            """INSERT INTO integracao_requisicoes
               (integracao_id, chave, fingerprint, tentativa_id, status, criada_em, atualizada_em)
               VALUES(?,?,?,?,'processando',?,?)""",
            (integracao["id"], idempotency_key, fingerprint, tentativa_id, agora, agora),
        )
        conn.execute(
            """INSERT INTO integracao_eventos
               (integracao_id, ws, acao, endpoint, status, quando)
               VALUES(?,?,?,?,?,?)""",
            (integracao["id"], integracao["ws"], "recebimento_iniciado",
             request.url.path, 202, agora),
        )
        return None, True

    existente, nova = db.transacao(reservar)
    if not nova:
        if existente["fingerprint"] != fingerprint:
            raise HTTPException(409, "Idempotency-Key já utilizada com conteúdo diferente.")
        if existente["status"] == "concluido":
            return JSONResponse(
                status_code=existente["resposta_status"],
                content=json.loads(existente["resposta_json"]),
                headers={"Idempotency-Replayed": "true"},
            )
        if existente["status"] == "processando":
            raise HTTPException(
                409, "Esta requisição ainda está em processamento. Não a reenvie com outra chave.",
                headers={"Retry-After": "5"},
            )
        raise HTTPException(
            409,
            "O processamento anterior ficou indeterminado. A chave permanece bloqueada para evitar duplicidade; solicite reconciliação operacional.",
        )

    def vincular_envio(conn, envio_id):
        cur = conn.execute(
            """UPDATE integracao_requisicoes SET envio_id=?, atualizada_em=?
               WHERE integracao_id=? AND chave=? AND tentativa_id=? AND status='processando'""",
            (envio_id, db.agora(), integracao["id"], idempotency_key, tentativa_id),
        )
        if cur.rowcount != 1:
            raise RuntimeError("A reserva idempotente não pôde ser vinculada ao envio.")

    try:
        resultado = await run_in_threadpool(
            pipeline.criar_envio,
            integracao["ws"],
            recebidos,
            origem=f"ERP: {integracao['nome']}",
            usuario=f"integracao:{integracao['id']}",
            retornar_detalhes=True,
            ao_criar_envio=vincular_envio,
        )
        envio_id = resultado["envio_id"]
        envio = _envio_do_workspace(envio_id, integracao["ws"])

        if resultado["documentos_aceitos"] > 0:
            codigo_http = 200 if resultado["status"] == "concluido" else 202
            codigo_resultado = "PROCESSED" if codigo_http == 200 else "ACCEPTED_FOR_PROCESSING"
            mensagem = (
                "Documento(s) recebido(s) e processado(s) diretamente."
                if codigo_http == 200
                else "Documento(s) recebido(s) e encaminhado(s) para processamento."
            )
        elif resultado["somente_duplicados"]:
            codigo_http = 409
            codigo_resultado = "DUPLICATE_DOCUMENT"
            mensagem = "Todos os documentos enviados já haviam sido recebidos anteriormente."
        else:
            codigo_http = 422
            codigo_resultado = "NO_ACCEPTED_DOCUMENTS"
            mensagem = "Nenhum documento válido foi identificado no envio."

        payload = {
            "envio_id": envio_id,
            "status": envio["status"],
            "resultado": codigo_resultado,
            "documentos_aceitos": resultado["documentos_aceitos"],
            "documentos_xml_processados": resultado["documentos_xml"],
            "arquivos_com_paginas": resultado["arquivos_com_paginas"],
            "paginas_enfileiradas": resultado["paginas_enfileiradas"],
            "arquivos_duplicados": resultado["arquivos_duplicados"],
            "mensagem": mensagem,
        }
        resposta_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        finalizado = db.agora()

        def concluir(conn):
            conn.execute(
                """UPDATE integracao_requisicoes
                   SET status='concluido', envio_id=?, resposta_status=?,
                       resposta_json=?, atualizada_em=?
                   WHERE integracao_id=? AND chave=? AND tentativa_id=? AND status='processando'""",
                (envio_id, codigo_http, resposta_json, finalizado,
                 integracao["id"], idempotency_key, tentativa_id),
            )
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                raise RuntimeError("Não foi possível finalizar a reserva idempotente.")
            conn.execute(
                """INSERT INTO integracao_eventos
                   (integracao_id, ws, acao, endpoint, status, quando)
                   VALUES(?,?,?,?,?,?)""",
                (integracao["id"], integracao["ws"], "recebimento_concluido",
                 request.url.path, codigo_http, finalizado),
            )

        db.transacao(concluir)
        return JSONResponse(status_code=codigo_http, content=payload)
    except BaseException:
        # Inclui cancelamento da tarefa: a chave continua bloqueada e rastreável.
        # Não liberar a chave: o pipeline pode ter persistido dados antes da falha.
        try:
            def registrar_falha(conn):
                cur = conn.execute(
                    """UPDATE integracao_requisicoes SET status='indeterminado', atualizada_em=?
                       WHERE integracao_id=? AND chave=? AND tentativa_id=? AND status='processando'""",
                    (db.agora(), integracao["id"], idempotency_key, tentativa_id),
                )
                if cur.rowcount:
                    conn.execute(
                        """INSERT INTO integracao_eventos
                           (integracao_id, ws, acao, endpoint, status, quando)
                           VALUES(?,?,?,?,?,?)""",
                        (integracao["id"], integracao["ws"], "recebimento_indeterminado",
                         request.url.path, 500, db.agora()),
                    )
            db.transacao(registrar_falha)
        except Exception:
            pass
        raise


@router.get("/documents")
def listar_envios(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    integracao: dict = Depends(exigir_integracao("results:read")),
):
    """Lista envios do workspace da credencial, com paginação."""
    envios = db.q(
        """SELECT id, criado_em, status, total, feitas, erro,
                  retomadas, motor, terminado_em, notas_xml
           FROM envios WHERE ws=? ORDER BY id DESC LIMIT ? OFFSET ?""",
        (integracao["ws"], limit, offset),
    )
    envios = [_sanitizar_envio(envio) for envio in envios]
    total = db.q(
        "SELECT COUNT(*) AS total FROM envios WHERE ws=?",
        (integracao["ws"],),
        um=True,
    )["total"]
    _auditar(integracao, request, "consulta_envios", 200)
    return {"items": envios, "limit": limit, "offset": offset, "total": total}


@router.get("/documents/{envio_id}")
def consultar_envio(
    request: Request,
    envio_id: int,
    integracao: dict = Depends(exigir_integracao("results:read")),
):
    """Consulta status e contagens de um envio pertencente ao workspace autenticado."""
    envio = _sanitizar_envio(_envio_do_workspace(envio_id, integracao["ws"]))
    envio["documentos_identificados"] = db.q(
        "SELECT COUNT(*) AS total FROM docs WHERE envio_id=? AND ws=?",
        (envio_id, integracao["ws"]),
        um=True,
    )["total"]
    envio["notas_nfse"] = db.q(
        "SELECT COUNT(*) AS total FROM notas WHERE envio_id=? AND ws=?",
        (envio_id, integracao["ws"]),
        um=True,
    )["total"]
    envio["documentos_fiscais"] = db.q(
        "SELECT COUNT(*) AS total FROM documentos_fiscais WHERE envio_id=? AND ws=?",
        (envio_id, integracao["ws"]),
        um=True,
    )["total"]
    _auditar(integracao, request, "consulta_envio", 200)
    return envio


@router.get("/documents/{envio_id}/results")
def consultar_resultados(
    request: Request,
    envio_id: int,
    integracao: dict = Depends(exigir_integracao("results:read")),
):
    """Retorna resultados estruturados sem expor XML bruto, OCR, CPF ou caminhos internos."""
    _envio_do_workspace(envio_id, integracao["ws"])

    documentos = db.q(
        """SELECT id, tipo, conf, pag_ini, pag_fim, status, criado_em,
                  subtipo, subtipo_revisao
           FROM docs WHERE envio_id=? AND ws=? ORDER BY id""",
        (envio_id, integracao["ws"]),
    )
    notas_nfse = db.q(
        """SELECT id, numero, data_emissao, competencia,
                  valor, valor_liquido, status, origem
           FROM notas WHERE envio_id=? AND ws=? ORDER BY id""",
        (envio_id, integracao["ws"]),
    )
    documentos_fiscais = db.q(
        """SELECT id, modelo, tipo, versao, numero, chave,
                  emissao, criado_em
           FROM documentos_fiscais WHERE envio_id=? AND ws=? ORDER BY id""",
        (envio_id, integracao["ws"]),
    )
    _auditar(integracao, request, "consulta_resultados", 200)
    return {
        "envio_id": envio_id,
        "documentos_identificados": documentos,
        "notas_nfse": notas_nfse,
        "documentos_fiscais": documentos_fiscais,
        "observacao": (
            "Resultados disponíveis no momento da consulta. Documentos em OCR "
            "podem receber resultados adicionais quando o processamento terminar."
        ),
    }
