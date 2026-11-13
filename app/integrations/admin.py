"""API administrativa de credenciais ERP (somente administradores humanos)."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from .. import auth, db
from .security import gerar_token, hash_token


router = APIRouter(prefix="/api/integracoes", tags=["Integrações ERP"])
PERMISSOES_VALIDAS = {"documents:write", "results:read"}


def _administrador(request: Request) -> dict:
    return auth.exigir(request, "admin")


def _expiracao(valor):
    if valor in (None, ""):
        return None
    if not isinstance(valor, str):
        raise HTTPException(400, "expira_em deve ser uma data ISO 8601 com fuso horário.")
    try:
        data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Data de expiração inválida; use ISO 8601.") from None
    if data.tzinfo is None:
        raise HTTPException(400, "A data de expiração precisa informar o fuso horário.")
    data = data.astimezone(timezone.utc)
    if data <= datetime.now(timezone.utc):
        raise HTTPException(400, "A data de expiração precisa estar no futuro.")
    return data.isoformat()


def _permissoes(valor):
    if valor is None:
        return ["documents:write", "results:read"]
    if not isinstance(valor, list) or not valor or any(not isinstance(p, str) for p in valor):
        raise HTTPException(400, "Informe uma lista não vazia de permissões.")
    if len(set(valor)) != len(valor) or not set(valor).issubset(PERMISSOES_VALIDAS):
        raise HTTPException(400, "Permissão inválida ou repetida.")
    return valor


def _evento(conexao, integracao_id, ws, acao, administrador, status=200):
    """Registra auditoria na mesma transação da alteração administrativa."""
    conexao.execute(
        """INSERT INTO integracao_eventos(
               integracao_id, ws, acao, endpoint, status, quando,
               ator_usuario, ator_nome, ator_perfil
           ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            integracao_id, ws, acao, None, status,
            datetime.now(timezone.utc).isoformat(),
            administrador["usuario"], administrador["nome"], administrador["perfil"],
        ),
    )


def _publica(registro):
    return {
        "id": registro["id"],
        "nome": registro["nome"],
        "workspace": registro["ws"],
        "token_prefix": registro["token_prefix"],
        "permissoes": json.loads(registro["permissoes"] or "[]"),
        "ativa": bool(registro["ativa"]),
        "criada_em": registro["criada_em"],
        "expira_em": registro["expira_em"],
        "revogada_em": registro["revogada_em"],
        "ultimo_acesso": registro["ultimo_acesso"],
    }


@router.post("")
def criar(request: Request, corpo: dict):
    administrador = _administrador(request)
    nome = corpo.get("nome")
    ws = corpo.get("ws")
    if not isinstance(nome, str) or not nome.strip() or len(nome.strip()) > 120:
        raise HTTPException(400, "Informe um nome de integração de até 120 caracteres.")
    if not isinstance(ws, str) or not ws.strip():
        raise HTTPException(400, "Informe o workspace da integração.")
    if not db.q("SELECT id FROM workspaces WHERE id=?", (ws,), um=True):
        raise HTTPException(404, "Workspace não encontrado.")

    permissoes = _permissoes(corpo.get("permissoes"))
    expira = _expiracao(corpo.get("expira_em"))
    token = gerar_token()
    prefixo = token[:12]
    agora = datetime.now(timezone.utc).isoformat()
    def persistir(conexao):
        cursor = conexao.execute(
            """INSERT INTO integracoes(nome, ws, token_hash, token_prefix, permissoes, ativa, criada_em, expira_em)
               VALUES(?,?,?,?,?,1,?,?)""",
            (nome.strip(), ws, hash_token(token), prefixo, json.dumps(permissoes), agora, expira),
        )
        integracao_id = cursor.lastrowid
        _evento(conexao, integracao_id, ws, "criacao", administrador)
        return integracao_id

    integracao_id = db.transacao(persistir)
    return {"integracao": _publica(db.q("SELECT * FROM integracoes WHERE id=?", (integracao_id,), um=True)),
            "token": token, "aviso": "Guarde o token agora: ele não será exibido novamente."}


@router.get("")
def listar(request: Request):
    _administrador(request)
    registros = db.q("SELECT * FROM integracoes ORDER BY id DESC")
    return [_publica(r) for r in registros]


@router.get("/{integracao_id}")
def detalhes(request: Request, integracao_id: int):
    _administrador(request)
    registro = db.q("SELECT * FROM integracoes WHERE id=?", (integracao_id,), um=True)
    if not registro:
        raise HTTPException(404, "Integração não encontrada.")
    eventos = db.q(
        """SELECT id, acao, endpoint, status, quando, ator_usuario, ator_nome, ator_perfil FROM integracao_eventos
           WHERE integracao_id=? ORDER BY id DESC LIMIT 100""",
        (integracao_id,),
    )
    return {"integracao": _publica(registro), "eventos": eventos}


@router.post("/{integracao_id}/rotacionar")
def rotacionar(request: Request, integracao_id: int, corpo: dict | None = None):
    administrador = _administrador(request)
    registro = db.q("SELECT * FROM integracoes WHERE id=?", (integracao_id,), um=True)
    if not registro:
        raise HTTPException(404, "Integração não encontrada.")
    novo_expira = _expiracao((corpo or {}).get("expira_em")) if (corpo or {}).get("expira_em") else registro["expira_em"]
    if novo_expira:
        try:
            atual = datetime.fromisoformat(novo_expira)
            if atual.tzinfo is None:
                atual = atual.replace(tzinfo=timezone.utc)
            if atual <= datetime.now(timezone.utc):
                raise HTTPException(400, "A credencial está expirada; informe uma nova expiração futura.")
        except ValueError:
            raise HTTPException(400, "Data de expiração inválida.") from None
    token = gerar_token()
    agora = datetime.now(timezone.utc).isoformat()
    def persistir(conexao):
        conexao.execute(
            """UPDATE integracoes SET token_hash=?, token_prefix=?, ativa=1, revogada_em=NULL, expira_em=?
               WHERE id=?""",
            (hash_token(token), token[:12], novo_expira, integracao_id),
        )
        _evento(conexao, integracao_id, registro["ws"], "rotacao", administrador)

    db.transacao(persistir)
    atualizado = db.q("SELECT * FROM integracoes WHERE id=?", (integracao_id,), um=True)
    return {"integracao": _publica(atualizado), "token": token,
            "aviso": "Token anterior invalidado. Guarde o novo token agora."}


@router.post("/{integracao_id}/revogar")
def revogar(request: Request, integracao_id: int):
    administrador = _administrador(request)
    registro = db.q("SELECT * FROM integracoes WHERE id=?", (integracao_id,), um=True)
    if not registro:
        raise HTTPException(404, "Integração não encontrada.")
    agora = datetime.now(timezone.utc).isoformat()
    def persistir(conexao):
        conexao.execute(
            "UPDATE integracoes SET ativa=0, revogada_em=? WHERE id=?",
            (agora, integracao_id),
        )
        _evento(conexao, integracao_id, registro["ws"], "revogacao", administrador)

    db.transacao(persistir)
    return {"ok": True, "integracao": _publica(db.q("SELECT * FROM integracoes WHERE id=?", (integracao_id,), um=True))}
