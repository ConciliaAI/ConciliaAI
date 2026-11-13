"""Ponto de entrada da API ERP e dependências de autenticação máquina a máquina.

As rotas deste módulo não usam cookies/sessões humanas. Cada endpoint declara
exigir_integracao(<escopo>) e obtém o workspace exclusivamente da credencial.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from .. import config, db, pipeline
from .auth import autenticar_integracao, exigir_escopo


router = APIRouter(prefix="/api/erp/v1", tags=["Integração ERP"])

MAX_ARQUIVOS = 20
EXTENSOES_PERMITIDAS = {
    ".xml", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    ".bmp", ".webp", ".zip",
}


def exigir_integracao(escopo: str):
    """Cria dependência que valida Bearer Token e o escopo exigido pela rota."""
    def dependencia(request: Request) -> dict:
        integracao = autenticar_integracao(request)
        exigir_escopo(integracao, escopo)
        return integracao

    return dependencia


def _sanitizar_envio(envio: dict) -> dict:
    """Remove detalhes internos de erro antes de expor um envio à integração ERP."""
    resposta = dict(envio)
    erro_interno = resposta.pop("erro", None)

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
    integracao: dict = Depends(exigir_integracao("documents:write")),
):
    """Recebe arquivos do ERP e os encaminha ao pipeline documental já existente."""
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

    try:
        resultado = pipeline.criar_envio(
            integracao["ws"],
            recebidos,
            origem=f"ERP: {integracao['nome']}",
            usuario=f"integracao:{integracao['id']}",
            retornar_detalhes=True,
        )
    except Exception:
        # O pipeline pode ter persistido parte do envio; não mascaramos a falha.
        raise

    envio_id = resultado["envio_id"]
    envio = _envio_do_workspace(envio_id, integracao["ws"])

    if resultado["documentos_aceitos"] > 0:
        codigo_http = 200 if resultado["status"] == "concluido" else 202
        codigo_resultado = (
            "PROCESSED" if codigo_http == 200 else "ACCEPTED_FOR_PROCESSING"
        )
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

    _auditar(integracao, request, "documentos_recebidos", codigo_http)
    return JSONResponse(
        status_code=codigo_http,
        content={
            "envio_id": envio_id,
            "status": envio["status"],
            "resultado": codigo_resultado,
            "documentos_aceitos": resultado["documentos_aceitos"],
            "documentos_xml_processados": resultado["documentos_xml"],
            "arquivos_com_paginas": resultado["arquivos_com_paginas"],
            "paginas_enfileiradas": resultado["paginas_enfileiradas"],
            "arquivos_duplicados": resultado["arquivos_duplicados"],
            "mensagem": mensagem,
        },
    )


@router.get("/documents")
def listar_envios(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    integracao: dict = Depends(exigir_integracao("results:read")),
):
    """Lista envios do workspace da credencial, com paginação."""
    envios = db.q(
        """SELECT id, nome, origem, criado_em, status, total, feitas, erro,
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
        """SELECT id, tipo, conf, pag_ini, pag_fim, empresa, status, criado_em,
                  subtipo, subtipo_revisao
           FROM docs WHERE envio_id=? AND ws=? ORDER BY id""",
        (envio_id, integracao["ws"]),
    )
    notas_nfse = db.q(
        """SELECT id, numero, data_emissao, competencia, nome_prestador,
                  descricao, valor, valor_liquido, status, origem
           FROM notas WHERE envio_id=? AND ws=? ORDER BY id""",
        (envio_id, integracao["ws"]),
    )
    documentos_fiscais = db.q(
        """SELECT id, nome_arquivo, modelo, tipo, versao, numero, chave,
                  emissao, emissor, destinatario, criado_em
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
