"""Login com perfis (admin, revisor, operador).

- Senhas guardadas com PBKDF2-SHA256 e sal.
- Sessão em cookie HttpOnly assinado com HMAC (também vale para imagens e downloads).
- Perfis:  operador -> envia e consulta | revisor -> + decide pendências e revela dados
           admin    -> + configurações, tipos de documento e avaliação.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import HTTPException, Request

from . import db
from .config import DADOS

COOKIE = "concilia_sessao"
DURACAO = 12 * 3600
PERFIS = {"admin": 3, "revisor": 2, "operador": 1}
NOMES = {"admin": "Administrador", "revisor": "Revisor", "operador": "Operador"}


def _segredo() -> bytes:
    s = os.environ.get("CONCILIA_SEGREDO", "").strip()
    if s:
        return s.encode()
    arq = DADOS / "segredo.txt"
    if not arq.exists():
        arq.write_text(secrets.token_hex(32), encoding="utf-8")
    return arq.read_text(encoding="utf-8").strip().encode()


def hash_senha(senha: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, 200_000)
    return f"{sal.hex()}${h.hex()}"


def confere_senha(senha: str, guardado: str) -> bool:
    try:
        sal, h = guardado.split("$")
        return hmac.compare_digest(hash_senha(senha, bytes.fromhex(sal)).split("$")[1], h)
    except ValueError:
        return False


def criar_usuarios_padrao():
    """Contas de demonstração. Senhas vêm do .env (CONCILIA_SENHA_ADMIN etc.) ou do padrão abaixo."""
    padrao = {"admin": ("Administrador", "admin123"), "revisor": ("Revisora", "revisor123"),
              "operador": ("Operador", "operador123")}
    sem_env = [u for u in padrao if not os.environ.get(f"CONCILIA_SENHA_{u.upper()}", "").strip()]
    if sem_env:
        print(f"ATENÇÃO: {', '.join(sem_env)} sem senha no .env: valem as senhas de demonstração (ex.: admin123). "
              "Defina CONCILIA_SENHA_* antes de abrir o sistema na rede.")
    for usuario, (nome, senha) in padrao.items():
        do_env = os.environ.get(f"CONCILIA_SENHA_{usuario.upper()}", "").strip()
        atual = db.q("SELECT senha_hash FROM usuarios WHERE usuario=?", (usuario,), um=True)
        if not atual:
            db.x("INSERT INTO usuarios VALUES(?,?,?,?)", (usuario, nome, usuario, hash_senha(do_env or senha)))
        elif do_env and not confere_senha(do_env, atual["senha_hash"]):
            # Senha trocada no .env: vale na próxima vez que o sistema abrir (antes, só valia num banco novo).
            db.x("UPDATE usuarios SET senha_hash=? WHERE usuario=?", (hash_senha(do_env), usuario))


def _assinar(dados: dict) -> str:
    corpo = base64.urlsafe_b64encode(json.dumps(dados).encode()).decode()
    assinatura = hmac.new(_segredo(), corpo.encode(), hashlib.sha256).hexdigest()
    return f"{corpo}.{assinatura}"


def _ler(token: str) -> dict | None:
    try:
        corpo, assinatura = token.rsplit(".", 1)
    except ValueError:
        return None
    certo = hmac.new(_segredo(), corpo.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(certo, assinatura):
        return None
    dados = json.loads(base64.urlsafe_b64decode(corpo.encode()))
    if dados.get("exp", 0) <= time.time():
        return None
    if dados.get("sid") and db.q("SELECT 1 FROM sessoes_encerradas WHERE sid=?", (dados["sid"],)):
        return None  # a pessoa clicou em "Sair": o cookie copiado antes não vale mais
    return dados


# Tentativas de login: depois de LIMITE_TENTATIVAS erros seguidos, o usuário espera BLOQUEIO_SEGUNDOS.
LIMITE_TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 5 * 60
_erros_login: dict[str, list[float]] = {}


def entrar(usuario, senha) -> tuple[str, dict]:
    if not isinstance(usuario, str) or not isinstance(senha, str):
        raise HTTPException(400, "Informe usuário e senha.")
    usuario = usuario.strip().lower()
    agora = time.time()
    recentes = [t for t in _erros_login.get(usuario, []) if agora - t < BLOQUEIO_SEGUNDOS]
    if len(recentes) >= LIMITE_TENTATIVAS:
        espera = int(BLOQUEIO_SEGUNDOS - (agora - recentes[0])) // 60 + 1
        raise HTTPException(429, f"Muitas tentativas erradas. Tente de novo em {espera} min.")
    u = db.q("SELECT * FROM usuarios WHERE usuario=?", (usuario,), um=True)
    if not u or not confere_senha(senha, u["senha_hash"]):
        _erros_login[usuario] = [*recentes, agora]
        raise HTTPException(401, "Usuário ou senha incorretos.")
    _erros_login.pop(usuario, None)
    publico = {"usuario": u["usuario"], "nome": u["nome"], "perfil": u["perfil"]}
    return _assinar({**publico, "exp": agora + DURACAO, "sid": secrets.token_hex(16)}), publico


def sair(request: Request):
    """Encerra a sessão do cookie: o token deixa de valer mesmo que alguém tenha copiado."""
    token = request.cookies.get(COOKIE)
    dados = _ler(token) if token else None
    if dados and dados.get("sid"):
        db.x("INSERT OR IGNORE INTO sessoes_encerradas(sid, exp) VALUES(?,?)", (dados["sid"], dados["exp"]))
        db.x("DELETE FROM sessoes_encerradas WHERE exp < ?", (time.time(),))


def usuario_da_requisicao(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    return _ler(token) if token else None


def exigir(request: Request, perfil_minimo: str) -> dict:
    u = getattr(request.state, "usuario", None) or usuario_da_requisicao(request)
    if not u:
        raise HTTPException(401, "Entre na sua conta para continuar.")
    if PERFIS.get(u["perfil"], 0) < PERFIS[perfil_minimo]:
        raise HTTPException(403, f"Só {NOMES[perfil_minimo].lower()} ou acima pode fazer isso.")
    return u
