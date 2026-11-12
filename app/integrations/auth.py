"""Autenticação máquina a máquina para integrações ERP.

Não reutiliza cookies/sessões humanas: cada credencial pertence a um único workspace.
"""
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from .. import db
from .security import hash_token, token_confere


_RE_BEARER = re.compile(r"^Bearer ([A-Za-z0-9_-]+)$")


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


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
        if expira <= _agora_utc():
            raise HTTPException(401, "Credencial de integração expirada.")

    db.x("UPDATE integracoes SET ultimo_acesso=? WHERE id=?", (_agora_utc().isoformat(), integracao["id"]))
    db.x(
        """INSERT INTO integracao_eventos(integracao_id, ws, acao, endpoint, status, quando)
           VALUES(?,?,?,?,?,?)""",
        (integracao["id"], integracao["ws"], "autenticacao", request.url.path, 200, _agora_utc().isoformat()),
    )
    integracao["permissoes"] = json.loads(integracao["permissoes"] or "[]")
    return integracao


def exigir_escopo(integracao: dict, escopo: str) -> None:
    if escopo not in integracao.get("permissoes", []):
        raise HTTPException(403, "A integração não possui permissão para esta operação.")
