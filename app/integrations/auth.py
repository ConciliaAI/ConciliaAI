"""Autenticação máquina a máquina para integrações ERP.

A autenticação valida a credencial; a decisão de escopo é auditada separadamente
para que um 403 não seja registrado incorretamente como operação autorizada.
"""
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from .. import db
from .security import hash_token, token_confere


_RE_BEARER = re.compile(r"^Bearer ([A-Za-z0-9_-]+)$")


def _agora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def autenticar_integracao(request: Request) -> dict:
    """Valida Bearer token e retorna a integração com workspace derivado do cadastro."""
    cabecalho = request.headers.get("Authorization", "")
    match = _RE_BEARER.fullmatch(cabecalho)
    if not match:
        raise HTTPException(401, "Credencial de integração ausente ou inválida.")

    token = match.group(1)
    hash_recebido = hash_token(token)
    integracao = db.q(
        """SELECT id, nome, ws, token_hash, permissoes, ativa, expira_em, revogada_em
           FROM integracoes WHERE token_hash=?""",
        (hash_recebido,),
        um=True,
    )
    if not integracao or not token_confere(token, integracao["token_hash"]):
        raise HTTPException(401, "Credencial de integração inválida.")
    if not integracao["ativa"] or integracao["revogada_em"]:
        raise HTTPException(401, "Credencial de integração revogada ou inativa.")

    if integracao["expira_em"]:
        try:
            expira = datetime.fromisoformat(integracao["expira_em"])
            if expira.tzinfo is None:
                expira = expira.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(401, "Credencial de integração inválida.") from None
        if expira <= datetime.now(timezone.utc):
            raise HTTPException(401, "Credencial de integração expirada.")

    integracao["permissoes"] = json.loads(integracao["permissoes"] or "[]")
    return integracao


def _registrar_decisao(integracao: dict, request: Request, acao: str, status: int) -> None:
    """Registra decisão de acesso e último acesso na mesma transação SQLite."""
    agora = _agora_utc()

    def operacao(conn):
        conn.execute(
            "UPDATE integracoes SET ultimo_acesso=? WHERE id=?",
            (agora, integracao["id"]),
        )
        conn.execute(
            """INSERT INTO integracao_eventos
               (integracao_id, ws, acao, endpoint, status, quando)
               VALUES(?,?,?,?,?,?)""",
            (integracao["id"], integracao["ws"], acao, request.url.path, status, agora),
        )

    db.transacao(operacao)


def exigir_escopo(integracao: dict, escopo: str) -> None:
    if escopo not in integracao.get("permissoes", []):
        raise HTTPException(403, "A integração não possui permissão para esta operação.")


def autorizar_integracao(request: Request, escopo: str) -> dict:
    """Valida credencial e audita explicitamente autorização ou negativa de escopo."""
    integracao = autenticar_integracao(request)
    try:
        exigir_escopo(integracao, escopo)
    except HTTPException:
        _registrar_decisao(integracao, request, "escopo_negado", 403)
        raise
    _registrar_decisao(integracao, request, "escopo_autorizado", 200)
    return integracao
